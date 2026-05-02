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

POLL_INTERVAL_SECONDS = 10  # Cek setiap 10 detik (lebih aman untuk rate limit)
TP_SL_CHECK_INTERVAL = 5   # Tapi cek TP/SL lebih sering (5 detik)


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
        consecutive_errors = 0

        while not self._stop_event.is_set():
            try:
                self._sync_all_trades()
                consecutive_errors = 0  # Reset on success
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"TradeMonitor sync error ({consecutive_errors}x): {e}")

                # Rate limit backoff
                if consecutive_errors >= 3:
                    logger.warning("Rate limit detected, waiting 30s...")
                    self._stop_event.wait(30)
                    consecutive_errors = 0
                else:
                    self._stop_event.wait(POLL_INTERVAL_SECONDS)

            self._stop_event.wait(POLL_INTERVAL_SECONDS)

    def _sync_all_trades(self):
        """Cek status semua trade RUNNING di database vs exchange."""
        from service.trade.trade_guard import TradeGuard

        running_trades = TradeGuard.get_all_running_trades()

        if not running_trades:
            return

        logger.debug(f"TradeMonitor: checking {len(running_trades)} running trade(s)...")

        # Batch fetch all open positions in ONE API call
        all_positions = self.exchange.get_open_positions()

        # Build a lookup for quick access
        positions_by_pair = {p["symbol"]: p for p in all_positions}

        for trade in running_trades:
            try:
                # Check TP/SL first (even if position still exists)
                position = positions_by_pair.get(trade.pair)
                if position:
                    self._check_manual_tp_sl(trade, position)

                # Then check if position still exists
                self._sync_trade(trade)
            except Exception as e:
                logger.error(f"Error syncing trade {trade.id} ({trade.pair}): {e}")

    def _sync_trade(self, trade):
        """
        Cek status trade dan update jika sudah closed.
        Logika:
        1. Cek status entry order (trade.exchange_order_id).
        2. Jika entry order CANCELED/EXPIRED/REJECTED -> Close trade as CANCELED.
        3. Jika entry order FILLED -> Cek posisi di exchange.
        4. Jika posisi 0 -> Close trade (cek apakah kena SL/TP).
        """
        if not trade.exchange_order_id:
            return

        # 1. Cek status entry order
        order = self.exchange.get_order_status(trade.pair, trade.exchange_order_id)
        if not order:
            return

        entry_status = order.get("status", "")

        # Jika entry order gagal/batal sebelum terisi
        if entry_status in ("CANCELED", "EXPIRED", "REJECTED"):
            self._close_trade(trade, order, reason="Entry Canceled")
            return

        # Jika entry order sudah FILLED atau PARTIALLY_FILLED, berarti trade sedang jalan.
        # Kita cek apakah posisi masih ada.
        if entry_status in ("FILLED", "PARTIALLY_FILLED"):
            # Cek posisi aktual di exchange
            positions = self.exchange.get_open_positions(trade.pair)
            # positions adalah list p yang Amt != 0.
            # Jika pair tidak ada di list ini, berarti posisi sudah tertutup.
            has_position = any(p["symbol"] == trade.pair for p in positions)

            if not has_position:
                # Posisi sudah tertutup! Cari tahu apakah SL atau TP yang memicu
                close_reason = self._detect_close_reason(trade)
                self._close_trade(trade, order, reason=close_reason)
            else:
                # Posisi masih ada - cek apakah TP/SL tercapai (manual monitoring)
                self._check_manual_tp_sl(trade, positions[0])

    def _detect_close_reason(self, trade) -> str:
        """
        Deteksi apakah posisi tertutup karena TP atau SL.
        Cek status TP/SL orders yang tersimpan di database.
        """
        # Check SL order status
        if trade.stop_loss_order_id:
            sl_order = self.exchange.get_order_status(trade.pair, trade.stop_loss_order_id)
            if sl_order and sl_order.get("status") in ("FILLED", "PARTIALLY_FILLED"):
                return "Hit SL"

        # Check TP order status
        if trade.take_profit_order_id:
            tp_order = self.exchange.get_order_status(trade.pair, trade.take_profit_order_id)
            if tp_order and tp_order.get("status") in ("FILLED", "PARTIALLY_FILLED"):
                return "Hit TP"

        # Fallback: guess based on current price vs entry
        current_price = self.exchange.get_realtime_price(trade.pair)
        if current_price > 0 and trade.entry_price:
            if trade.side == "BUY":
                if current_price >= trade.target_price:
                    return "Hit TP"
                elif current_price <= trade.stop_loss_price:
                    return "Hit SL"
            else:  # SELL
                if current_price <= trade.target_price:
                    return "Hit TP"
                elif current_price >= trade.stop_loss_price:
                    return "Hit SL"

        # Default
        return "Position Closed"

    def _check_manual_tp_sl(self, trade, position):
        """
        Manual TP/SL check - untuk testnet yang tidak support TP/SL orders.
        Jika harga market mencapai SL atau TP, tutup posisi secara manual.
        """
        if not trade.stop_loss_price or not trade.target_price:
            return

        current_price = self.exchange.get_realtime_price(trade.pair)
        if current_price <= 0:
            return

        entry_price = float(position.get("entryPrice", 0))
        side = trade.side

        # Tentukan apakah TP atau SL tercapai
        triggered = None

        if side == "BUY":
            # Long position: TP di atas entry, SL di bawah entry
            if current_price >= trade.target_price:
                triggered = "Hit TP"
            elif current_price <= trade.stop_loss_price:
                triggered = "Hit SL"
        elif side == "SELL":
            # Short position: TP di bawah entry, SL di atas entry
            if current_price <= trade.target_price:
                triggered = "Hit TP"
            elif current_price >= trade.stop_loss_price:
                triggered = "Hit SL"

        if triggered:
            logger.info(
                f"Manual TP/SL triggered: {trade.pair} {side} - {triggered} "
                f"(Entry: {entry_price}, Current: {current_price}, TP: {trade.target_price}, SL: {trade.stop_loss_price})"
            )

            # Tutup posisi dengan market order
            close_side = "SELL" if side == "BUY" else "BUY"
            quantity = abs(float(position.get("positionAmt", 0)))

            close_order = self.exchange.place_market_order(
                trade.pair, close_side, quantity
            )

            if close_order:
                # Cari tahu apakah TP atau SL
                if triggered == "Hit TP":
                    new_status = "CLOSED_TP"
                    exit_reason = "Hit TP"
                else:
                    new_status = "CLOSED_SL"
                    exit_reason = "Hit SL"

                # Hitung realized P/L
                realized_pnl = self._calculate_pnl(trade, current_price)

                # Update database
                from data.database import SessionFactory
                from data.models import TradeRecord

                try:
                    with SessionFactory() as session:
                        db_trade = session.query(TradeRecord).filter_by(id=trade.id).first()
                        if db_trade:
                            db_trade.status = new_status
                            db_trade.exit_price = current_price
                            db_trade.exit_reason = exit_reason
                            db_trade.realized_pnl = realized_pnl
                            db_trade.closed_at = datetime.utcnow()
                            session.commit()
                except Exception as e:
                    logger.error(f"Error updating trade {trade.id} in DB: {e}")
                    return

                logger.info(
                    f"Trade closed: {trade.pair} {trade.side} -> {exit_reason} | "
                    f"PnL: {realized_pnl:+.2f} USDT"
                )

                # Kirim notifikasi Telegram
                if self.telegram:
                    self._notify_trade_closed(trade, current_price, realized_pnl, exit_reason)

                # Trigger Autopsy jika SL
                if new_status == "CLOSED_SL":
                    threading.Thread(
                        target=self._trigger_autopsy,
                        args=(trade,),
                        daemon=True,
                        name=f"AutopsyThread-{trade.pair}",
                    ).start()

    def _close_trade(self, trade, order, reason=None):
        """Update DB saat trade ditutup, kirim notifikasi, trigger autopsy jika SL."""
        from data.database import SessionFactory
        from data.models import TradeRecord

        status = order.get("status", "")

        # Untuk exit price, gunakan:
        # 1. avgPrice dari closing order (TP/SL), atau
        # 2. Current mark price jika position sudah tertutup (tidak ada order info)
        exit_price = float(order.get("avgPrice", 0) or 0)

        # If position is closed, try to get exit price from TP/SL orders
        if exit_price == 0 and reason in ("Hit SL", "Hit TP"):
            if reason == "Hit SL" and trade.stop_loss_order_id:
                sl_order = self.exchange.get_order_status(trade.pair, trade.stop_loss_order_id)
                if sl_order:
                    exit_price = float(sl_order.get("avgPrice") or sl_order.get("stopPrice") or 0)
            elif reason == "Hit TP" and trade.take_profit_order_id:
                tp_order = self.exchange.get_order_status(trade.pair, trade.take_profit_order_id)
                if tp_order:
                    exit_price = float(tp_order.get("avgPrice") or tp_order.get("stopPrice") or 0)

        # Last resort: get current mark price
        if exit_price == 0:
            exit_price = self.exchange.get_realtime_price(trade.pair)

# Jika reason manual disediakan, gunakan itu
        if reason == "Entry Canceled":
            exit_reason = "Entry Canceled"
            new_status = "CANCELED"
            exit_price = 0  # No exit price for canceled entries
        elif reason == "Hit SL":
            exit_reason = "Hit SL"
            new_status = "CLOSED_SL"
        elif reason == "Hit TP":
            exit_reason = "Hit TP"
            new_status = "CLOSED_TP"
        elif reason == "Position Closed":
            # Fallback: assume TP if we can't determine
            exit_reason = "Closed (TP)"
            new_status = "CLOSED_TP"
        else:
            exit_reason = "Unknown"
            new_status = "CLOSED_TP"

        # Hitung PnL hanya jika kita punya entry dan exit price
        realized_pnl = 0.0
        if trade.entry_price and trade.entry_price > 0 and exit_price and exit_price > 0:
            realized_pnl = self._calculate_pnl(trade, exit_price)

        # Update database
        try:
            with SessionFactory() as session:
                db_trade = session.query(TradeRecord).filter_by(id=trade.id).first()
                if db_trade:
                    db_trade.status = new_status
                    db_trade.exit_price = exit_price
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
            self._notify_trade_closed(trade, exit_price, realized_pnl, exit_reason)

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
