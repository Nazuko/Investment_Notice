from __future__ import annotations

from typing import Protocol

from bot.models import MarketSnapshot, Position, Signal


class Strategy(Protocol):
    id: str

    def evaluate(
        self, position: Position | None, market: MarketSnapshot
    ) -> list[Signal]: ...
