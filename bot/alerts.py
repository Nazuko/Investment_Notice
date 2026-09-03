from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.db import connect
from bot.models import Signal


class AlertLog:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def recently_sent(self, signal: Signal, within_hours: float) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
        with connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT 1 FROM alerts
                WHERE dedupe_key = ? AND sent_at >= ?
                LIMIT 1
                """,
                (signal.dedupe_key(), cutoff.isoformat()),
            ).fetchone()
        return row is not None

    def record(self, signal: Signal) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO alerts (dedupe_key, symbol, side, rule_id, price, reason, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.dedupe_key(),
                    signal.symbol,
                    signal.side,
                    signal.rule_id,
                    signal.price,
                    signal.reason,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
