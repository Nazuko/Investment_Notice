from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "tw_symbols.json"


@dataclass(frozen=True)
class TwSymbol:
    code: str
    name: str
    yahoo: str
    market: str  # twse | tpex


def _norm(text: str) -> str:
    return text.strip().upper().replace(" ", "")


@lru_cache(maxsize=1)
def load_catalog(path: Path | None = None) -> list[TwSymbol]:
    data_path = path or DATA_PATH
    with data_path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return [
        TwSymbol(
            code=item["code"],
            name=item["name"],
            yahoo=item["yahoo"],
            market=item["market"],
        )
        for item in raw
    ]


def _index(path: Path | None = None) -> dict[str, TwSymbol]:
    by_yahoo: dict[str, TwSymbol] = {}
    for item in load_catalog(path):
        by_yahoo[_norm(item.yahoo)] = item
        by_yahoo[_norm(item.code)] = item
    return by_yahoo


def lookup(symbol: str, path: Path | None = None) -> TwSymbol | None:
    if not symbol:
        return None
    return _index(path).get(_norm(symbol))


def name_for(symbol: str, fallback: str = "", path: Path | None = None) -> str:
    item = lookup(symbol, path)
    if item:
        return item.name
    return fallback or symbol


def search(query: str, limit: int = 20, path: Path | None = None) -> list[TwSymbol]:
    q = query.strip()
    if not q:
        # A short default list so the dropdown can open on focus.
        return load_catalog(path)[:limit]
    q_folded = q.casefold()
    q_code = _norm(q)
    ranked: list[tuple[int, TwSymbol]] = []
    for item in load_catalog(path):
        code = item.code.upper()
        name = item.name
        if q_code == code or q_code == _norm(item.yahoo):
            rank = 0
        elif code.startswith(q_code) or item.yahoo.upper().startswith(q_code):
            rank = 1
        elif q_folded in name.casefold():
            rank = 2 if name.startswith(q) else 3
        elif q_code in code:
            rank = 4
        else:
            continue
        ranked.append((rank, item))
    ranked.sort(key=lambda pair: (pair[0], pair[1].code))
    seen: set[str] = set()
    out: list[TwSymbol] = []
    for _, item in ranked:
        if item.yahoo in seen:
            continue
        seen.add(item.yahoo)
        out.append(item)
        if len(out) >= limit:
            break
    return out
