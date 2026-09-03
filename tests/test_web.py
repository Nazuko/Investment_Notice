from __future__ import annotations

from pathlib import Path

from bot.prices import StubPriceProvider
from bot.web import create_app


def _client(tmp_path: Path):
    db = tmp_path / "bot.db"
    yaml_path = tmp_path / "holdings.yaml"
    yaml_path.write_text("positions: []\nwatchlist: []\n", encoding="utf-8")
    app = create_app(
        settings={
            "price_provider": "stub",
            "strategies": ["noop"],
            "notify": {"channels": ["console"], "dedupe_hours": 24},
        },
        db_path=db,
        yaml_path=yaml_path,
        price_provider=StubPriceProvider({"2330.TW": 900.0, "AAPL": 180.0}),
        seed_yaml=False,
    )
    app.config["TESTING"] = True
    return app.test_client()


def test_dashboard_and_add_position(tmp_path: Path) -> None:
    client = _client(tmp_path)
    home = client.get("/")
    assert home.status_code == 200
    assert "庫存與購入價".encode("utf-8") in home.data

    added = client.post(
        "/positions",
        data={"position_symbol": "2330.TW", "qty": "1000", "avg_cost": "580", "position_note": "台積電"},
        follow_redirects=True,
    )
    assert added.status_code == 200
    assert b"2330.TW" in added.data
    assert "台積電".encode("utf-8") in added.data
    quotes = client.get("/api/quotes")
    assert quotes.status_code == 200
    assert quotes.get_json()["2330.TW"] == 900.0


def test_watchlist_and_run(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/watchlist", data={"watch_symbol": "AAPL", "watch_note": "watch"})
    page = client.get("/")
    assert b"AAPL" in page.data
    ran = client.post("/run", follow_redirects=True)
    assert ran.status_code == 200
    assert "沒有買賣訊號".encode("utf-8") in ran.data


def test_delete_position(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/positions", data={"position_symbol": "AAPL", "qty": "1", "avg_cost": "10"})
    deleted = client.post("/positions/AAPL/delete", follow_redirects=True)
    assert "已移除庫存 AAPL".encode("utf-8") in deleted.data
    assert "尚無庫存".encode("utf-8") in deleted.data
