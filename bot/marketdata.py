from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import csv
import io
import json
import urllib.request

from bot.db import connect
from bot.symbols import load_catalog, lookup

TWSE_DAY_ALL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=open_data"
TPEX_DAY_ALL = (
    "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/"
    "stk_wn1430_result.php?l=zh-tw&o=csv"
)
MIN_TURNOVER = 100_000_000  # 1 億
HISTORY_CALENDAR_DAYS = 400
YF_CHUNK = 60

# 對齊使用者另一個 App 的廉價收購清單，補 K 時一定要抓到。
PRIORITY_CODES = ["6446", "2395", "3605", "5351", "7795", "6409", "1714", "2466"]
INDEX_TWSE = "INDEX.TWSE"
INDEX_TPEX = "INDEX.TPEX"
INDEX_YAHOO = {INDEX_TWSE: "^TWII", INDEX_TPEX: "^TWOII"}
INDEX_YAHOO_FALLBACK = {INDEX_TPEX: "006201.TW"}


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
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; InvestmentNotice/0.1)",
            "Accept": "application/json,text/csv,*/*",
        },
    )
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


def _decode_table(raw: bytes) -> str:
    for enc in ("utf-8-sig", "big5", "cp950"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _tpex_colmap(header: list[str]) -> dict[str, int]:
    aliases = {
        "code": ("代號", "證券代號", "股票代號"),
        "close": ("收盤", "收盤價"),
        "open": ("開盤", "開盤價"),
        "high": ("最高", "最高價"),
        "low": ("最低", "最低價"),
        "volume": ("成交股數", "成交量"),
        "turnover": ("成交金額", "成交值"),
    }
    found: dict[str, int] = {}
    cleaned = [c.strip().strip('"') for c in header]
    for key, names in aliases.items():
        for i, col in enumerate(cleaned):
            if any(name in col for name in names):
                found[key] = i
                break
    return found


def parse_tpex_csv(raw: bytes, session: date | None = None) -> tuple[date | None, list[tuple[str, DailyBar]]]:
    text = _decode_table(raw)
    rows = list(csv.reader(io.StringIO(text)))
    as_of = session
    header_i = None
    colmap: dict[str, int] = {}
    for i, row in enumerate(rows):
        if not row:
            continue
        joined = ",".join(row)
        for cell in row[:3]:
            parsed = _parse_roc_or_iso(cell)
            if parsed:
                as_of = parsed
        if "年" in joined and "月" in joined and "日" in joined:
            digits = "".join(ch if ch.isdigit() or ch in "/-" else " " for ch in joined)
            for token in digits.split():
                parsed = _parse_roc_or_iso(token)
                if parsed:
                    as_of = parsed
        if any("代號" in c for c in row):
            header_i = i
            colmap = _tpex_colmap(row)
            break
    out: list[tuple[str, DailyBar]] = []
    start = (header_i + 1) if header_i is not None else 0
    bar_date = as_of or date.today()
    for row in rows[start:]:
        if len(row) < 3:
            continue
        code = row[colmap["code"]].strip().strip('"') if "code" in colmap else row[0].strip().strip('"')
        if not code.isdigit() or is_etf(code):
            continue
        close_i = colmap.get("close", 2)
        close = _num(row[close_i] if len(row) > close_i else "")
        if close <= 0:
            continue
        open_i = colmap.get("open", 4)
        high_i = colmap.get("high", 5)
        low_i = colmap.get("low", 6)
        vol_i = colmap.get("volume", 8)
        turn_i = colmap.get("turnover", 9)
        volume = _num(row[vol_i] if len(row) > vol_i else "")
        turnover = _num(row[turn_i] if len(row) > turn_i else "")
        if turnover <= 0 and volume > 0:
            turnover = close * volume
        bar = DailyBar(
            date=bar_date,
            open=_num(row[open_i] if len(row) > open_i else "") or close,
            high=_num(row[high_i] if len(row) > high_i else "") or close,
            low=_num(row[low_i] if len(row) > low_i else "") or close,
            close=close,
            volume=volume,
            turnover=turnover,
        )
        out.append((yahoo_for(code, "tpex"), bar))
    return as_of or bar_date if out else as_of, out


def parse_tpex_json(raw: bytes, session: date | None = None) -> tuple[date | None, list[tuple[str, DailyBar]]]:
    try:
        payload = json.loads(_decode_table(raw))
    except json.JSONDecodeError:
        return session, []
    as_of = session
    for key in ("reportDate", "date", "Date"):
        if payload.get(key):
            parsed = _parse_roc_or_iso(str(payload[key]))
            if parsed:
                as_of = parsed
    tables = payload.get("aaData") or payload.get("tables") or []
    if isinstance(tables, dict):
        tables = tables.get("aaData") or []
    out: list[tuple[str, DailyBar]] = []
    bar_date = as_of or date.today()
    for row in tables:
        if not row or len(row) < 3:
            continue
        code = str(row[0]).strip()
        if not code.isdigit() or is_etf(code):
            continue
        close = _num(str(row[2]))
        if close <= 0:
            continue
        volume = _num(str(row[8])) if len(row) > 8 else 0.0
        turnover = _num(str(row[9])) if len(row) > 9 else 0.0
        if turnover <= 0 and volume > 0:
            turnover = close * volume
        bar = DailyBar(
            date=bar_date,
            open=_num(str(row[4])) if len(row) > 4 else close,
            high=_num(str(row[5])) if len(row) > 5 else close,
            low=_num(str(row[6])) if len(row) > 6 else close,
            close=close,
            volume=volume,
            turnover=turnover,
        )
        out.append((yahoo_for(code, "tpex"), bar))
    return as_of or bar_date if out else as_of, out


def _parse_roc_or_iso(text: str) -> date | None:
    text = text.strip().replace("=", "").replace('"', "")
    if not text:
        return None
    if "年" in text and "月" in text:
        digits = "".join(ch if ch.isdigit() else " " for ch in text).split()
        if len(digits) >= 3:
            y, m, d = int(digits[0]), int(digits[1]), int(digits[2])
            if y < 1911:
                y += 1911
            try:
                return date(y, m, d)
            except ValueError:
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


def _roc_slash(d: date) -> str:
    return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"


def _tpex_urls(as_of: date | None) -> list[str]:
    urls = []
    if as_of:
        roc = _roc_slash(as_of)
        west = as_of.isoformat().replace("-", "/")
        urls.extend(
            [
                (
                    "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/"
                    f"stk_wn1430_result.php?l=zh-tw&d={roc}&se=AL&o=csv"
                ),
                (
                    "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/"
                    f"stk_wn1430_result.php?l=zh-tw&d={roc}&se=AL&o=json"
                ),
                f"https://www.tpex.org.tw/www/zh-tw/afterTrading/otcQuotes?date={west}&id=&response=csv",
            ]
        )
    urls.append(TPEX_DAY_ALL)
    return urls


def fetch_tpex_session(as_of: date | None) -> tuple[date | None, list[tuple[str, DailyBar]]]:
    last_as_of = as_of
    for url in _tpex_urls(as_of):
        try:
            raw = _http_get(url)
        except Exception:
            continue
        if "json" in url or raw[:1] in (b"{", b"["):
            got_as_of, rows = parse_tpex_json(raw, as_of)
        else:
            got_as_of, rows = parse_tpex_csv(raw, as_of)
        last_as_of = got_as_of or last_as_of
        if rows:
            return last_as_of, rows
    return last_as_of, []


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
    tpex_as_of, tpex_rows = fetch_tpex_session(as_of)
    if as_of is None:
        as_of = tpex_as_of
    for symbol, bar in tpex_rows:
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


def priority_yahoo_symbols() -> list[str]:
    out: list[str] = []
    for code in PRIORITY_CODES:
        item = lookup(code)
        out.append(item.yahoo if item else f"{code}.TW")
    return out


def history_universe(quotes: dict[str, DailyBar]) -> list[str]:
    symbols = universe_over_turnover(quotes)
    seen = set(symbols)
    for extra in priority_yahoo_symbols():
        if extra not in seen:
            symbols.append(extra)
            seen.add(extra)
    return symbols


def _fill_missing_history(store: BarStore, symbols: list[str], session: date | None) -> None:
    cutoff = (session or date.today()) - timedelta(days=HISTORY_CALENDAR_DAYS)
    missing: list[str] = []
    for symbol in symbols:
        existing = store.history(symbol)
        if existing and existing[0].date <= cutoff and len(existing) >= 120:
            continue
        missing.append(symbol)
    for i in range(0, len(missing), YF_CHUNK):
        chunk = missing[i : i + YF_CHUNK]
        batch = fetch_history_yfinance_batch(chunk)
        for symbol, hist in batch.items():
            if hist:
                store.upsert_bars(symbol, hist)
        still = [s for s in chunk if not batch.get(s)]
        if still:
            retry = fetch_history_yfinance_batch(still)
            for symbol, hist in retry.items():
                if hist:
                    store.upsert_bars(symbol, hist)


def _month_starts(months: int = 18) -> list[date]:
    today = date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(months):
        out.append(date(y, m, 1))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def bars_from_twse_fmtqik(payload: dict) -> list[DailyBar]:
    bars: list[DailyBar] = []
    for row in payload.get("data") or []:
        if len(row) < 5:
            continue
        bar_date = _parse_roc_or_iso(str(row[0]))
        close = _num(str(row[4]))
        if bar_date is None or close <= 0:
            continue
        bars.append(DailyBar(bar_date, close, close, close, close, 0.0, 0.0))
    return bars


def bars_from_tpex_st41(payload: dict) -> list[DailyBar]:
    bars: list[DailyBar] = []
    tables = payload.get("tables") or []
    rows = []
    if tables and isinstance(tables[0], dict):
        rows = tables[0].get("data") or []
    for row in rows:
        if len(row) < 5:
            continue
        bar_date = _parse_roc_or_iso(str(row[0]))
        close = _num(str(row[4]))
        if bar_date is None or close <= 0:
            continue
        bars.append(DailyBar(bar_date, close, close, close, close, 0.0, 0.0))
    return bars


def fetch_twse_index_history() -> list[DailyBar]:
    bars: list[DailyBar] = []
    for start in _month_starts():
        url = (
            "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK"
            f"?response=json&date={start.strftime('%Y%m%d')}"
        )
        try:
            payload = json.loads(_http_get(url).decode("utf-8-sig"))
        except Exception:
            continue
        bars.extend(bars_from_twse_fmtqik(payload))
    bars.sort(key=lambda b: b.date)
    return bars


def fetch_tpex_index_history() -> list[DailyBar]:
    bars: list[DailyBar] = []
    for start in _month_starts():
        roc = f"{start.year - 1911}/{start.month:02d}"
        url = (
            "https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_index/"
            f"st41_result.php?l=zh-tw&d={roc}&o=json"
        )
        try:
            payload = json.loads(_decode_table(_http_get(url)))
        except Exception:
            continue
        bars.extend(bars_from_tpex_st41(payload))
    bars.sort(key=lambda b: b.date)
    return bars


def refresh_indices(store: BarStore, session: date | None) -> None:
    twse = fetch_twse_index_history()
    if not twse:
        twse = fetch_history_yfinance_batch(["^TWII"]).get("^TWII") or []
    if twse:
        store.upsert_bars(INDEX_TWSE, twse)
    otc = fetch_tpex_index_history()
    if otc:
        store.upsert_bars(INDEX_TPEX, otc)


def refresh_market(
    store: BarStore,
    *,
    fill_history: bool = True,
    fill_indices: bool = True,
) -> date | None:
    as_of, quotes = fetch_session_quotes()
    if not quotes:
        raise RuntimeError("無法下載上市／上櫃盤後報價")
    for symbol, bar in quotes.items():
        store.upsert_bars(symbol, [bar])
    session = as_of or store.latest_date()
    if fill_history:
        _fill_missing_history(store, history_universe(quotes), session)
    if fill_indices:
        refresh_indices(store, session)
    return session
