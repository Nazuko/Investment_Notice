from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from bot.marketdata import DailyBar


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def ema_series(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    seed = sum(values[:period]) / period
    out = [seed]
    for price in values[period:]:
        out.append(price * k + out[-1] * (1 - k))
    return out


def macd_osc(closes: list[float]) -> list[float]:
    if len(closes) < 35:
        return []
    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    offset = len(ema12) - len(ema26)
    macd_line = [a - b for a, b in zip(ema12[offset:], ema26)]
    signal = ema_series(macd_line, 9)
    if not signal:
        return []
    sig_offset = len(macd_line) - len(signal)
    return [m - s for m, s in zip(macd_line[sig_offset:], signal)]


def resample_last(bars: list[DailyBar], key_fn) -> list[DailyBar]:
    groups: dict = defaultdict(list)
    order = []
    for bar in bars:
        key = key_fn(bar.date)
        if key not in groups:
            order.append(key)
        groups[key].append(bar)
    out = []
    for key in order:
        chunk = groups[key]
        first, last = chunk[0], chunk[-1]
        out.append(
            DailyBar(
                date=last.date,
                open=first.open,
                high=max(b.high for b in chunk),
                low=min(b.low for b in chunk),
                close=last.close,
                volume=sum(b.volume for b in chunk),
                turnover=sum(b.turnover for b in chunk),
            )
        )
    return out


def weekly_bars(bars: list[DailyBar]) -> list[DailyBar]:
    return resample_last(bars, lambda d: d.isocalendar()[:2])


def completed_weekly_bars(bars: list[DailyBar]) -> list[DailyBar]:
    weeks = weekly_bars(bars)
    if not weeks or not bars:
        return weeks
    last = bars[-1]
    # 盤後 SOP：週還沒收完（最後一根不是週五）就不要把當週算進週 OSC。
    if last.date.weekday() < 4:
        last_week = last.date.isocalendar()[:2]
        if weeks[-1].date.isocalendar()[:2] == last_week:
            return weeks[:-1]
    return weeks


def monthly_bars(bars: list[DailyBar]) -> list[DailyBar]:
    return resample_last(bars, lambda d: (d.year, d.month))


@dataclass
class Frame:
    bars: list[DailyBar]

    @property
    def closes(self) -> list[float]:
        return [b.close for b in self.bars]

    def last(self) -> DailyBar:
        return self.bars[-1]

    def prev(self) -> DailyBar | None:
        if len(self.bars) < 2:
            return None
        return self.bars[-2]


def pct_change(new: float, old: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / old


def monthly_jump(months: list[DailyBar], lookback: int, threshold: float) -> bool:
    if len(months) < 2:
        return False
    window = months[-(lookback + 1) :]
    for i in range(1, len(window)):
        if pct_change(window[i].close, window[i - 1].close) > threshold:
            return True
    return False


def vcp_month_1_2(months: list[DailyBar]) -> bool:
    # 1月前 >= 2月前 * 1.2, or 2 vs 3, ... through 6 vs 7
    if len(months) < 3:
        return False
    for ago in range(1, 7):
        older_i = -(ago + 1)
        if abs(older_i) > len(months):
            break
        if months[-ago].close >= months[older_i].close * 1.2:
            return True
    return False


def strong_day(frame: Frame) -> tuple[bool, list[str]]:
    reasons = []
    last = frame.last()
    months = monthly_bars(frame.bars)
    ok_vcp = vcp_month_1_2(months)
    if ok_vcp:
        reasons.append("月線曾單月>=20%")
    lots = last.volume / 1000
    ok_vol = lots >= 1000
    if ok_vol:
        reasons.append("量>=1000張")
    ma5 = sma(frame.closes, 5)
    ma20 = sma(frame.closes, 20)
    ma60 = sma(frame.closes, 60)
    ok_ma = ma5 is not None and ma20 is not None and ma60 is not None and ma5 > ma20 and ma5 > ma60
    if ok_ma:
        reasons.append("5MA>20MA且>60MA")
    ok_turn = last.turnover > 100_000_000
    if ok_turn:
        reasons.append("成值>1億")
    osc = macd_osc(frame.closes)
    ok_osc = len(osc) >= 2 and osc[-1] > osc[-2]
    if ok_osc:
        reasons.append("日OSC往上")
    return all([ok_vcp, ok_vol, ok_ma, ok_turn, ok_osc]), reasons


def pullback_day(frame: Frame) -> tuple[bool, list[str]]:
    last = frame.last()
    prev = frame.prev()
    reasons = []
    ok_turn = last.turnover > 100_000_000
    if ok_turn:
        reasons.append("成值>1億")
    weeks = weekly_bars(frame.bars)
    ok_week = False
    if len(weeks) >= 3:
        ok_week = pct_change(weeks[-2].close, weeks[-3].close) >= 0.15
    elif len(weeks) >= 2:
        ok_week = pct_change(weeks[-1].close, weeks[-2].close) >= 0.15
    if ok_week:
        reasons.append("前一週漲幅>=15%")
    ok_down = prev is not None and pct_change(last.close, prev.close) < 0
    if ok_down:
        reasons.append("昨收下跌")
    return ok_turn and ok_week and ok_down, reasons


def week_trend(frame: Frame) -> tuple[bool, list[str]]:
    last = frame.last()
    reasons = []
    ok_turn = last.turnover > 100_000_000
    if ok_turn:
        reasons.append("成值>1億")
    osc = macd_osc([b.close for b in weekly_bars(frame.bars)])
    ok = len(osc) >= 2 and osc[-1] > osc[-2] and osc[-1] > 0 and osc[-2] < 0
    if ok:
        reasons.append("週OSC由負轉正往上")
    return ok_turn and ok, reasons


def strong_week(frame: Frame) -> tuple[bool, list[str]]:
    last = frame.last()
    reasons = []
    week_osc = macd_osc([b.close for b in weekly_bars(frame.bars)])
    day_osc = macd_osc(frame.closes)
    ok_w = len(week_osc) >= 2 and week_osc[-1] > 0 and week_osc[-1] > week_osc[-2]
    ok_d = len(day_osc) >= 2 and day_osc[-1] > 0 and day_osc[-1] > day_osc[-2]
    ma5 = sma(frame.closes, 5)
    ma20 = sma(frame.closes, 20)
    ma60 = sma(frame.closes, 60)
    ok_ma = (
        ma5 is not None
        and ma20 is not None
        and ma60 is not None
        and ma5 > ma20 > ma60
    )
    if len(frame.bars) >= 15:
        avg15 = sum(b.turnover for b in frame.bars[-15:]) / 15
        ok_avg = avg15 > 100_000_000
    else:
        ok_avg = False
    if ok_w:
        reasons.append("週OSC>0且往上")
    if ok_d:
        reasons.append("日OSC>0且往上")
    if ok_ma:
        reasons.append("5>20>60多頭排列")
    if ok_avg:
        reasons.append("15日均成值>1億")
    return all([ok_w, ok_d, ok_ma, ok_avg]), reasons


def week_pullback(frame: Frame) -> tuple[bool, list[str]]:
    last = frame.last()
    reasons = []
    months = monthly_bars(frame.bars)
    ok_jump = monthly_jump(months, lookback=4, threshold=0.30)
    month_osc = macd_osc([b.close for b in months])
    ok_osc = len(month_osc) >= 2 and month_osc[-1] > month_osc[-2]
    ma240 = sma(frame.closes, 240)
    ok_ma = ma240 is not None and last.close > ma240
    ok_turn = last.turnover > 100_000_000
    if ok_jump:
        reasons.append("4個月內單月>30%")
    if ok_osc:
        reasons.append("月OSC往上")
    if ok_ma:
        reasons.append("收盤>240MA")
    if ok_turn:
        reasons.append("成值>1億")
    return all([ok_jump, ok_osc, ok_ma, ok_turn]), reasons


@dataclass
class Check:
    id: str
    label: str
    ok: bool

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "ok": self.ok}


def price_band_or(close: float, ma120: float | None, ma20: float | None) -> tuple[bool, str]:
    """課義「>120MA / <20MA」對齊另一個 App：兩種進場擇一即可。"""
    over_120 = ma120 is not None and close > ma120
    under_20 = ma20 is not None and close < ma20
    if over_120 and under_20:
        return True, "收盤>120MA且<20MA"
    if over_120:
        return True, "收盤>120MA"
    if under_20:
        return True, "收盤<20MA"
    return False, "收盤>120MA或<20MA"


def cheap_buy_checks(frame: Frame) -> list[Check]:
    last = frame.last()
    months = monthly_bars(frame.bars)
    ok_jump = monthly_jump(months, lookback=6, threshold=0.30)
    week_osc = macd_osc([b.close for b in completed_weekly_bars(frame.bars)])
    ok_w = len(week_osc) >= 2 and week_osc[-1] < week_osc[-2]
    ma60_now = sma(frame.closes, 60)
    ma60_prev = sma(frame.closes[:-1], 60) if len(frame.closes) > 60 else None
    ok_ma60 = (
        ma60_now is not None
        and ma60_prev is not None
        and ma60_now > ma60_prev
    )
    ma120 = sma(frame.closes, 120)
    ma20 = sma(frame.closes, 20)
    ok_band, band_label = price_band_or(last.close, ma120, ma20)
    ok_turn = last.turnover > 100_000_000
    return [
        Check("jump", "6個月內單月>30%", ok_jump),
        Check("week_osc", "週OSC往下", ok_w),
        Check("ma60", "60MA仍向上", ok_ma60),
        Check("band", band_label if ok_band else "收盤>120MA或<20MA", ok_band),
        Check("turnover", "成值>1億", ok_turn),
    ]


def _checks_pass(checks: list[Check]) -> bool:
    return all(c.ok for c in checks)


def cheap_buy_session_checks(frame: Frame) -> list[Check]:
    """五條件 AND。若最新一根（常為當日未完成）沒過，改看前一盤後交易日。"""
    current = cheap_buy_checks(frame)
    if _checks_pass(current):
        return current
    if len(frame.bars) < 40:
        return current
    previous = cheap_buy_checks(Frame(frame.bars[:-1]))
    if _checks_pass(previous):
        tagged = [
            Check(c.id, c.label if c.id != "turnover" else "成值>1億（昨收）", c.ok)
            for c in previous
        ]
        return tagged
    return current


def cheap_buy(frame: Frame) -> tuple[bool, list[str]]:
    checks = cheap_buy_session_checks(frame)
    reasons = [c.label for c in checks if c.ok]
    return _checks_pass(checks), reasons


SKILLS = {
    "strong_day": strong_day,
    "pullback_day": pullback_day,
    "week_trend": week_trend,
    "strong_week": strong_week,
    "week_pullback": week_pullback,
    "cheap_buy": cheap_buy,
}


def evaluate_skill(skill_id: str, bars: list[DailyBar]) -> tuple[bool, list[str], list[dict]]:
    fn = SKILLS[skill_id]
    if len(bars) < 30:
        return False, [], []
    frame = Frame(bars)
    if skill_id == "cheap_buy":
        checks = cheap_buy_session_checks(frame)
        payload = [c.as_dict() for c in checks]
        reasons = [c.label for c in checks if c.ok]
        return all(c.ok for c in checks), reasons, payload
    ok, reasons = fn(frame)
    payload = [{"id": r, "label": r, "ok": True} for r in reasons]
    return ok, reasons, payload
