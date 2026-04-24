from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import enum
from datetime import datetime
from db.database import Base

class SourceType(enum.Enum):
    news = "news"
    social = "social"

class ActionType(enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class TradeStatus(enum.Enum):
    RUNNING = "RUNNING"
    CLOSED_PROFIT = "CLOSED_PROFIT"
    CLOSED_LOSS = "CLOSED_LOSS"
    CANCELED = "CANCELED"

class Sentiment(Base):
    __tablename__ = "sentiments"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    asset = Column(String, index=True)
    source_type = Column(Enum(SourceType))
    sentiment_score = Column(Float)
    summary = Column(String)
    raw_data = Column(JSONB, nullable=True)

class Decision(Base):
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    pair = Column(String, index=True)
    action = Column(Enum(ActionType))
    confidence = Column(Float)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    entry_reason = Column(String)
    llm_context = Column(JSONB, nullable=True)
    
    trades = relationship("Trade", back_populates="decision")

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(Integer, ForeignKey("decisions.id"))
    exchange_order_id = Column(String, nullable=True, index=True)
    pair = Column(String, index=True)
    status = Column(Enum(TradeStatus), default=TradeStatus.RUNNING, index=True)
    entry_price = Column(Float)
    actual_move = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True)
    loss_reason_analysis = Column(String, nullable=True) # From Trade Autopsy
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    
    decision = relationship("Decision", back_populates="trades")
