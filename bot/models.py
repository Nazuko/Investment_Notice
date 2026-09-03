from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class Position:
    symbol: str
    qty: float
    avg_cost: float
    note: str = ""


@dataclass(frozen=True)
class WatchItem:
    symbol: str
    note: str = ""


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    as_of: datetime
    currency: str | None = None


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class MarketSnapshot:
    quote: Quote
    history: list[Bar] = field(default_factory=list)


@dataclass
class Signal:
    symbol: str
    side: Side
    rule_id: str
    price: float
    reason: str
    meta: dict[str, Any] = field(default_factory=dict)

    def dedupe_key(self) -> str:
        return f"{self.symbol}|{self.side}|{self.rule_id}"
