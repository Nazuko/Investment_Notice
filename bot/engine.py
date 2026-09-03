from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from bot.alerts import AlertLog
from bot.holdings import HoldingsStore
from bot.models import MarketSnapshot, Position, Signal, WatchItem
from bot.notify.base import Channel, Notifier
from bot.notify.console import ConsoleChannel
from bot.notify.email import EmailChannel
from bot.prices import PriceProvider, make_price_provider
from bot.strategies.registry import load_strategies


class StrategyEngine:
    def __init__(self, strategies: list) -> None:
        self.strategies = strategies

    def evaluate(
        self, position: Position | None, market: MarketSnapshot
    ) -> list[Signal]:
        signals: list[Signal] = []
        for strategy in self.strategies:
            signals.extend(strategy.evaluate(position, market))
        return signals


def build_channels(settings: dict[str, Any]) -> list[Channel]:
    names = (settings.get("notify") or {}).get("channels") or ["console"]
    channels: list[Channel] = []
    for name in names:
        if name == "console":
            channels.append(ConsoleChannel())
        elif name == "email":
            to = list((settings.get("email") or {}).get("to") or [])
            channels.append(EmailChannel(to=to or None))
        else:
            raise ValueError(
                f"Unknown notify channel '{name}'. "
                "Supported now: console, email. Stubs exist for telegram/line/discord."
            )
    return channels


def unique_symbols(positions: Iterable[Position], watch: Iterable[WatchItem]) -> list[str]:
    seen: list[str] = []
    for item in list(positions) + list(watch):
        if item.symbol not in seen:
            seen.append(item.symbol)
    return seen


def run_tick(
    *,
    store: HoldingsStore,
    prices: PriceProvider,
    engine: StrategyEngine,
    notifier: Notifier,
    alert_log: AlertLog,
    dedupe_hours: float,
    history_period: str = "6mo",
) -> list[Signal]:
    positions = {p.symbol: p for p in store.list_positions()}
    watch = store.list_watchlist()
    symbols = unique_symbols(positions.values(), watch)
    dispatched: list[Signal] = []

    for symbol in symbols:
        quote = prices.get_quote(symbol)
        history = prices.get_history(symbol, period=history_period)
        market = MarketSnapshot(quote=quote, history=history)
        position = positions.get(symbol)
        for signal in engine.evaluate(position, market):
            if alert_log.recently_sent(signal, within_hours=dedupe_hours):
                continue
            notifier.notify(signal)
            alert_log.record(signal)
            dispatched.append(signal)
    return dispatched


def build_runtime(settings: dict[str, Any], db_path: Path):
    store = HoldingsStore(db_path)
    prices = make_price_provider(settings.get("price_provider", "yfinance"))
    engine = StrategyEngine(load_strategies(settings.get("strategies") or ["noop"]))
    notifier = Notifier(build_channels(settings))
    alert_log = AlertLog(db_path)
    dedupe_hours = float((settings.get("notify") or {}).get("dedupe_hours") or 24)
    return store, prices, engine, notifier, alert_log, dedupe_hours
