from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bot.alerts import AlertLog
from bot.engine import StrategyEngine, run_tick
from bot.holdings import HoldingsStore
from bot.models import Quote, Signal
from bot.notify.base import Notifier
from bot.notify.console import RecordingChannel
from bot.prices import StubPriceProvider


class AlwaysSell:
    id = "always-sell"

    def evaluate(self, position, market):
        return [
            Signal(
                symbol=market.quote.symbol,
                side="sell",
                rule_id=self.id,
                price=market.quote.price,
                reason="over cost",
                meta={"avg_cost": None if position is None else position.avg_cost},
            )
        ]


def test_dedupe_skips_second_send(tmp_path: Path) -> None:
    db = tmp_path / "bot.db"
    log = AlertLog(db)
    signal = Signal(
        symbol="AAPL",
        side="sell",
        rule_id="always-sell",
        price=200,
        reason="x",
    )
    assert log.recently_sent(signal, within_hours=24) is False
    log.record(signal)
    assert log.recently_sent(signal, within_hours=24) is True
    other = Signal(
        symbol="AAPL",
        side="buy",
        rule_id="always-sell",
        price=200,
        reason="x",
    )
    assert log.recently_sent(other, within_hours=24) is False


def test_run_tick_notifies_once(tmp_path: Path) -> None:
    db = tmp_path / "bot.db"
    store = HoldingsStore(db)
    store.upsert_position("AAPL", 5, 100)
    recorder = RecordingChannel()
    prices = StubPriceProvider({"AAPL": 120.0})
    kwargs = dict(
        store=store,
        prices=prices,
        engine=StrategyEngine([AlwaysSell()]),
        notifier=Notifier([recorder]),
        alert_log=AlertLog(db),
        dedupe_hours=24,
    )
    first = run_tick(**kwargs)
    second = run_tick(**kwargs)
    assert len(first) == 1
    assert first[0].side == "sell"
    assert len(recorder.sent) == 1
    assert second == []
    assert len(recorder.sent) == 1


def test_stub_price_provider() -> None:
    provider = StubPriceProvider({"2330.TW": 900})
    quote: Quote = provider.get_quote("2330.TW")
    assert quote.price == 900
    assert quote.as_of.tzinfo is timezone.utc
    hist = provider.get_history("2330.TW")
    assert hist[0].close == 900
