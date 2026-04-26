import logging
import time
from datetime import datetime
from typing import List, Dict, Any
from db.repository.trade_repository import TradeRepository
from db.models import Trade, TradeStatus
from service.market.market_service import MarketService
from llm.autopsy_engine import AutopsyEngine

logger = logging.getLogger(__name__)

class TradeMonitor:
    """
    Monitor background untuk mengecek status trade yang RUNNING di Exchange.
    Jika mendeteksi trade sudah closed (Profit/Loss), update DB dan panggil Autopsy jika loss.
    """

    def __init__(self):
        self.market_service = MarketService()
        self.repo = TradeRepository()
        self.autopsy = AutopsyEngine()

    def check_trades(self):
        """Entry point untuk mengecek semua trade aktif."""
        running_trades = self.repo.get_running_trades()
        if not running_trades:
            return

        logger.info(f"🔍 Monitoring {len(running_trades)} running trades...")

        for trade in running_trades:
            try:
                self._process_single_trade(trade)
            except Exception as e:
                logger.error(f"Error monitoring trade {trade.pair}: {e}")

    def _process_single_trade(self, trade: Trade):
        """Cek status satu trade ke exchange (Futures)."""
        exchange = self.market_service.binance.exchange
        symbol = self._format_symbol(trade.pair)
        since = int(trade.opened_at.timestamp() * 1000)

        # 1. Cek apakah posisi masih terbuka
        try:
            positions = exchange.fetch_positions([symbol])
            active_position = next((p for p in positions if p['symbol'] == symbol), None)
            
            # Jika 'entryPrice' > 0, berarti posisi masih RUNNING
            if active_position and float(active_position.get('entryPrice', 0)) > 0:
                # Update entry_price di DB jika sebelumnya 0
                if trade.entry_price == 0.0:
                    trade.entry_price = float(active_position['entryPrice'])
                    # self.repo.save_entry_price(trade.id, trade.entry_price)
                return # Masih jalan, jangan di-close
        except Exception as e:
            logger.warning(f"Failed to fetch position for {symbol}: {e}")

        # 2. Jika posisi sudah TIDAK ADA, cari order penutupnya
        try:
            orders = exchange.fetch_closed_orders(symbol, since=since)
            if not orders:
                # Jika posisi hilang tapi order tidak ketemu, mungkin manual close via market
                # Coba fetch_my_trades
                trades = exchange.fetch_my_trades(symbol, since=since)
                if not trades:
                    return
                latest_execution = trades[-1]
                exit_price = latest_execution['price']
                exit_reason = "Market Close / Unknown"
                pnl = latest_execution.get('realizedPnl', 0.0)
            else:
                latest_order = orders[-1]
                exit_price = latest_order.get('average') or latest_order.get('price')
                exit_reason = latest_order.get('info', {}).get('type', 'Stop/Limit')
                # PnL di Futures biasanya ada di 'info' atau dihitung manual
                # Kita hitung manual saja agar konsisten
                pnl = 0.0

            # Hitung Profit/Loss
            side = "LONG" if trade.decision.action.value == "BUY" else "SHORT"
            if pnl == 0.0: # Jika belum terisi dari data exchange
                if side == "LONG":
                    pnl = exit_price - trade.entry_price
                else:
                    pnl = trade.entry_price - exit_price

            is_profit = pnl > 0
            status = TradeStatus.CLOSED_PROFIT if is_profit else TradeStatus.CLOSED_LOSS
            
            logger.info(f"✅ {symbol} CLOSED | Side: {side} | Exit: {exit_price} | PnL: {pnl:.4f}")

            # 3. Update Database
            success = self.repo.update_trade_exit(
                trade_id=trade.id,
                status=status,
                exit_reason=exit_reason,
                realized_pnl=float(pnl),
                exit_price=float(exit_price)
            )

            # 4. Trigger Autopsy if LOSS
            if success and status == TradeStatus.CLOSED_LOSS:
                logger.info(f"🧠 {symbol} hit SL! Triggering Autopsy...")
                self.autopsy.run_autopsy(trade)

        except Exception as e:
            logger.error(f"Error fetching exit data for {symbol}: {e}")

    def _format_symbol(self, pair: str) -> str:
        """Convert BTCUSDT -> BTC/USDT"""
        if "/" in pair:
            return pair
        base = pair.replace("USDT", "")
        return f"{base}/USDT"
