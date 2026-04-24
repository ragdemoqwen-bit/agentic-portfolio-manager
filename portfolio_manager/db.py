"""SQLAlchemy setup + ORM models for the portfolio store."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # stock | etf | mutual_fund | bond | option
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    avg_cost: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    market: Mapped[str] = mapped_column(String(16), default="USA")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(16))  # buy | sell
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    traded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DailyBrief(Base):
    __tablename__ = "daily_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    body: Mapped[str] = mapped_column(Text)


class CachedNews(Base):
    __tablename__ = "news_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512))
    publisher: Mapped[str | None] = mapped_column(String(128), nullable=True)
    link: Mapped[str] = mapped_column(String(1024))
    published: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def make_engine(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(db_path: Path) -> sessionmaker[Session]:
    return sessionmaker(bind=make_engine(db_path), expire_on_commit=False, future=True)
