"""Refresh bot/data/tw_symbols.json from FinMind TaiwanStockInfo."""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

from bot.symbols import DATA_PATH

SOURCE = "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"
CODE_RE = re.compile(r"^[0-9]{4,6}[A-Z]?$")


def fetch_rows() -> list[dict]:
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "InvestmentNotice/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    if payload.get("status") != 200:
        raise RuntimeError(f"FinMind error: {payload.get('msg')}")
    return payload["data"]


def build_catalog(rows: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        market = row.get("type")
        code = str(row.get("stock_id") or "").strip().upper()
        name = str(row.get("stock_name") or "").strip()
        if market not in {"twse", "tpex"}:
            continue
        if not name or not CODE_RE.match(code):
            continue
        yahoo = f"{code}.TW" if market == "twse" else f"{code}.TWO"
        prev = latest.get(code)
        if prev is None or str(row.get("date") or "") >= str(prev.get("_date") or ""):
            latest[code] = {
                "code": code,
                "name": name,
                "yahoo": yahoo,
                "market": market,
                "_date": row.get("date") or "",
            }
    items = []
    for item in latest.values():
        item.pop("_date", None)
        items.append(item)
    items.sort(key=lambda x: x["code"])
    return items


def refresh(path: Path | None = None) -> Path:
    dest = path or DATA_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog(fetch_rows())
    dest.write_text(json.dumps(catalog, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    return dest


def main() -> None:
    dest = refresh()
    print(f"Wrote {dest} ({dest.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
