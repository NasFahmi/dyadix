"""
test_autopsy.py

Script untuk mengetes fitur Autopsy Trade.
Cara kerja:
  1. Cari trade terakhir di database.
  2. Jika tidak ada, buat trade MOCK (pura-pura rugi).
  3. Paksa jalankan AutopsyEngine.run() untuk trade tersebut.
  4. Periksa apakah LLM memberikan feedback analisis post-mortem.

Jalankan dengan:
  uv run python test_autopsy.py
"""

import sys
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

def get_or_create_loss_trade():
    """Ambil trade rugi terakhir atau buat trade mock baru."""
    from data.database import SessionFactory
    from data.models import TradeRecord
    import uuid

    with SessionFactory() as session:
        # Cari trade yang rugi (realized_pnl < 0)
        trade = session.query(TradeRecord).filter(TradeRecord.realized_pnl < 0).order_by(TradeRecord.opened_at.desc()).first()
        
        if trade:
            logger.info(f"Menggunakan trade rugi yang sudah ada: {trade.pair} (PnL: ${trade.realized_pnl})")
            return trade

        # Jika tidak ada, buat trade mock
        logger.info("Tidak ditemukan trade rugi di DB. Membuat trade MOCK untuk testing...")
        
        mock_trade = TradeRecord(
            pair="BTCUSDT",
            exchange_order_id=f"test-mock-{uuid.uuid4().hex[:8]}",
            side="BUY",
            status="CLOSED_SL",
            entry_price=71500.0,
            stop_loss_price=71000.0,
            target_price=73000.0,
            quantity=0.005,
            leverage=10,
            realized_pnl=-2.5, # Rugi $2.5
            opened_at=datetime.utcnow() - timedelta(hours=2),
            closed_at=datetime.utcnow() - timedelta(hours=1, minutes=50),
            exit_price=71000.0,
            exit_reason="Hit SL"
        )
        
        session.add(mock_trade)
        session.commit()
        session.refresh(mock_trade)
        return mock_trade

def main():
    print("\n" + "█" * 60)
    print("  DYADIX — Autopsy Trigger Test")
    print("█" * 60)

    # 1. Dapatkan trade rugi
    trade = get_or_create_loss_trade()

    # 2. Inisialisasi Autopsy Engine
    from service.trade.autopsy_engine import AutopsyEngine
    from bot.telegram import TelegramNotifier
    
    # Kita pakai TelegramNotifier agar bisa lihat hasil di HP jika terhubung
    telegram = TelegramNotifier()
    engine = AutopsyEngine(telegram=telegram)

    print("\n" + "=" * 60)
    print(f"  TRADING AUTOPSY START")
    print("=" * 60)
    print(f"  Pair      : {trade.pair}")
    print(f"  Side      : {trade.side}")
    print(f"  PnL       : ${trade.realized_pnl}")
    print(f"  Opened At : {trade.opened_at}")
    print(f"  Closed At : {trade.closed_at}")
    print("=" * 60)

    print("\n  ⏳ Menjalankan LLM Autopsy (ini butuh waktu beberapa detik)...")
    
    try:
        success = engine.run(trade)
        
        if success:
            # Refresh data trade dari DB untuk melihat hasil yang disimpan
            from data.database import SessionFactory
            from data.models import TradeRecord
            
            with SessionFactory() as session:
                updated_trade = session.query(TradeRecord).get(trade.id)
                
                print("\n" + "✅ AUTOPSY SUCCESS")
                print("-" * 60)
                print("📋 ANALYSIS:")
                print(updated_trade.autopsy_analysis or "N/A")
                print("\n💡 [LESSON]:")
                print(updated_trade.autopsy_lesson or "N/A")
                print("-" * 60)
        else:
            print("\n❌ AUTOPSY FAILED — Cek log untuk alasan kegagalan.")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "█" * 60)
    print("  TEST COMPLETED")
    print("█" * 60 + "\n")

if __name__ == "__main__":
    main()
