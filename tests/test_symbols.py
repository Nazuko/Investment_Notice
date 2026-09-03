from bot.symbols import lookup, name_for, search


def test_search_code_and_name() -> None:
    by_code = search("2330")
    assert any(item.yahoo == "2330.TW" and item.name == "台積電" for item in by_code)
    by_name = search("台積")
    assert any(item.code == "2330" for item in by_name)


def test_otc_uses_two_suffix() -> None:
    item = lookup("6488")
    assert item is not None
    assert item.yahoo == "6488.TWO"
    assert item.market == "tpex"
    assert name_for("6488.TWO") == item.name


def test_etf_listed() -> None:
    item = lookup("0050.TW")
    assert item is not None
    assert item.name == "元大台灣50"


def test_unknown_symbol() -> None:
    assert lookup("AAPL") is None
    assert name_for("AAPL", fallback="備註") == "備註"
