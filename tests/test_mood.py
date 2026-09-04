from __future__ import annotations

from bot.mood import classify_index, combine_cycle, compute_mood
from bot.marketdata import INDEX_TWSE, BarStore, DailyBar
from datetime import date, timedelta


def _closes_to_bars(symbol: str, closes: list[float], start: date = date(2025, 1, 2)) -> list[DailyBar]:
    bars = []
    d = start
    for close in closes:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        bars.append(DailyBar(d, close, close, close, close, 0, 0))
        d += timedelta(days=1)
    return bars


def test_classify_strong_on_steady_uptrend() -> None:
    closes = [100 + i * 0.8 for i in range(80)]
    assert classify_index(closes) == "strong"


def test_combine_cycle_from_two_indices() -> None:
    assert combine_cycle("strong", "chop") == "up"
    assert combine_cycle("calm", "gust") == "down"
    assert combine_cycle("strong", "calm") == "watch"
    assert combine_cycle("unknown", "strong") == "unknown"


def test_compute_mood_from_stored_index_bars(tmp_path) -> None:
    store = BarStore(tmp_path / "bot.db")
    up = [20000 + i * 30 for i in range(80)]
    store.upsert_bars(INDEX_TWSE, _closes_to_bars(INDEX_TWSE, up))
    from bot.marketdata import INDEX_TPEX

    store.upsert_bars(INDEX_TPEX, _closes_to_bars(INDEX_TPEX, [200 + i * 0.4 for i in range(80)]))
    payload = compute_mood(store)
    assert payload["cycle"] == "up"
    assert "易漲" in payload["cycle_label"]
    assert payload["twse"]["state"] in {"strong", "chop"}
    assert payload["otc"]["state"] in {"strong", "chop"}


def test_parse_official_index_tables() -> None:
    from bot.marketdata import bars_from_tpex_st41, bars_from_twse_fmtqik

    twse = bars_from_twse_fmtqik(
        {
            "data": [
                ["115/09/01", "0", "0", "0", "46,948.72", "820.25"],
                ["115/09/02", "0", "0", "0", "46,164.72", "-784.00"],
            ]
        }
    )
    assert [b.close for b in twse] == [46948.72, 46164.72]
    assert twse[0].date.isoformat() == "2026-09-01"
    otc = bars_from_tpex_st41(
        {
            "tables": [
                {
                    "data": [
                        ["115/09/01", "1", "2", "3", 410.77, 9.07],
                        ["115/09/03", "1", "2", "3", 395.25, -11.71],
                    ]
                }
            ]
        }
    )
    assert otc[1].close == 395.25
    assert otc[1].date.isoformat() == "2026-09-03"
