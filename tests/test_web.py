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
        price_provider=StubPriceProvider({"2330.TW": 900.0, "0050.TW": 150.0}),
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
        data={"position_symbol": "2330.TW", "qty": "1000", "avg_cost": "580", "position_note": ""},
        follow_redirects=True,
    )
    assert added.status_code == 200
    assert "台積電".encode("utf-8") in added.data
    assert b"2330.TW" in added.data
    quotes = client.get("/api/quotes")
    assert quotes.status_code == 200
    assert quotes.get_json()["2330.TW"] == 900.0


def test_reject_non_tw_symbol(tmp_path: Path) -> None:
    client = _client(tmp_path)
    page = client.post(
        "/positions",
        data={"position_symbol": "AAPL", "qty": "1", "avg_cost": "10"},
        follow_redirects=True,
    )
    assert "請從清單選擇台股".encode("utf-8") in page.data
    assert "尚無庫存".encode("utf-8") in page.data


def test_symbol_search_api(tmp_path: Path) -> None:
    client = _client(tmp_path)
    found = client.get("/api/symbols?q=台積")
    assert found.status_code == 200
    payload = found.get_json()
    assert any(item["yahoo"] == "2330.TW" for item in payload)
    assert any("台積電" in item["label"] for item in payload)


def test_watchlist_and_run(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/watchlist", data={"watch_symbol": "0050.TW", "watch_note": "watch"})
    page = client.get("/")
    assert "元大台灣50".encode("utf-8") in page.data
    ran = client.post("/run", follow_redirects=True)
    assert ran.status_code == 200
    assert "沒有買賣訊號".encode("utf-8") in ran.data


def test_delete_position(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/positions", data={"position_symbol": "2330.TW", "qty": "1", "avg_cost": "10"})
    deleted = client.post("/positions/2330.TW/delete", follow_redirects=True)
    assert "已移除庫存 台積電".encode("utf-8") in deleted.data
    assert "尚無庫存".encode("utf-8") in deleted.data


def test_personality_pages_and_tabs(tmp_path: Path) -> None:
    from datetime import date

    from bot.marketdata import BarStore

    client = _client(tmp_path)
    home = client.get("/")
    assert "打工型".encode("utf-8") in home.data
    assert "成長型".encode("utf-8") in home.data

    db = tmp_path / "bot.db"
    store = BarStore(db)
    store.save_screen(
        "worker",
        "strong_day",
        date(2026, 9, 3),
        [
            {
                "symbol": "2330.TW",
                "name": "台積電",
                "close": 900.0,
                "turnover": 20_000_000_000,
                "volume_lots": 20000,
                "reasons": ["成值>1億"],
            }
        ],
    )
    page = client.get("/select/worker")
    assert page.status_code == 200
    assert "強勢日風箏".encode("utf-8") in page.data
    assert "拉回日風箏".encode("utf-8") in page.data
    assert "台積電".encode("utf-8") in page.data
    other = client.get("/select/worker?skill=pullback_day")
    assert "這個分頁目前沒有通過條件".encode("utf-8") in other.data
    soon = client.get("/select/growth/soon")
    assert soon.status_code == 200
    assert "講義還沒放到".encode("utf-8") in soon.data
