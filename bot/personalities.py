from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bot.config import CONFIG_DIR
from bot.marketdata import BarStore, MIN_TURNOVER, refresh_market
from bot.screener import evaluate_skill
from bot.symbols import name_for


def load_personas(path: Path | None = None) -> dict[str, Any]:
    yaml_path = path or (CONFIG_DIR / "personalities.yaml")
    with yaml_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("personas") or {}


def run_skill(store: BarStore, persona: str, skill_id: str, *, refresh: bool = False) -> dict:
    if refresh:
        as_of = refresh_market(store, fill_history=True)
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
    hits = []
    for row in rows:
        symbol = row["symbol"]
        history = store.history(symbol)
        if not history:
            continue
        ok, reasons = evaluate_skill(skill_id, history)
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
            }
        )
    hits.sort(key=lambda r: r["turnover"], reverse=True)
    store.save_screen(persona, skill_id, as_of, hits)
    return {"as_of": as_of, "rows": hits, "count": len(hits)}
