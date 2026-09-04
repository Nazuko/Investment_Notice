from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from bot.marketdata import INDEX_TPEX, INDEX_TWSE, BarStore, DailyBar
from bot.screener import macd_osc, sma


STATE_LABELS = {
    "strong": "強風",
    "chop": "亂流",
    "calm": "無風",
    "gust": "陣風",
    "unknown": "資料不足",
}

CYCLE_HINTS = {
    "up": "易漲循環：打工／上班族勝率較高；老闆型等待時間較短。",
    "down": "易跌循環：短線勝率偏低；老闆型較適合分批撿便宜（風度越差、分批越多）。",
    "watch": "交界／區間：兩個指數方向不一致，先觀察是否同向。",
    "unknown": "尚未更新指數，請按「更新風度」。",
}


@dataclass
class IndexMood:
    symbol: str
    name: str
    close: float | None
    prev_close: float | None
    sma20: float | None
    osc: float | None
    osc_prev: float | None
    state: str
    as_of: date | None

    @property
    def change_pct(self) -> float | None:
        if self.close is None or self.prev_close in (None, 0):
            return None
        return (self.close - self.prev_close) / self.prev_close

    @property
    def state_label(self) -> str:
        return STATE_LABELS.get(self.state, self.state)

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "close": self.close,
            "prev_close": self.prev_close,
            "change_pct": self.change_pct,
            "sma20": self.sma20,
            "osc": self.osc,
            "osc_prev": self.osc_prev,
            "state": self.state,
            "state_label": self.state_label,
            "as_of": self.as_of.isoformat() if self.as_of else None,
        }


def classify_index(closes: list[float]) -> str:
    if len(closes) < 22:
        return "unknown"
    ma20 = sma(closes, 20)
    osc = macd_osc(closes)
    if ma20 is None or len(osc) < 2:
        return "unknown"
    above = closes[-1] > ma20
    osc_up = osc[-1] > osc[-2]
    if above and osc_up:
        return "strong"
    if above and not osc_up:
        return "chop"
    if not above and not osc_up:
        return "calm"
    return "gust"


def combine_cycle(twse_state: str, otc_state: str) -> str:
    up = {"strong", "chop"}
    down = {"calm", "gust"}
    if twse_state == "unknown" or otc_state == "unknown":
        return "unknown"
    if twse_state in up and otc_state in up:
        return "up"
    if twse_state in down and otc_state in down:
        return "down"
    return "watch"


def _from_bars(symbol: str, name: str, bars: list[DailyBar]) -> IndexMood:
    if not bars:
        return IndexMood(symbol, name, None, None, None, None, None, "unknown", None)
    closes = [b.close for b in bars]
    osc = macd_osc(closes)
    prev = bars[-2].close if len(bars) > 1 else None
    return IndexMood(
        symbol=symbol,
        name=name,
        close=bars[-1].close,
        prev_close=prev,
        sma20=sma(closes, 20),
        osc=osc[-1] if osc else None,
        osc_prev=osc[-2] if len(osc) > 1 else None,
        state=classify_index(closes),
        as_of=bars[-1].date,
    )


def compute_mood(store: BarStore) -> dict[str, Any]:
    twse = _from_bars(INDEX_TWSE, "加權指數", store.history(INDEX_TWSE))
    otc = _from_bars(INDEX_TPEX, "櫃買指數", store.history(INDEX_TPEX))
    cycle = combine_cycle(twse.state, otc.state)
    cycle_labels = {
        "up": "易漲循環（強風－亂流）",
        "down": "易跌循環（無風－陣風）",
        "watch": "待觀察（交界／區間）",
        "unknown": "風度尚未更新",
    }
    as_of = twse.as_of or otc.as_of
    return {
        "as_of": as_of.isoformat() if as_of else None,
        "cycle": cycle,
        "cycle_label": cycle_labels[cycle],
        "hint": CYCLE_HINTS[cycle],
        "twse": twse.as_dict(),
        "otc": otc.as_dict(),
    }


def save_mood(store: BarStore, payload: dict[str, Any]) -> None:
    as_of = date.fromisoformat(payload["as_of"]) if payload.get("as_of") else date.today()
    store.save_screen("_mood", "market", as_of, [payload])


def load_mood(store: BarStore) -> dict[str, Any] | None:
    as_of, rows = store.load_screen("_mood", "market")
    if not rows:
        if as_of:
            return compute_mood(store)
        computed = compute_mood(store)
        if computed.get("cycle") != "unknown":
            return computed
        return None
    return rows[0]


def refresh_mood(store: BarStore, *, fill_history: bool = False) -> dict[str, Any]:
    from bot.marketdata import refresh_market

    refresh_market(store, fill_history=fill_history, fill_indices=True)
    payload = compute_mood(store)
    save_mood(store, payload)
    return payload
