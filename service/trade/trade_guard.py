"""
service/trade/trade_guard.py

Mengecek apakah ada trade yang sedang RUNNING untuk suatu pair.
Digunakan oleh LoopScheduler sebelum signal detection.
"""

import logging
from data.database import SessionFactory
from data.models import TradeRecord

logger = logging.getLogger(__name__)


class TradeGuard:
    """
    Guard untuk mencegah pembukaan posisi baru jika
    sudah ada trade yang sedang berjalan (RUNNING) untuk pair yang sama.
    """

    @staticmethod
    def has_running_trade(pair: str) -> bool:
        """
        Query database: apakah ada trade RUNNING untuk pair ini?

        Args:
            pair: Contoh "BTCUSDT"

        Returns:
            True jika ada trade running, False jika tidak.
        """
        try:
            with SessionFactory() as session:
                trade = (
                    session.query(TradeRecord)
                    .filter(
                        TradeRecord.pair == pair,
                        TradeRecord.status == "RUNNING",
                    )
                    .first()
                )
                return trade is not None
        except Exception as e:
            logger.error(f"TradeGuard DB error for {pair}: {e}")
            # Jika DB error, lebih aman asumsikan ADA trade (skip)
            return True

    @staticmethod
    def is_daily_limit_reached() -> tuple[bool, str]:
        """
        Mengecek apakah hari ini sudah mencapai limit (max trades atau total max SL).
        Return: (True, "reason") jika limit tercapai, (False, "") jika aman.
        """
        try:
            from config.settings import get_config
            from datetime import datetime
            
            config = get_config().get("risk_management", {})
            max_daily_trades = config.get("max_daily_trades", 0)
            max_daily_sl = config.get("max_daily_sl", 0)
            
            if max_daily_trades <= 0 and max_daily_sl <= 0:
                return False, ""
                
            today = datetime.utcnow().date()
            start_of_day = datetime(today.year, today.month, today.day)
            
            with SessionFactory() as session:
                trades_today = (
                    session.query(TradeRecord)
                    .filter(TradeRecord.opened_at >= start_of_day)
                    .order_by(TradeRecord.opened_at.asc())
                    .all()
                )
                
                # Cek max daily trades
                if max_daily_trades > 0 and len(trades_today) >= max_daily_trades:
                    return True, f"Max daily trades reached ({max_daily_trades})"
                    
                # Cek max daily SL (Total SL hari ini)
                if max_daily_sl > 0:
                    total_sl = sum(1 for trade in trades_today if trade.status == "CLOSED_SL")
                    if total_sl >= max_daily_sl:
                        return True, f"Max daily SL reached ({max_daily_sl})"
                        
            return False, ""
        except Exception as e:
            logger.error(f"TradeGuard limit check error: {e}")
            return False, ""

    @staticmethod
    def get_running_trade(pair: str):
        """
        Ambil record trade RUNNING untuk pair ini (jika ada).

        Returns:
            TradeRecord atau None.
        """
        try:
            with SessionFactory() as session:
                return (
                    session.query(TradeRecord)
                    .filter(
                        TradeRecord.pair == pair,
                        TradeRecord.status == "RUNNING",
                    )
                    .first()
                )
        except Exception as e:
            logger.error(f"TradeGuard get_running error for {pair}: {e}")
            return None

    @staticmethod
    def get_all_running_trades() -> list:
        """
        Ambil semua trade yang sedang RUNNING atau PENDING.
        Digunakan oleh TradeMonitor untuk monitoring.

        Returns:
            List of TradeRecord.
        """
        try:
            with SessionFactory() as session:
                return (
                    session.query(TradeRecord)
                    .filter(TradeRecord.status.in_(["RUNNING", "PENDING"]))
                    .all()
                )
        except Exception as e:
            logger.error(f"TradeGuard get_all_running error: {e}")
            return []

    @staticmethod
    def get_closed_trades(limit: int = 10) -> list:
        """
        Ambil semua trade yang sudah closed (CLOSED_TP, CLOSED_SL, CANCELED).
        Digunakan oleh /trades command untuk menampilkan histori.

        Args:
            limit: Jumlah trades terakhir yang ditampilkan (default 10)

        Returns:
            List of TradeRecord.
        """
        try:
            with SessionFactory() as session:
                return (
                    session.query(TradeRecord)
                    .filter(TradeRecord.status.in_(["CLOSED_TP", "CLOSED_SL", "CANCELED"]))
                    .order_by(TradeRecord.closed_at.desc())
                    .limit(limit)
                    .all()
                )
        except Exception as e:
            logger.error(f"TradeGuard get_closed_trades error: {e}")
            return []
