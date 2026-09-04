from bot.prices import YFinancePriceProvider, make_price_provider
from bot.strategies.registry import load_strategies


def test_make_price_provider_yfinance() -> None:
    assert isinstance(make_price_provider("yfinance"), YFinancePriceProvider)


def test_load_noop_strategy() -> None:
    strategies = load_strategies(["noop"])
    assert strategies[0].id == "noop"
