"""Opportunity model and builder — the core output of the scanner."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone


class Direction(str, enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class InstrumentType(str, enum.Enum):
    STOCK = "Stock"
    CALL_OPTION = "Call Option"
    PUT_OPTION = "Put Option"


@dataclass
class OptionDetail:
    strike: float
    expiration: str
    dte: int
    premium: float | None = None
    iv: float | None = None
    iv_rank: float | None = None
    delta: float | None = None
    theta: float | None = None
    vega: float | None = None
    open_interest: int | None = None
    volume: int | None = None
    is_leap: bool = False


@dataclass
class Opportunity:
    ticker: str
    score: float
    direction: Direction
    instrument: InstrumentType
    strategy: str
    timeframe: str

    entry_price: float
    target_price: float
    stop_loss: float
    risk_reward: float

    risk_per_unit: float
    suggested_qty: int
    max_loss: float
    portfolio_risk_pct: float

    technical_summary: str
    sentiment_summary: str
    catalysts: str

    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    option_detail: OptionDetail | None = None

    # Wheel strategy fields
    wheel_candidate: bool = False
    wheel_notes: str = ""


def build_opportunity(
    ticker: str,
    current_price: float,
    direction: Direction,
    instrument: InstrumentType,
    strategy: str,
    timeframe: str,
    target_pct: float,
    stop_pct: float,
    technical_summary: str,
    sentiment_summary: str,
    catalysts: str,
    score: float,
    portfolio_size: float = 100_000.0,
    max_risk_pct: float = 5.0,
    option_detail: OptionDetail | None = None,
    wheel_candidate: bool = False,
    wheel_notes: str = "",
) -> Opportunity:
    if instrument == InstrumentType.STOCK:
        if direction == Direction.LONG:
            target_price = current_price * (1 + target_pct / 100)
            stop_loss = current_price * (1 - stop_pct / 100)
        else:
            target_price = current_price * (1 - target_pct / 100)
            stop_loss = current_price * (1 + stop_pct / 100)
        risk_per_unit = abs(current_price - stop_loss)
        reward_per_unit = abs(target_price - current_price)
        entry_price = current_price
    else:
        premium = option_detail.premium if option_detail and option_detail.premium else 0.0
        entry_price = premium
        risk_per_unit = premium * (stop_pct / 100)
        reward_per_unit = premium * (target_pct / 100)
        target_price = premium * (1 + target_pct / 100)
        stop_loss = premium * (1 - stop_pct / 100)

    risk_reward = reward_per_unit / risk_per_unit if risk_per_unit > 0 else 0.0

    max_loss_budget = portfolio_size * (max_risk_pct / 100)
    if instrument == InstrumentType.STOCK:
        suggested_qty = max(1, int(max_loss_budget / risk_per_unit)) if risk_per_unit > 0 else 0
        max_loss = suggested_qty * risk_per_unit
    else:
        contract_risk = risk_per_unit * 100
        suggested_qty = max(1, int(max_loss_budget / contract_risk)) if contract_risk > 0 else 0
        max_loss = suggested_qty * contract_risk

    portfolio_risk_pct = (max_loss / portfolio_size * 100) if portfolio_size > 0 else 0.0

    return Opportunity(
        ticker=ticker,
        score=score,
        direction=direction,
        instrument=instrument,
        strategy=strategy,
        timeframe=timeframe,
        entry_price=round(entry_price, 2),
        target_price=round(target_price, 2),
        stop_loss=round(stop_loss, 2),
        risk_reward=round(risk_reward, 2),
        risk_per_unit=round(risk_per_unit, 2),
        suggested_qty=suggested_qty,
        max_loss=round(max_loss, 2),
        portfolio_risk_pct=round(portfolio_risk_pct, 2),
        technical_summary=technical_summary,
        sentiment_summary=sentiment_summary,
        catalysts=catalysts,
        option_detail=option_detail,
        wheel_candidate=wheel_candidate,
        wheel_notes=wheel_notes,
    )
