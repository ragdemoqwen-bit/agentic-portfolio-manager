"""SQLite persistence for scan results — stores opportunities for later review."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..db import Base
from .opportunities import Direction, InstrumentType, Opportunity

log = logging.getLogger(__name__)


class ScanResult(Base):
    __tablename__ = "scan_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(8))
    instrument: Mapped[str] = mapped_column(String(32))
    strategy: Mapped[str] = mapped_column(String(256))
    timeframe: Mapped[str] = mapped_column(String(32))
    entry_price: Mapped[float] = mapped_column(Float)
    target_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    risk_reward: Mapped[float] = mapped_column(Float)
    risk_per_unit: Mapped[float] = mapped_column(Float)
    suggested_qty: Mapped[int] = mapped_column(Integer)
    max_loss: Mapped[float] = mapped_column(Float)
    portfolio_risk_pct: Mapped[float] = mapped_column(Float)
    technical_summary: Mapped[str] = mapped_column(Text)
    sentiment_summary: Mapped[str] = mapped_column(Text)
    catalysts: Mapped[str] = mapped_column(Text)
    option_detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    wheel_candidate: Mapped[int] = mapped_column(Integer, default=0)
    wheel_notes: Mapped[str] = mapped_column(Text, default="")
    scanned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


def save_opportunities(session: Session, opps: list[Opportunity]) -> int:
    count = 0
    for opp in opps:
        od_json = None
        if opp.option_detail:
            od_json = json.dumps({
                "strike": opp.option_detail.strike,
                "expiration": opp.option_detail.expiration,
                "dte": opp.option_detail.dte,
                "premium": opp.option_detail.premium,
                "iv": opp.option_detail.iv,
                "iv_rank": opp.option_detail.iv_rank,
                "delta": opp.option_detail.delta,
                "theta": opp.option_detail.theta,
                "vega": opp.option_detail.vega,
                "is_leap": opp.option_detail.is_leap,
            })
        session.add(ScanResult(
            ticker=opp.ticker,
            score=opp.score,
            direction=opp.direction.value,
            instrument=opp.instrument.value,
            strategy=opp.strategy,
            timeframe=opp.timeframe,
            entry_price=opp.entry_price,
            target_price=opp.target_price,
            stop_loss=opp.stop_loss,
            risk_reward=opp.risk_reward,
            risk_per_unit=opp.risk_per_unit,
            suggested_qty=opp.suggested_qty,
            max_loss=opp.max_loss,
            portfolio_risk_pct=opp.portfolio_risk_pct,
            technical_summary=opp.technical_summary,
            sentiment_summary=opp.sentiment_summary,
            catalysts=opp.catalysts,
            option_detail_json=od_json,
            wheel_candidate=1 if opp.wheel_candidate else 0,
            wheel_notes=opp.wheel_notes,
            scanned_at=opp.scanned_at,
        ))
        count += 1
    session.commit()
    return count


def load_opportunities(
    session: Session,
    ticker: str | None = None,
    min_score: float = 0.0,
    limit: int = 50,
) -> list[Opportunity]:
    q = session.query(ScanResult).order_by(ScanResult.scanned_at.desc())
    if ticker:
        q = q.filter(ScanResult.ticker == ticker.upper())
    if min_score > 0:
        q = q.filter(ScanResult.score >= min_score)
    q = q.limit(limit)

    results: list[Opportunity] = []
    for row in q:
        from .opportunities import OptionDetail

        od = None
        if row.option_detail_json:
            try:
                od_data = json.loads(row.option_detail_json)
                od = OptionDetail(**od_data)
            except Exception:
                pass
        results.append(Opportunity(
            ticker=row.ticker,
            score=row.score,
            direction=Direction(row.direction),
            instrument=InstrumentType(row.instrument),
            strategy=row.strategy,
            timeframe=row.timeframe,
            entry_price=row.entry_price,
            target_price=row.target_price,
            stop_loss=row.stop_loss,
            risk_reward=row.risk_reward,
            risk_per_unit=row.risk_per_unit,
            suggested_qty=row.suggested_qty,
            max_loss=row.max_loss,
            portfolio_risk_pct=row.portfolio_risk_pct,
            technical_summary=row.technical_summary,
            sentiment_summary=row.sentiment_summary,
            catalysts=row.catalysts,
            scanned_at=row.scanned_at,
            option_detail=od,
            wheel_candidate=bool(row.wheel_candidate),
            wheel_notes=row.wheel_notes,
        ))
    return results
