"""
data/models.py

SQLAlchemy ORM models untuk tabel PostgreSQL Dyadix.
Tabel:
  - sentiments : Hasil analisis sentimen LLM (news + social)
  - decisions   : Setiap output Decision LLM
  - trades      : Setiap order yang dieksekusi di Binance Futures
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, Boolean,
    DateTime, Text, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from data.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class SentimentRecord(Base):
    """
    Menyimpan hasil analisis sentimen dari LLM.
    Dibuat setiap kali News + Social dikirim ke LLM untuk dianalisis.
    """
    __tablename__ = "sentiments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_new_uuid)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    asset = Column(String(20), default="CRYPTO", index=True)  # e.g. BTC, CRYPTO (general)
    source_type = Column(String(20), default="news_social")   # 'news', 'social', 'news_social'

    # Hasil analisis LLM
    overall_sentiment = Column(String(30))      # e.g. "Strong Bullish", "Neutral"
    sentiment_score = Column(Float)             # 0-100
    confidence = Column(Float)                  # 0.0 - 1.0
    dominant_narrative = Column(Text)
    news_impact = Column(Text)
    social_mood = Column(Text)
    trading_implication = Column(Text)
    key_insights = Column(JSONB)                # Array of strings

    # Data mentah / summary
    summary = Column(Text)                      # Ringkasan teks
    raw_data = Column(JSONB)                    # Seluruh output LLM mentah

    def __repr__(self):
        return f"<Sentiment {self.overall_sentiment} score={self.sentiment_score} @ {self.timestamp}>"


class DecisionRecord(Base):
    """
    Menyimpan setiap output dari Decision LLM.
    Dibuat sebelum order dieksekusi.
    """
    __tablename__ = "decisions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_new_uuid)
    pair = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Output Decision LLM
    decision = Column(String(10), nullable=False)        # BUY / SELL / HOLD / WAIT
    confidence = Column(Float)
    bias = Column(String(30))
    entry_zone = Column(String(80))
    entry_price_calc = Column(Float)                     # Midpoint dari entry_zone
    stop_loss = Column(Float)
    target = Column(Float)
    risk_reward = Column(String(20))
    execution_type = Column(String(10))                  # MARKET / LIMIT
    recommended_timeframe = Column(String(10))
    reason = Column(Text)

    # Context lengkap yang dikirim ke LLM (untuk audit & autopsy)
    llm_context = Column(JSONB)

    # Relasi ke trades (1 decision bisa menghasilkan 1 trade)
    trade = relationship("TradeRecord", back_populates="decision", uselist=False)

    def __repr__(self):
        return f"<Decision {self.pair} {self.decision} @ {self.timestamp}>"


class TradeRecord(Base):
    """
    Menyimpan setiap order yang dieksekusi di Binance Futures.
    Status berubah seiring lifecycle trade.
    """
    __tablename__ = "trades"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_new_uuid)
    decision_id = Column(UUID(as_uuid=False), ForeignKey("decisions.id"), nullable=True)
    pair = Column(String(20), nullable=False, index=True)
    exchange_order_id = Column(String(50), unique=True, index=True)

    # Detail posisi
    side = Column(String(10), nullable=False)             # BUY / SELL
    status = Column(String(20), nullable=False, default="RUNNING", index=True)
    # Status: RUNNING | CLOSED_TP | CLOSED_SL | CANCELED | PENDING

    # Harga & quantity
    entry_price = Column(Float)                           # Harga aktual dari Binance
    entry_price_planned = Column(Float)                   # Midpoint yang direncanakan
    stop_loss_price = Column(Float)
    target_price = Column(Float)
    quantity = Column(Float)
    leverage = Column(Integer)

    # Hasil trade
    exit_price = Column(Float)
    realized_pnl = Column(Float)                          # PnL dalam USDT
    exit_reason = Column(String(30))                      # "Hit SL" | "Hit TP" | "Manual"

    # Autopsy (diisi setelah SL)
    autopsy_analysis = Column(Text)                       # Analisis LLM lengkap
    autopsy_lesson = Column(Text)                         # [LESSON] yang diekstrak

    # Timestamps
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    # Relasi
    decision = relationship("DecisionRecord", back_populates="trade")

    def __repr__(self):
        return f"<Trade {self.pair} {self.side} {self.status}>"

    @property
    def duration_minutes(self) -> float | None:
        """Durasi trade dalam menit."""
        if self.opened_at and self.closed_at:
            delta = self.closed_at - self.opened_at
            return round(delta.total_seconds() / 60, 1)
        return None

    @property
    def pnl_str(self) -> str:
        """Format PnL untuk notifikasi."""
        if self.realized_pnl is None:
            return "N/A"
        sign = "+" if self.realized_pnl >= 0 else ""
        return f"{sign}${self.realized_pnl:.2f}"
