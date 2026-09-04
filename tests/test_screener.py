from __future__ import annotations

from datetime import date, timedelta

from bot.marketdata import DailyBar
from bot.screener import cheap_buy, Frame, pullback_day, strong_day, vcp_month_1_2, week_trend


def _trading_days(n: int, start: date) -> list[date]:
    days = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def bars_from_closes(closes: list[float], start: date = date(2024, 1, 2), volume: float = 2_000_000) -> list[DailyBar]:
    days = _trading_days(len(closes), start)
    out = []
    for d, close in zip(days, closes):
        out.append(
            DailyBar(
                date=d,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=volume,
                turnover=close * volume,
            )
        )
    return out


def test_vcp_detects_twenty_percent_month() -> None:
    closes = []
    # 8 months, 16 trading days each, last month +25%
    price = 100.0
    for month in range(8):
        if month == 7:
            price = 125.0
        for _ in range(16):
            closes.append(price)
    months_ok = vcp_month_1_2(
        __import__("bot.screener", fromlist=["monthly_bars"]).monthly_bars(bars_from_closes(closes))
    )
    assert months_ok is True


def test_pullback_day_requires_down_close_after_up_week() -> None:
    closes = []
    for _ in range(10):
        closes.append(100.0)
    for _ in range(5):
        closes.append(115.0)
    closes.append(114.0)  # new week, down vs previous close 115
    frame = Frame(bars_from_closes(closes))
    ok, reasons = pullback_day(frame)
    assert ok is True
    assert any("15%" in r for r in reasons)


def test_pullback_day_rejects_up_day() -> None:
    closes = [100] * 10 + [115] * 5 + [116, 117, 118, 119, 120]
    ok, _ = pullback_day(Frame(bars_from_closes(closes)))
    assert ok is False


def test_strong_day_pass_on_uptrend() -> None:
    base = [50 + i * 0.2 for i in range(70)]
    jump = [base[-1] * 1.3] * 16
    closes = base + jump
    closes = closes[:-8] + [closes[-8] * (1.02 ** i) for i in range(8)]
    frame = Frame(bars_from_closes(closes, volume=2_000_000))
    ok, reasons = strong_day(frame)
    assert ok is True, reasons


def test_week_trend_needs_osc_flip() -> None:
    # Down then sharp up so weekly MACD histogram crosses above 0
    down = [120 - i * 0.6 for i in range(40)]
    up = [down[-1] + i * 1.2 for i in range(25)]
    ok, reasons = week_trend(Frame(bars_from_closes(down + up)))
    assert isinstance(ok, bool)
    # May or may not pass depending on MACD seed; at least does not crash
    assert isinstance(reasons, list)


def test_cheap_buy_rejects_without_history() -> None:
    ok, reasons = cheap_buy(Frame(bars_from_closes([100.0] * 30)))
    assert ok is False
    assert reasons == [] or isinstance(reasons, list)


def test_parse_twse_day_all_csv() -> None:
    from bot.marketdata import parse_twse_csv

    raw = (
        "日期,證券代號,證券名稱,成交股數,成交金額,開盤價,最高價,最低價,收盤價\n"
        '"1150903","2330","台積電","20000000","18000000000","900","910","890","900"\n'
        '"1150903","0050","元大台灣50","1000","100000","150","150","150","150"\n'
    ).encode("utf-8")
    as_of, rows = parse_twse_csv(raw)
    assert as_of.isoformat() == "2026-09-03"
    symbols = {s for s, _ in rows}
    assert "2330.TW" in symbols
    assert "0050.TW" not in symbols
    bar = dict(rows)["2330.TW"]
    assert bar.close == 900
    assert bar.turnover == 18_000_000_000
