"""
data/database.py

Inisialisasi koneksi PostgreSQL menggunakan SQLAlchemy.
Dibaca dari environment variables via .env.
"""

import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def get_database_url() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "dyadix")
    user = os.getenv("POSTGRES_USER", "dyadix")
    password = os.getenv("POSTGRES_PASSWORD", "")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def get_engine():
    url = get_database_url()
    return create_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True,  # Verifikasi koneksi sebelum digunakan
        echo=False,
    )


def get_session_factory():
    engine = get_engine()
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db():
    """
    Buat semua tabel yang belum ada di database.
    Dipanggil saat bot pertama kali start.
    """
    from data.models import SentimentRecord, DecisionRecord, TradeRecord  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized.")


# Session factory singleton
SessionFactory = get_session_factory()
