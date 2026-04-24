from datetime import datetime, timezone

from portfolio_manager import analytics
from portfolio_manager.db import Holding
from portfolio_manager.fx import FXRates
from portfolio_manager.portfolio import Position
from portfolio_manager.providers.base import Quote


def _pos(ticker, kind, market, qty, cost, ccy, price):
    h = Holding(
        ticker=ticker, kind=kind, market=market, quantity=qty, avg_cost=cost, currency=ccy
    )
    q = Quote(
        ticker=ticker,
        price=price,
        currency=ccy,
        as_of=datetime.now(timezone.utc),
        source="fake",
    )
    return Position(holding=h, quote=q)


def test_allocation_by_asset_class_sums_to_100():
    positions = [
        _pos("AAPL", "stock", "USA", qty=10, cost=150, ccy="USD", price=200),  # 2000 USD
        _pos("VOO", "etf", "USA", qty=5, cost=400, ccy="USD", price=420),  # 2100 USD
        _pos("BND", "bond", "USA", qty=10_000, cost=100, ccy="USD", price=98),  # 9800 USD
    ]
    fx = FXRates(base="USD")
    rows = analytics.by_asset_class(positions, fx)
    assert sum(r.share_pct for r in rows) == 100.0
    by_label = {r.label: r for r in rows}
    assert "stock" in by_label
    assert "etf" in by_label
    assert "bond" in by_label


def test_allocation_by_market_and_currency_with_fx():
    positions = [
        _pos("AAPL", "stock", "USA", qty=10, cost=150, ccy="USD", price=200),  # 2000 USD
        _pos("D05.SI", "stock", "SG", qty=100, cost=33.5, ccy="SGD", price=40),  # 4000 SGD
    ]
    fx = FXRates(base="USD", rates={"SGD": 0.75})
    rows_market = analytics.by_market(positions, fx)
    assert {r.label for r in rows_market} == {"USA", "SG"}
    usa = next(r for r in rows_market if r.label == "USA")
    sg = next(r for r in rows_market if r.label == "SG")
    assert abs(usa.value - 2000) < 1e-6
    assert abs(sg.value - 3000) < 1e-6  # 4000 SGD * 0.75

    rows_ccy = analytics.by_currency(positions, fx)
    assert {r.label for r in rows_ccy} == {"USD", "SGD"}


def test_allocation_by_ticker_orders_by_value():
    positions = [
        _pos("A", "stock", "USA", qty=1, cost=1, ccy="USD", price=10),
        _pos("B", "stock", "USA", qty=1, cost=1, ccy="USD", price=100),
    ]
    fx = FXRates(base="USD")
    rows = analytics.by_ticker(positions, fx)
    assert [r.label for r in rows] == ["B", "A"]
