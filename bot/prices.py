from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from bot.models import Bar, Quote


class PriceProvider(Protocol):
    def get_quote(self, symbol: str) -> Quote: ...

    def get_history(self, symbol: str, period: str = "6mo") -> list[Bar]: ...


class StubPriceProvider:
    """Fixed quotes for tests and offline development."""

    def __init__(self, prices: dict[str, float] | None = None) -> None:
        self.prices = {k.upper(): v for k, v in (prices or {}).items()}

    def get_quote(self, symbol: str) -> Quote:
        key = symbol.upper()
        if key not in self.prices:
            raise KeyError(f"No stub price for {symbol}")
        return Quote(
            symbol=key,
            price=self.prices[key],
            as_of=datetime.now(timezone.utc),
        )

    def get_history(self, symbol: str, period: str = "6mo") -> list[Bar]:
        quote = self.get_quote(symbol)
        now = datetime.now(timezone.utc)
        return [
            Bar(
                timestamp=now,
                open=quote.price,
                high=quote.price,
                low=quote.price,
                close=quote.price,
            )
        ]


class YFinancePriceProvider:
    def get_quote(self, symbol: str) -> Quote:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        price = getattr(info, "last_price", None)
        if price is None:
            hist = ticker.history(period="1d")
            if hist.empty:
                raise RuntimeError(f"No quote available for {symbol}")
            price = float(hist["Close"].iloc[-1])
        currency = getattr(info, "currency", None)
        return Quote(
            symbol=symbol.upper(),
            price=float(price),
            as_of=datetime.now(timezone.utc),
            currency=str(currency) if currency else None,
        )

    def get_history(self, symbol: str, period: str = "6mo") -> list[Bar]:
        import yfinance as yf

        hist = yf.Ticker(symbol).history(period=period)
        if hist.empty:
            return []
        bars: list[Bar] = []
        for ts, row in hist.iterrows():
            ts_dt = ts.to_pydatetime()
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            bars.append(
                Bar(
                    timestamp=ts_dt,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume") or 0),
                )
            )
        return bars


def make_price_provider(name: str) -> PriceProvider:
    if name == "yfinance":
        return YFinancePriceProvider()
    if name == "stub":
        return StubPriceProvider()
    raise ValueError(f"Unknown price provider: {name}")
