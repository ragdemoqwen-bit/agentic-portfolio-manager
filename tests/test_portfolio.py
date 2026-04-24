from datetime import datetime, timezone

import pytest

from portfolio_manager.db import make_session_factory
from portfolio_manager.fx import FXRates
from portfolio_manager.portfolio import (
    add_holding,
    compute_totals,
    list_holdings,
    remove_holding,
    snapshot_positions,
)
from portfolio_manager.providers.base import NewsItem, Quote


class FakeProvider:
    name = "fake"

    def __init__(self, quotes: dict[str, Quote]) -> None:
        self._quotes = quotes

    def get_quote(self, ticker: str):
        return self._quotes.get(ticker)

    def get_news(self, ticker: str, limit: int = 5):
        return [
            NewsItem(
                ticker=ticker,
                title=f"{ticker} headline",
                publisher="TestWire",
                link=f"https://example.com/{ticker}",
                published=datetime.now(timezone.utc),
                summary=None,
            )
        ]

    def get_analyst_snapshot(self, ticker: str):
        return None


@pytest.fixture
def session(tmp_path):
    factory = make_session_factory(tmp_path / "port.db")
    with factory() as s:
        yield s


def test_add_and_list_holding(session):
    add_holding(session, ticker="AAPL", quantity=10, avg_cost=150.0)
    holdings = list_holdings(session)
    assert len(holdings) == 1
    assert holdings[0].ticker == "AAPL"
    assert holdings[0].kind == "stock"
    assert holdings[0].currency == "USD"
    assert holdings[0].market == "USA"


def test_add_auto_detects_option(session):
    add_holding(session, ticker="AAPL240119C00150000", quantity=1, avg_cost=12.5)
    holding = list_holdings(session)[0]
    assert holding.kind == "option"


def test_blended_avg_cost(session):
    add_holding(session, ticker="VOO", quantity=10, avg_cost=400.0)
    add_holding(session, ticker="VOO", quantity=10, avg_cost=440.0)
    holding = list_holdings(session)[0]
    assert holding.quantity == 20
    assert abs(holding.avg_cost - 420.0) < 1e-9


def test_remove_partial(session):
    add_holding(session, ticker="AAPL", quantity=10, avg_cost=150.0)
    remove_holding(session, ticker="AAPL", quantity=3)
    holding = list_holdings(session)[0]
    assert holding.quantity == 7


def test_remove_all(session):
    add_holding(session, ticker="AAPL", quantity=10, avg_cost=150.0)
    remove_holding(session, ticker="AAPL")
    assert list_holdings(session) == []


def test_snapshot_positions_and_totals(session):
    add_holding(session, ticker="AAPL", quantity=10, avg_cost=150.0)
    add_holding(session, ticker="D05.SI", quantity=100, avg_cost=33.5)
    quotes = {
        "AAPL": Quote(
            ticker="AAPL",
            price=200.0,
            currency="USD",
            as_of=datetime.now(timezone.utc),
            source="fake",
            previous_close=195.0,
            day_change_pct=2.56,
        ),
        "D05.SI": Quote(
            ticker="D05.SI",
            price=40.0,
            currency="SGD",
            as_of=datetime.now(timezone.utc),
            source="fake",
            previous_close=39.0,
            day_change_pct=2.56,
        ),
    }
    provider = FakeProvider(quotes)
    positions = snapshot_positions(session, provider)
    assert len(positions) == 2

    # No FX rates supplied — should fall back to leaving amounts in native currency
    # (SGD + USD mixed). Totals should still be the raw sum.
    fx = FXRates(base="USD")
    totals = compute_totals(positions, fx)
    # AAPL: 10 * 200 = 2000 USD; D05.SI: 100 * 40 = 4000 SGD (left as-is)
    assert totals.market_value == 2000 + 4000
    # Cost basis: 10*150 + 100*33.5 = 1500 + 3350 = 4850
    assert totals.cost_basis == 4850.0


def test_snapshot_positions_with_fx(session):
    add_holding(session, ticker="AAPL", quantity=10, avg_cost=150.0)
    add_holding(session, ticker="D05.SI", quantity=100, avg_cost=33.5)
    quotes = {
        "AAPL": Quote(
            ticker="AAPL", price=200.0, currency="USD",
            as_of=datetime.now(timezone.utc), source="fake",
        ),
        "D05.SI": Quote(
            ticker="D05.SI", price=40.0, currency="SGD",
            as_of=datetime.now(timezone.utc), source="fake",
        ),
    }
    provider = FakeProvider(quotes)
    positions = snapshot_positions(session, provider)
    fx = FXRates(base="USD", rates={"SGD": 0.75})  # 1 SGD = 0.75 USD
    totals = compute_totals(positions, fx)
    # AAPL: 2000 USD; D05.SI: 4000 SGD * 0.75 = 3000 USD → total 5000
    assert abs(totals.market_value - 5000.0) < 1e-6
