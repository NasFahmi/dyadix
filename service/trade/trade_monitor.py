"""
service/trade/trade_monitor.py

Background thread yang memantau status semua trade RUNNING di Binance Futures.
Jika mendeteksi TP atau SL tercapai:
  - Update status di PostgreSQL
  - Kirim notifikasi Telegram
  - Jika SL: trigger AutopsyEngine
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30  # Cek setiap 30 detik


class TradeMonitor:
    """
    Background service untuk monitoring status order di Binance.
    Berjalan di thread terpisah agar tidak blocking loop utama.
    """

    def __init__(self, telegram=None):
        from service.exchange.binance_futures_client import BinanceFuturesClient

        self.exchange = BinanceFuturesClient()
        self.telegram = telegram
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Mulai monitoring di background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="TradeMonitorThread",
        )
        self._thread.start()
        logger.info("TradeMonitor started.")

    def stop(self):
        """Hentikan monitoring thread."""
        self._stop_event.set()
        logger.info("TradeMonitor stopped.")

    def _run(self):
        """Loop utama monitoring."""
        while not self._stop_event.is_set():
            try:
                self._sync_all_trades()
            except Exception as e:
                logger.error(f"TradeMonitor sync error: {e}")

            self._stop_event.wait(POLL_INTERVAL_SECONDS)

    def _sync_all_trades(self):
        """Cek status semua trade RUNNING di database vs exchange."""
        from service.trade.trade_guard import TradeGuard

        running_trades = TradeGuard.get_all_running_trades()

        if not running_trades:
            return

        logger.debug(f"TradeMonitor: checking {len(running_trades)} running trade(s)...")

        for trade in running_trades:
            try:
                self._sync_trade(trade)
            except Exception as e:
                logger.error(f"Error syncing trade {trade.id} ({trade.pair}): {e}")

    def _sync_trade(self, trade):
        """Cek satu trade dan update jika sudah closed."""
        if not trade.exchange_order_id:
            return

        order = self.exchange.get_order_status(trade.pair, trade.exchange_order_id)
        if not order:
            return

        status = order.get("status", "")

        # Status Binance Futures: NEW, PARTIALLY_FILLED, FILLED, CANCELED, EXPIRED, STOPPED
        if status in ("FILLED", "STOPPED", "CANCELED", "EXPIRED"):
            self._close_trade(trade, order)

    def _close_trade(self, trade, order):
        """Update DB saat trade ditutup, kirim notifikasi, trigger autopsy jika SL."""
        from data.database import SessionFactory
        from data.models import TradeRecord

        status = order.get("status", "")
        avg_price = float(order.get("avgPrice", 0) or trade.entry_price or 0)
        order_type = order.get("type", "")

        # Tentukan exit_reason berdasarkan tipe order yang ter-fill
        if order_type == "STOP_MARKET" or status == "STOPPED":
            exit_reason = "Hit SL"
            new_status = "CLOSED_SL"
        elif order_type == "TAKE_PROFIT_MARKET":
            exit_reason = "Hit TP"
            new_status = "CLOSED_TP"
        elif status == "CANCELED":
            exit_reason = "Canceled"
            new_status = "CANCELED"
        else:
            exit_reason = "Unknown"
            new_status = "CLOSED_TP"  # Asumsi TP jika FILLED biasa

        # Hitung PnL sederhana
        realized_pnl = self._calculate_pnl(trade, avg_price)

        # Update database
        try:
            with SessionFactory() as session:
                db_trade = session.query(TradeRecord).filter_by(id=trade.id).first()
                if db_trade:
                    db_trade.status = new_status
                    db_trade.exit_price = avg_price
                    db_trade.exit_reason = exit_reason
                    db_trade.realized_pnl = realized_pnl
                    db_trade.closed_at = datetime.utcnow()
                    session.commit()
                    session.refresh(db_trade)
                    closed_trade = db_trade
        except Exception as e:
            logger.error(f"Error updating trade {trade.id} in DB: {e}")
            return

        logger.info(
            f"Trade closed: {trade.pair} {trade.side} → {exit_reason} | "
            f"PnL: {realized_pnl:+.2f} USDT"
        )

        # Kirim notifikasi Telegram
        if self.telegram:
            self._notify_trade_closed(trade, avg_price, realized_pnl, exit_reason)

        # Trigger Autopsy jika kena SL
        if new_status == "CLOSED_SL":
            threading.Thread(
                target=self._trigger_autopsy,
                args=(trade,),
                daemon=True,
                name=f"AutopsyThread-{trade.pair}",
            ).start()

    def _calculate_pnl(self, trade, exit_price: float) -> float:
        """Hitung PnL dalam USDT."""
        if not trade.entry_price or not trade.quantity:
            return 0.0

        price_diff = exit_price - trade.entry_price
        if trade.side == "SELL":
            price_diff = -price_diff

        pnl = price_diff * trade.quantity * (trade.leverage or 1)
        return round(pnl, 2)

    def _notify_trade_closed(self, trade, exit_price: float, pnl: float, exit_reason: str):
        """Kirim notifikasi Telegram saat trade ditutup."""
        if not self.telegram:
            return

        duration = ""
        if trade.opened_at:
            delta = datetime.utcnow() - trade.opened_at
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes = remainder // 60
            duration = f"{hours}j {minutes}m"

        if exit_reason == "Hit TP":
            icon = "🟢"
            label = "PROFIT"
        elif exit_reason == "Hit SL":
            icon = "🔴"
            label = "LOSS"
        else:
            icon = "⚪"
            label = "CLOSED"

        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"

        text = (
            f"{icon} <b>TRADE {label} — {trade.pair}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Entry:</b> ${trade.entry_price:,.2f} → <b>Exit:</b> ${exit_price:,.2f}\n"
            f"<b>PnL:</b> {pnl_str}\n"
            f"<b>Durasi:</b> {duration}\n"
            f"<b>Reason:</b> {exit_reason}"
        )

        if exit_reason == "Hit SL":
            text += "\n\n🔬 <i>Autopsy sedang dianalisis...</i>"

        self.telegram.send_message(text)

    def _trigger_autopsy(self, trade):
        """Panggil AutopsyEngine di thread terpisah."""
        try:
            from service.trade.autopsy_engine import AutopsyEngine
            engine = AutopsyEngine(telegram=self.telegram)
            engine.run(trade)
        except Exception as e:
            logger.error(f"Autopsy failed for {trade.pair} trade {trade.id}: {e}")
