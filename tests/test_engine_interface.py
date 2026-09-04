from __future__ import annotations

from datetime import datetime, timezone

from bot.engine import StrategyEngine
from bot.models import MarketSnapshot, Position, Quote, Signal
from bot.strategies.noop import NoopStrategy


class FakeBuyStrategy:
    id = "fake-buy"

    def evaluate(self, position, market):
        return [
            Signal(
                symbol=market.quote.symbol,
                side="buy",
                rule_id=self.id,
                price=market.quote.price,
                reason="test buy",
            )
        ]


def _market(symbol: str = "AAPL", price: float = 100.0) -> MarketSnapshot:
    return MarketSnapshot(
        quote=Quote(symbol=symbol, price=price, as_of=datetime.now(timezone.utc))
    )


def test_noop_returns_empty() -> None:
    engine = StrategyEngine([NoopStrategy()])
    position = Position(symbol="AAPL", qty=1, avg_cost=90)
    assert engine.evaluate(position, _market()) == []


def test_engine_collects_signals_with_null_position() -> None:
    engine = StrategyEngine([NoopStrategy(), FakeBuyStrategy()])
    signals = engine.evaluate(None, _market("MSFT", 400))
    assert len(signals) == 1
    assert signals[0].side == "buy"
    assert signals[0].symbol == "MSFT"
    assert signals[0].rule_id == "fake-buy"
