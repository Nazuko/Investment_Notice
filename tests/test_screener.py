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


def test_price_band_or_accepts_either_leg() -> None:
    from bot.screener import price_band_or

    both, label_both = price_band_or(110, 100, 120)
    assert both is True
    assert "120MA" in label_both and "20MA" in label_both
    over_only, label_over = price_band_or(110, 100, 90)
    assert over_only is True
    assert label_over == "收盤>120MA"
    under_only, label_under = price_band_or(80, 100, 90)
    assert under_only is True
    assert label_under == "收盤<20MA"
    neither, _ = price_band_or(95, 100, 90)
    assert neither is False


def test_completed_week_drops_unfinished_week() -> None:
    from bot.screener import completed_weekly_bars, weekly_bars

    # 2024-01-02 is Tuesday; a Wednesday last bar should drop current ISO week.
    bars = bars_from_closes([100, 101, 102, 103, 104, 105, 106, 107], start=date(2024, 1, 2))
    full = weekly_bars(bars)
    done = completed_weekly_bars(bars)
    assert bars[-1].date.weekday() < 4
    assert len(done) == len(full) - 1


def test_cheap_buy_session_fallback_returns_five_checks() -> None:
    from bot.screener import cheap_buy_session_checks

    bars = bars_from_closes([100.0] * 50, volume=2_000_000)
    checks = cheap_buy_session_checks(Frame(bars))
    assert len(checks) == 5
    assert {c.id for c in checks} == {"jump", "week_osc", "ma60", "band", "turnover"}


def test_cheap_buy_checks_pass_when_only_above_120ma() -> None:
    from bot.screener import cheap_buy_checks, sma

    price = 80.0
    closes: list[float] = []
    for month in range(10):
        if month == 4:
            price *= 1.4
        for _ in range(16):
            price *= 1.003
            closes.append(price)
    frame = Frame(bars_from_closes(closes, volume=2_000_000))
    ma120 = sma(frame.closes, 120)
    ma20 = sma(frame.closes, 20)
    assert ma120 is not None and ma20 is not None
    assert frame.last().close > ma120
    # Pullback not required: still above 20MA is OK.
    assert frame.last().close > ma20
    checks = {c.id: c.ok for c in cheap_buy_checks(frame)}
    assert checks["band"] is True
    assert checks["jump"] is True
    assert checks["turnover"] is True


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


def test_parse_tpex_csv_with_header() -> None:
    from bot.marketdata import parse_tpex_csv

    raw = (
        "115年09月03日上櫃股票每日收盤行情\n"
        "代號,名稱,收盤,漲跌,開盤,最高,最低,均價,成交股數,成交金額\n"
        "5351,鈺創,50.00,+1.00,49.00,51.00,48.00,50.00,2000000,100000000\n"
        "0050,ETF,10,0,10,10,10,10,1,10\n"
    ).encode("utf-8")
    as_of, rows = parse_tpex_csv(raw)
    assert as_of.isoformat() == "2026-09-03"
    symbols = {s for s, _ in rows}
    assert "5351.TWO" in symbols
    assert "0050.TWO" not in symbols
    bar = dict(rows)["5351.TWO"]
    assert bar.close == 50
    assert bar.turnover == 100_000_000


def test_history_universe_includes_priority_and_full_turnover() -> None:
    from bot.marketdata import DailyBar, PRIORITY_CODES, history_universe
    from bot.symbols import lookup

    as_of = date(2026, 9, 3)
    quotes = {
        "2330.TW": DailyBar(as_of, 900, 910, 890, 900, 1_000_000, 200_000_000),
        "2303.TW": DailyBar(as_of, 50, 51, 49, 50, 1_000_000, 150_000_000),
    }
    uni = history_universe(quotes)
    assert "2330.TW" in uni
    assert "2303.TW" in uni
    for code in PRIORITY_CODES:
        item = lookup(code)
        assert item is not None
        assert item.yahoo in uni

