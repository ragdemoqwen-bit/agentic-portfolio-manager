"""Core portfolio business logic sitting on top of the SQLite store."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from . import assets
from .agent.daily_brief import HoldingSnapshot
from .db import Holding, Transaction
from .fx import FXRates
from .markets import classify_ticker, is_option_symbol
from .providers.base import MarketDataProvider, Quote

log = logging.getLogger(__name__)


@dataclass
class Position:
    holding: Holding
    quote: Quote | None

    @property
    def market_value_native(self) -> float | None:
        if self.quote is None:
            return None
        handler = assets.resolve(self.holding.kind)
        return handler.market_value(
            assets.base.ValuationContext(
                quantity=self.holding.quantity,
                price=self.quote.price,
                currency=self.quote.currency,
            )
        )

    @property
    def cost_basis_native(self) -> float:
        handler = assets.resolve(self.holding.kind)
        return handler.market_value(
            assets.base.ValuationContext(
                quantity=self.holding.quantity,
                price=self.holding.avg_cost,
                currency=self.holding.currency,
            )
        )

    @property
    def pnl_native(self) -> float | None:
        mv = self.market_value_native
        if mv is None:
            return None
        return mv - self.cost_basis_native


def _infer_kind(ticker: str, explicit_kind: str | None) -> str:
    if explicit_kind:
        return explicit_kind
    if is_option_symbol(ticker):
        return assets.AssetKind.OPTION.value
    return assets.AssetKind.STOCK.value


def add_holding(
    session: Session,
    ticker: str,
    quantity: float,
    avg_cost: float,
    kind: str | None = None,
    notes: str | None = None,
) -> Holding:
    kind = _infer_kind(ticker, kind)
    info = classify_ticker(ticker)
    existing = session.query(Holding).filter_by(ticker=ticker).one_or_none()
    if existing is not None:
        # Blended cost basis when adding to an existing lot.
        total_qty = existing.quantity + quantity
        if total_qty == 0:
            existing.avg_cost = 0.0
        else:
            existing.avg_cost = (existing.quantity * existing.avg_cost + quantity * avg_cost) / total_qty
        existing.quantity = total_qty
        if notes:
            existing.notes = notes
        session.add(
            Transaction(
                ticker=ticker,
                action="buy",
                quantity=quantity,
                price=avg_cost,
                currency=info.currency,
            )
        )
        session.commit()
        return existing
    holding = Holding(
        ticker=ticker,
        kind=kind,
        quantity=quantity,
        avg_cost=avg_cost,
        currency=info.currency,
        market=info.market.value,
        notes=notes,
    )
    session.add(holding)
    session.add(
        Transaction(
            ticker=ticker,
            action="buy",
            quantity=quantity,
            price=avg_cost,
            currency=info.currency,
        )
    )
    session.commit()
    return holding


def remove_holding(session: Session, ticker: str, quantity: float | None = None) -> None:
    holding = session.query(Holding).filter_by(ticker=ticker).one_or_none()
    if holding is None:
        return
    if quantity is None or quantity >= holding.quantity:
        session.add(
            Transaction(
                ticker=ticker,
                action="sell",
                quantity=holding.quantity,
                price=holding.avg_cost,
                currency=holding.currency,
            )
        )
        session.delete(holding)
    else:
        holding.quantity -= quantity
        session.add(
            Transaction(
                ticker=ticker,
                action="sell",
                quantity=quantity,
                price=holding.avg_cost,
                currency=holding.currency,
            )
        )
    session.commit()


def list_holdings(session: Session) -> list[Holding]:
    return list(session.query(Holding).order_by(Holding.ticker).all())


def snapshot_positions(
    session: Session,
    provider: MarketDataProvider,
) -> list[Position]:
    out: list[Position] = []
    for h in list_holdings(session):
        q = provider.get_quote(h.ticker)
        out.append(Position(holding=h, quote=q))
    return out


@dataclass
class PortfolioTotals:
    base_ccy: str
    market_value: float
    cost_basis: float

    @property
    def pnl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def pnl_pct(self) -> float:
        return 0.0 if self.cost_basis == 0 else (self.pnl / self.cost_basis) * 100.0


def compute_totals(positions: list[Position], fx: FXRates) -> PortfolioTotals:
    mv = 0.0
    cb = 0.0
    for p in positions:
        cb += fx.convert(p.cost_basis_native, p.holding.currency)
        v = p.market_value_native
        if v is not None:
            mv += fx.convert(v, p.quote.currency if p.quote else p.holding.currency)
        else:
            mv += fx.convert(p.cost_basis_native, p.holding.currency)
    return PortfolioTotals(base_ccy=fx.base, market_value=mv, cost_basis=cb)


def positions_to_snapshots(positions: list[Position]) -> list[HoldingSnapshot]:
    return [
        HoldingSnapshot(
            ticker=p.holding.ticker,
            kind=p.holding.kind,
            quantity=p.holding.quantity,
            avg_cost=p.holding.avg_cost,
            currency=p.holding.currency,
            price=p.quote.price if p.quote else None,
            day_change_pct=p.quote.day_change_pct if p.quote else None,
            name=p.quote.name if p.quote else None,
        )
        for p in positions
    ]
