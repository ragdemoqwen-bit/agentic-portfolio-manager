from portfolio_manager import assets
from portfolio_manager.assets.base import ValuationContext
from portfolio_manager.assets.option import parse_occ


def test_stock_market_value():
    h = assets.resolve("stock")
    mv = h.market_value(ValuationContext(quantity=10, price=100, currency="USD"))
    assert mv == 1000


def test_option_multiplier_is_100():
    h = assets.resolve("option")
    mv = h.market_value(ValuationContext(quantity=1, price=2.5, currency="USD"))
    assert mv == 250


def test_bond_multiplier_is_0_01():
    h = assets.resolve("bond")
    # $10,000 face value at clean price 98.5 → $9,850 market value
    mv = h.market_value(ValuationContext(quantity=10_000, price=98.5, currency="USD"))
    assert abs(mv - 9850.0) < 1e-6


def test_etf_and_mutual_fund_are_linear():
    for kind in ("etf", "mutual_fund"):
        h = assets.resolve(kind)
        assert h.market_value(ValuationContext(quantity=3, price=400, currency="USD")) == 1200


def test_resolve_unknown_kind_raises():
    try:
        assets.resolve("crypto")
    except ValueError as exc:
        assert "crypto" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown kind")


def test_parse_occ_symbol():
    p = parse_occ("AAPL240119C00150000")
    assert p is not None
    assert p.underlying == "AAPL"
    assert p.expiry == "2024-01-19"
    assert p.right == "call"
    assert p.strike == 150.0


def test_parse_occ_symbol_rejects_plain_ticker():
    assert parse_occ("AAPL") is None
