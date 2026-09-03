from __future__ import annotations

from bot.models import MarketSnapshot, Position, Signal


class NoopStrategy:
    """Placeholder until real condition files are uploaded and implemented."""

    id = "noop"

    def evaluate(
        self, position: Position | None, market: MarketSnapshot
    ) -> list[Signal]:
        return []
