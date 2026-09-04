from __future__ import annotations

from pathlib import Path

import yaml

from bot.config import holdings_yaml_path
from bot.db import connect
from bot.models import Position, WatchItem


class HoldingsStore:
    def __init__(self, db_path: Path, yaml_path: Path | None = None) -> None:
        self.db_path = db_path
        self.yaml_path = yaml_path or holdings_yaml_path()

    def list_positions(self) -> list[Position]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT symbol, qty, avg_cost, note FROM positions ORDER BY symbol"
            ).fetchall()
        return [
            Position(
                symbol=row["symbol"],
                qty=row["qty"],
                avg_cost=row["avg_cost"],
                note=row["note"] or "",
            )
            for row in rows
        ]

    def list_watchlist(self) -> list[WatchItem]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT symbol, note FROM watchlist ORDER BY symbol"
            ).fetchall()
        return [WatchItem(symbol=row["symbol"], note=row["note"] or "") for row in rows]

    def upsert_position(
        self, symbol: str, qty: float, avg_cost: float, note: str = ""
    ) -> Position:
        symbol = symbol.strip().upper()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO positions (symbol, qty, avg_cost, note)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    qty = excluded.qty,
                    avg_cost = excluded.avg_cost,
                    note = excluded.note
                """,
                (symbol, qty, avg_cost, note),
            )
            conn.commit()
        return Position(symbol=symbol, qty=qty, avg_cost=avg_cost, note=note)

    def remove_position(self, symbol: str) -> bool:
        symbol = symbol.strip().upper()
        with connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
            conn.commit()
            return cur.rowcount > 0

    def upsert_watch(self, symbol: str, note: str = "") -> WatchItem:
        symbol = symbol.strip().upper()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO watchlist (symbol, note) VALUES (?, ?)
                ON CONFLICT(symbol) DO UPDATE SET note = excluded.note
                """,
                (symbol, note),
            )
            conn.commit()
        return WatchItem(symbol=symbol, note=note)

    def remove_watch(self, symbol: str) -> bool:
        symbol = symbol.strip().upper()
        with connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
            conn.commit()
            return cur.rowcount > 0

    def import_yaml(self, path: Path | None = None) -> None:
        yaml_path = path or self.yaml_path
        with yaml_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        for item in data.get("positions") or []:
            self.upsert_position(
                symbol=item["symbol"],
                qty=float(item["qty"]),
                avg_cost=float(item["avg_cost"]),
                note=str(item.get("note") or ""),
            )
        for item in data.get("watchlist") or []:
            self.upsert_watch(
                symbol=item["symbol"],
                note=str(item.get("note") or ""),
            )

    def export_yaml(self, path: Path | None = None) -> None:
        yaml_path = path or self.yaml_path
        payload = {
            "positions": [
                {
                    "symbol": p.symbol,
                    "qty": p.qty,
                    "avg_cost": p.avg_cost,
                    "note": p.note,
                }
                for p in self.list_positions()
            ],
            "watchlist": [
                {"symbol": w.symbol, "note": w.note} for w in self.list_watchlist()
            ],
        }
        with yaml_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)
