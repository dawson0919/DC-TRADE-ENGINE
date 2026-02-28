"""SQLAlchemy async ORM models for multi-user SaaS."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Boolean, Integer, Float, Text, DateTime,
    ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    clerk_id = Column(String(255), primary_key=True)
    email = Column(String(320), nullable=False)
    display_name = Column(String(255), default="")
    role = Column(String(20), default="user")  # "user" or "admin"
    is_active = Column(Boolean, default=True)
    max_bots = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    api_credentials = relationship("ApiCredential", back_populates="user", cascade="all,delete-orphan")
    bots = relationship("Bot", back_populates="user", cascade="all,delete-orphan")


class ApiCredential(Base):
    __tablename__ = "api_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), ForeignKey("users.clerk_id", ondelete="CASCADE"), nullable=False)
    exchange = Column(String(50), default="pionex")
    api_key_encrypted = Column(Text, nullable=False)
    api_secret_encrypted = Column(Text, nullable=False)
    label = Column(String(100), default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="api_credentials")

    __table_args__ = (
        Index("idx_api_credentials_user_id", "user_id"),
    )


class Bot(Base):
    __tablename__ = "bots"

    bot_id = Column(String(20), primary_key=True)
    user_id = Column(String(255), ForeignKey("users.clerk_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    strategy = Column(String(100), nullable=False)
    symbol = Column(String(50), nullable=False)
    timeframe = Column(String(10), nullable=False)
    capital = Column(Float, default=10000.0)
    params = Column(JSONB, default=dict)
    paper_mode = Column(Boolean, default=True)
    sl_pct = Column(Float, nullable=True)
    tp_pct = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, default=20.0)
    status = Column(String(20), default="stopped")
    total_pnl = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    last_signal = Column(String(50), default="")
    last_signal_time = Column(String(50), default="")
    error_msg = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="bots")
    trades = relationship("TradeHistory", back_populates="bot", cascade="all,delete-orphan")

    __table_args__ = (
        Index("idx_bots_user_id", "user_id"),
    )


class TradeHistory(Base):
    __tablename__ = "trade_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(String(20), ForeignKey("bots.bot_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(255), nullable=False)
    entry_time = Column(DateTime(timezone=True), nullable=True)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    side = Column(String(10), default="long")
    entry_price = Column(Float, default=0.0)
    exit_price = Column(Float, default=0.0)
    size = Column(Float, default=0.0)
    pnl = Column(Float, default=0.0)
    fees = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    bot = relationship("Bot", back_populates="trades")

    __table_args__ = (
        Index("idx_trade_history_bot_id", "bot_id"),
        Index("idx_trade_history_user_id", "user_id"),
    )
