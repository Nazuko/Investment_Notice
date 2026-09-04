from __future__ import annotations

from pathlib import Path

from bot.holdings import HoldingsStore


def test_import_yaml_and_list(tmp_path: Path) -> None:
    yaml_path = tmp_path / "holdings.yaml"
    yaml_path.write_text(
        """
positions:
  - symbol: 2330.TW
    qty: 1000
    avg_cost: 580
    note: TSMC
watchlist:
  - symbol: AAPL
    note: watch
""",
        encoding="utf-8",
    )
    store = HoldingsStore(tmp_path / "bot.db")
    store.import_yaml(yaml_path)
    positions = store.list_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "2330.TW"
    assert positions[0].qty == 1000
    assert positions[0].avg_cost == 580
    watch = store.list_watchlist()
    assert watch[0].symbol == "AAPL"


def test_upsert_and_remove(tmp_path: Path) -> None:
    store = HoldingsStore(tmp_path / "bot.db")
    store.upsert_position("aapl", 10, 150.5, "apple")
    listed = store.list_positions()
    assert listed[0].symbol == "AAPL"
    assert listed[0].avg_cost == 150.5
    assert store.remove_position("AAPL") is True
    assert store.list_positions() == []
    assert store.remove_position("AAPL") is False


def test_export_yaml_roundtrip(tmp_path: Path) -> None:
    store = HoldingsStore(tmp_path / "bot.db")
    store.upsert_position("2330.TW", 1, 1.0)
    out = tmp_path / "out.yaml"
    store.export_yaml(out)
    other = HoldingsStore(tmp_path / "other.db")
    other.import_yaml(out)
    assert other.list_positions()[0].symbol == "2330.TW"
