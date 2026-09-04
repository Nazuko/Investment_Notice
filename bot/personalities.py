from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bot.config import CONFIG_DIR
from bot.marketdata import (
    INDEX_TPEX,
    INDEX_TWSE,
    BarStore,
    MIN_TURNOVER,
    priority_yahoo_symbols,
    refresh_market,
)
from bot.mood import compute_mood, save_mood
from bot.screener import evaluate_skill
from bot.symbols import name_for


def load_personas(path: Path | None = None) -> dict[str, Any]:
    yaml_path = path or (CONFIG_DIR / "personalities.yaml")
    with yaml_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("personas") or {}


def run_skill(store: BarStore, persona: str, skill_id: str, *, refresh: bool = False) -> dict:
    if refresh:
        as_of = refresh_market(store, fill_history=True, fill_indices=True)
        save_mood(store, compute_mood(store))
    else:
        as_of = store.latest_date()
    if as_of is None:
        return {"as_of": None, "rows": [], "count": 0}

    from bot.db import connect

    with connect(store.db_path) as conn:
        rows = conn.execute(
            """
            SELECT symbol, close, volume, turnover
            FROM daily_bars
            WHERE d = ? AND turnover >= ?
            ORDER BY turnover DESC
            """,
            (as_of.isoformat(), MIN_TURNOVER),
        ).fetchall()
    symbols: list[str] = []
    seen: set[str] = set()
    skip = {INDEX_TWSE, INDEX_TPEX}
    for row in rows:
        symbol = row["symbol"]
        if symbol in skip:
            continue
        symbols.append(symbol)
        seen.add(symbol)
    for extra in priority_yahoo_symbols():
        if extra not in seen:
            symbols.append(extra)
            seen.add(extra)

    hits = []
    for symbol in symbols:
        history = store.history(symbol)
        if not history:
            continue
        ok, reasons, checks = evaluate_skill(skill_id, history)
        if not ok:
            continue
        last = history[-1]
        hits.append(
            {
                "symbol": symbol,
                "name": name_for(symbol, fallback=symbol),
                "close": last.close,
                "turnover": last.turnover,
                "volume_lots": last.volume / 1000,
                "reasons": reasons,
                "checks": checks,
            }
        )
    hits.sort(key=lambda r: r["turnover"], reverse=True)
    store.save_screen(persona, skill_id, as_of, hits)
    return {"as_of": as_of, "rows": hits, "count": len(hits)}
