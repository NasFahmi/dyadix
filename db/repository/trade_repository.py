import logging
from typing import List, Optional
from datetime import datetime
from db.database import SessionLocal
from db.models import Trade, TradeStatus

logger = logging.getLogger(__name__)

class TradeRepository:
    @staticmethod
    def get_running_trades() -> List[Trade]:
        """Ambil semua trade yang statusnya masih RUNNING."""
        db = SessionLocal()
        try:
            return db.query(Trade).filter(Trade.status == TradeStatus.RUNNING).all()
        except Exception as e:
            logger.error(f"Error fetching running trades: {e}")
            return []
        finally:
            db.close()

    @staticmethod
    def update_trade_exit(
        trade_id, 
        status: TradeStatus, 
        exit_reason: str, 
        realized_pnl: float = 0.0, 
        exit_price: float = None
    ) -> bool:
        """Update trade saat posisi ditutup."""
        db = SessionLocal()
        try:
            trade = db.query(Trade).filter(Trade.id == trade_id).first()
            if trade:
                trade.status = status
                trade.exit_reason = exit_reason
                trade.realized_pnl = realized_pnl
                trade.closed_at = datetime.utcnow()
                # entry_price bisa diupdate di sini jika baru didapat dari exchange
                db.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating trade exit: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def update_autopsy(trade_id, analysis: str) -> bool:
        """Simpan hasil analisis autopsy ke database."""
        db = SessionLocal()
        try:
            trade = db.query(Trade).filter(Trade.id == trade_id).first()
            if trade:
                trade.loss_reason_analysis = analysis
                db.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating autopsy analysis: {e}")
            db.rollback()
            return False
        finally:
            db.close()
