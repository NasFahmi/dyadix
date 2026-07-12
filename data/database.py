"""
data/database.py

Inisialisasi koneksi PostgreSQL menggunakan SQLAlchemy.
Dibaca dari environment variables via .env.
"""

import os
import logging
import urllib.parse
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
    safe_password = urllib.parse.quote_plus(password)
    return f"postgresql+psycopg2://{user}:{safe_password}@{host}:{port}/{db}"


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
    from sqlalchemy import text

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    # Tambahkan kolom is_break_even secara dinamis jika belum ada
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE trades ADD COLUMN IF NOT EXISTS is_break_even BOOLEAN DEFAULT FALSE"))
            conn.commit()
            logger.info("Checked and updated 'trades' schema for 'is_break_even' column.")
    except Exception as e:
        logger.warning(f"Failed to check/update trades schema (non-fatal): {e}")

    logger.info("Database tables initialized.")


# Session factory singleton
SessionFactory = get_session_factory()
