from portfolio_manager.markets import Market, classify_ticker, is_option_symbol


def test_us_ticker_defaults_to_usa_usd():
    info = classify_ticker("AAPL")
    assert info.market == Market.USA
    assert info.currency == "USD"


def test_singapore_suffix():
    info = classify_ticker("D05.SI")
    assert info.market == Market.SINGAPORE
    assert info.currency == "SGD"


def test_india_nse_suffix():
    info = classify_ticker("RELIANCE.NS")
    assert info.market == Market.INDIA_NSE
    assert info.currency == "INR"


def test_india_bse_suffix():
    info = classify_ticker("500325.BO")
    assert info.market == Market.INDIA_BSE
    assert info.currency == "INR"


def test_option_symbol_detection():
    # AAPL 2024-01-19 $150 call
    assert is_option_symbol("AAPL240119C00150000")
    assert not is_option_symbol("AAPL")
    assert not is_option_symbol("D05.SI")
