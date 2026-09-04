from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import csv
import io
import json
import urllib.request

from bot.db import connect
from bot.symbols import load_catalog

TWSE_DAY_ALL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=open_data"
TPEX_DAY_ALL = (
    "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/"
    "stk_wn1430_result.php?l=zh-tw&o=csv"
)
MIN_TURNOVER = 100_000_000  # 1 億
HISTORY_CALENDAR_DAYS = 400


@dataclass(frozen=True)
class DailyBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float  # shares
    turnover: float  # TWD


def _http_get(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "InvestmentNotice/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _num(text: str) -> float:
    cleaned = (text or "").replace(",", "").replace("--", "").replace("—", "").strip()
    if not cleaned or cleaned in {"nan", "NaN", "N/A"}:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def is_etf(code: str) -> bool:
    return code.startswith("00")


def yahoo_for(code: str, market: str) -> str:
    suffix = ".TW" if market == "twse" else ".TWO"
    return f"{code}{suffix}"


def parse_twse_csv(raw: bytes) -> tuple[date | None, list[tuple[str, DailyBar]]]:
    text = raw.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        return None, []
    header = [c.strip() for c in rows[0]]
    as_of = None
    out: list[tuple[str, DailyBar]] = []
    for row in rows[1:]:
        if len(row) < 9:
            continue
        mapping = dict(zip(header, row)) if header else {}
        code = (mapping.get("證券代號") or row[1]).strip()
        if not code or is_etf(code):
            continue
        date_s = (mapping.get("日期") or row[0]).strip()
        bar_date = _parse_roc_or_iso(date_s)
        if bar_date is None:
            continue
        as_of = bar_date
        close = _num(mapping.get("收盤價") or row[8])
        volume = _num(mapping.get("成交股數") or row[3])
        turnover = _num(mapping.get("成交金額") or row[4])
        if close <= 0:
            continue
        if turnover <= 0 and volume > 0:
            turnover = close * volume
        bar = DailyBar(
            date=bar_date,
            open=_num(mapping.get("開盤價") or row[5]) or close,
            high=_num(mapping.get("最高價") or row[6]) or close,
            low=_num(mapping.get("最低價") or row[7]) or close,
            close=close,
            volume=volume,
            turnover=turnover,
        )
        out.append((yahoo_for(code, "twse"), bar))
    return as_of, out


def parse_tpex_csv(raw: bytes) -> tuple[date | None, list[tuple[str, DailyBar]]]:
    text = raw.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    as_of = None
    out: list[tuple[str, DailyBar]] = []
    for row in rows:
        if len(row) < 8:
            continue
        code = row[0].strip().strip('"')
        if not code.isdigit() or is_etf(code):
            continue
        close = _num(row[2] if len(row) > 2 else "")
        # Common TPEX csv: 代號,名稱,收盤,漲跌,開盤,最高,最低,均價,成交股數,成交金額,...
        if close <= 0 and len(row) > 7:
            close = _num(row[7])
        volume = _num(row[8]) if len(row) > 8 else 0.0
        turnover = _num(row[9]) if len(row) > 9 else 0.0
        if close <= 0:
            continue
        if turnover <= 0 and volume > 0:
            turnover = close * volume
        bar_date = date.today()
        as_of = bar_date
        bar = DailyBar(
            date=bar_date,
            open=_num(row[4]) or close,
            high=_num(row[5]) or close,
            low=_num(row[6]) or close,
            close=close,
            volume=volume,
            turnover=turnover,
        )
        out.append((yahoo_for(code, "tpex"), bar))
    return as_of, out


def _parse_roc_or_iso(text: str) -> date | None:
    text = text.strip().replace("=", "").replace('"', "")
    if not text:
        return None
    if text.isdigit() and len(text) == 7:
        year = int(text[:3]) + 1911
        month = int(text[3:5])
        day = int(text[5:7])
        return date(year, month, day)
    if text.isdigit() and len(text) == 8:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    if "/" in text:
        parts = text.split("/")
        if len(parts) == 3:
            y, m, d = (int(p) for p in parts)
            if y < 1911:
                y += 1911
            return date(y, m, d)
    if "-" in text:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None


class BarStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def upsert_bars(self, symbol: str, bars: list[DailyBar]) -> None:
        with connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO daily_bars (symbol, d, open, high, low, close, volume, turnover)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, d) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume, turnover=excluded.turnover
                """,
                [
                    (
                        symbol,
                        bar.date.isoformat(),
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.volume,
                        bar.turnover,
                    )
                    for bar in bars
                ],
            )
            conn.commit()

    def history(self, symbol: str) -> list[DailyBar]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT d, open, high, low, close, volume, turnover
                FROM daily_bars WHERE symbol = ? ORDER BY d
                """,
                (symbol,),
            ).fetchall()
        return [
            DailyBar(
                date=date.fromisoformat(row["d"]),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                turnover=row["turnover"],
            )
            for row in rows
        ]

    def latest_date(self) -> date | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT MAX(d) AS d FROM daily_bars").fetchone()
        if not row or not row["d"]:
            return None
        return date.fromisoformat(row["d"])

    def save_screen(self, persona: str, skill: str, as_of: date, payload: list[dict]) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO screen_runs (persona, skill, as_of, payload, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(persona, skill) DO UPDATE SET
                    as_of=excluded.as_of, payload=excluded.payload, updated_at=excluded.updated_at
                """,
                (
                    persona,
                    skill,
                    as_of.isoformat(),
                    json.dumps(payload, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

    def load_screen(self, persona: str, skill: str) -> tuple[date | None, list[dict]]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT as_of, payload FROM screen_runs WHERE persona = ? AND skill = ?",
                (persona, skill),
            ).fetchone()
        if not row:
            return None, []
        return date.fromisoformat(row["as_of"]), json.loads(row["payload"])


def fetch_session_quotes() -> tuple[date | None, dict[str, DailyBar]]:
    quotes: dict[str, DailyBar] = {}
    as_of = None
    try:
        twse_as_of, twse_rows = parse_twse_csv(_http_get(TWSE_DAY_ALL))
        as_of = twse_as_of or as_of
        for symbol, bar in twse_rows:
            quotes[symbol] = bar
    except Exception:
        pass
    try:
        tpex_as_of, tpex_rows = parse_tpex_csv(_http_get(TPEX_DAY_ALL))
        if as_of is None:
            as_of = tpex_as_of
        for symbol, bar in tpex_rows:
            # Align TPEX date to TWSE session date when available.
            if as_of and bar.date != as_of:
                bar = DailyBar(
                    date=as_of,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    turnover=bar.turnover,
                )
            quotes[symbol] = bar
    except Exception:
        pass
    return as_of, quotes


def fetch_history_yfinance_batch(symbols: list[str]) -> dict[str, list[DailyBar]]:
    import yfinance as yf

    if not symbols:
        return {}
    data = yf.download(
        tickers=symbols,
        period="18mo",
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False,
    )
    out: dict[str, list[DailyBar]] = {s: [] for s in symbols}
    if data is None or data.empty:
        return out

    def bars_from_frame(frame) -> list[DailyBar]:
        rows: list[DailyBar] = []
        if frame is None or getattr(frame, "empty", True):
            return rows
        if "Close" not in frame.columns:
            return rows
        for ts, row in frame.iterrows():
            close = float(row["Close"])
            if close != close:  # NaN
                continue
            volume = float(row["Volume"]) if "Volume" in frame.columns else 0.0
            if volume != volume:
                volume = 0.0
            rows.append(
                DailyBar(
                    date=ts.to_pydatetime().date(),
                    open=float(row["Open"]) if row["Open"] == row["Open"] else close,
                    high=float(row["High"]) if row["High"] == row["High"] else close,
                    low=float(row["Low"]) if row["Low"] == row["Low"] else close,
                    close=close,
                    volume=volume,
                    turnover=close * volume,
                )
            )
        return rows

    if len(symbols) == 1:
        out[symbols[0]] = bars_from_frame(data)
        return out
    for symbol in symbols:
        try:
            frame = data[symbol]
        except Exception:
            continue
        out[symbol] = bars_from_frame(frame)
    return out


def universe_over_turnover(quotes: dict[str, DailyBar], minimum: float = MIN_TURNOVER) -> list[str]:
    allowed = {item.yahoo for item in load_catalog() if not is_etf(item.code)}
    picked = [
        symbol
        for symbol, bar in quotes.items()
        if bar.turnover >= minimum and symbol in allowed
    ]
    picked.sort(key=lambda s: quotes[s].turnover, reverse=True)
    return picked


def refresh_market(store: BarStore, *, fill_history: bool = True) -> date | None:
    as_of, quotes = fetch_session_quotes()
    if not quotes:
        raise RuntimeError("無法下載上市／上櫃盤後報價")
    for symbol, bar in quotes.items():
        store.upsert_bars(symbol, [bar])
    session = as_of or store.latest_date()
    if fill_history:
        symbols = universe_over_turnover(quotes)[:80]
        missing = []
        cutoff = (session or date.today()) - timedelta(days=HISTORY_CALENDAR_DAYS)
        for symbol in symbols:
            existing = store.history(symbol)
            if existing and existing[0].date <= cutoff and len(existing) >= 120:
                continue
            missing.append(symbol)
        batch = fetch_history_yfinance_batch(missing)
        for symbol, hist in batch.items():
            if hist:
                store.upsert_bars(symbol, hist)
    return session
