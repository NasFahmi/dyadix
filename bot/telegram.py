"""
bot/telegram.py

Telegram Bot Notifier untuk Dyadix DSS.
Mengirim notifikasi saat:
  1. Signal terdeteksi (sebelum LLM call)
  2. Decision LLM selesai (hasil analisis)

Konfigurasi via .env:
  TELEGRAM_BOT=<bot_token>
  TELEGRAM_CHAT_ID=<chat_id>

Cara mendapatkan CHAT_ID:
  1. Kirim pesan ke bot Anda di Telegram
  2. Buka https://api.telegram.org/bot<TOKEN>/getUpdates
  3. Cari "chat":{"id": ...} → itu adalah CHAT_ID Anda
"""

import os
import logging
import requests
import threading
import time
from typing import Dict, Optional, Callable
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Mengirim notifikasi ke Telegram Bot API.
    Menggunakan HTTP requests langsung (tidak butuh library python-telegram-bot).
    """

    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.token and self.chat_id)
        
        self.polling_thread = None
        self.stop_event = threading.Event()
        self.last_update_id = 0

        if not self.enabled:
            if not self.token:
                logger.warning("TELEGRAM_BOT token not set in .env — notifications disabled")
            if not self.chat_id:
                logger.warning("TELEGRAM_CHAT_ID not set in .env — notifications disabled")
        else:
            logger.info("Telegram notifier initialized")

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Kirim pesan teks ke Telegram.
        
        Returns:
            True jika berhasil, False jika gagal.
        """
        if not self.enabled:
            return False

        url = self.BASE_URL.format(token=self.token)
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.debug("Telegram message sent successfully")
                return True
            else:
                logger.error(
                    f"Telegram API error: {resp.status_code} — {resp.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────
    #  POLLING FOR COMMANDS
    # ─────────────────────────────────────────────────────────────────────

    def start_polling(self, command_callback: Callable[[str], None]):
        """
        Mulai polling di background thread untuk mendengarkan command.
        """
        if not self.enabled:
            return

        self.stop_event.clear()
        self.polling_thread = threading.Thread(
            target=self._poll,
            args=(command_callback,),
            daemon=True,
            name="TelegramPollingThread"
        )
        self.polling_thread.start()
        logger.info("Telegram polling started")

    def stop_polling(self):
        """
        Berhentikan polling thread.
        """
        if self.polling_thread and self.polling_thread.is_alive():
            self.stop_event.set()
            # Tidak perlu join karena thread daemon dan bisa memblokir exit
            logger.info("Telegram polling stopped")

    def _poll(self, command_callback: Callable[[str], None]):
        """
        Loop polling untuk mengambil updates dari Telegram API.
        """
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        
        while not self.stop_event.is_set():
            try:
                payload = {
                    "offset": self.last_update_id + 1,
                    "timeout": 5  # long polling timeout
                }
                resp = requests.post(url, json=payload, timeout=10)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        updates = data.get("result", [])
                        for update in updates:
                            self.last_update_id = update["update_id"]
                            
                            message = update.get("message", {})
                            text = message.get("text", "").strip()
                            chat_id = str(message.get("chat", {}).get("id", ""))
                            
                            # Pastikan hanya memproses dari CHAT_ID yang valid
                            if chat_id != self.chat_id:
                                continue
                                
                            if text == "/start":
                                command_callback("start")
                            elif text == "/stop":
                                command_callback("stop")
                            elif text == "/auto":
                                command_callback("auto")
                            elif text == "/status":
                                command_callback("status")
                            elif text == "/trades":
                                command_callback("trades")
                                
            except requests.exceptions.Timeout:
                pass  # Wajar karena long polling
            except Exception as e:
                logger.error(f"Error in Telegram polling: {e}")
                time.sleep(2)  # Hindari spam log jika ada error jaringan
                
            # Beri jeda sedikit agar tidak over-request jika tidak ada timeout
            time.sleep(0.5)

    # ─────────────────────────────────────────────────────────────────────
    #  FORMATTED MESSAGES
    # ─────────────────────────────────────────────────────────────────────

    def notify_signal_detected(self, pair: str, signal_result: Dict) -> bool:
        """
        Kirim notifikasi saat signal terdeteksi (SEBELUM LLM call).
        """
        confidence = signal_result.get("confidence", 0)
        bias = signal_result.get("suggested_bias", "Unknown")
        signal_type = signal_result.get("signal_type", "N/A")
        reasons = signal_result.get("reasons", [])
        scores = signal_result.get("scores", {})

        # Emoji berdasarkan bias
        emoji = "🟢" if "Bullish" in bias else "🔴" if "Bearish" in bias else "⚪"

        reasons_text = "\n".join(f"  • {r}" for r in reasons[:6])

        text = (
            f"{emoji} <b>SIGNAL DETECTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Pair:</b> {pair}\n"
            f"<b>Type:</b> {signal_type}\n"
            f"<b>Bias:</b> {bias}\n"
            f"<b>Confidence:</b> {confidence}\n"
            f"<b>Bull/Bear:</b> {scores.get('bullish', 0)} / {scores.get('bearish', 0)}\n"
            f"\n<b>Reasons:</b>\n{reasons_text}\n"
            f"\n⏳ <i>Calling Decision LLM...</i>"
        )

        return self.send_message(text)

    def notify_decision(
        self, pair: str, signal_result: Dict, decision: Dict,
        realtime_price: float = 0.0
    ) -> bool:
        """
        Kirim notifikasi hasil Decision LLM.
        """
        action = decision.get("decision", "N/A")
        confidence = decision.get("confidence", "N/A")
        bias = decision.get("bias", "N/A")
        timeframe = decision.get("recommended_timeframe", "N/A")
        entry_zone = decision.get("entry_zone", "N/A")
        target = decision.get("target", "N/A")
        stop_loss = decision.get("stop_loss", "N/A")
        risk_reward = decision.get("risk_reward", "N/A")
        execution_type = decision.get("execution_type", "N/A")
        expected_move = decision.get("expected_move", "N/A")
        reason = decision.get("reason", "N/A")
        invalidated_if = decision.get("invalidated_if", "N/A")
        key_risks = decision.get("key_risks", [])

        # Emoji berdasarkan action
        if action == "BUY":
            action_emoji = "🟢 BUY"
        elif action == "SELL":
            action_emoji = "🔴 SELL"
        elif action == "HOLD":
            action_emoji = "🟡 HOLD"
        else:
            action_emoji = "⏸ WAIT"

        # Emoji berdasarkan execution type
        if execution_type == "MARKET":
            exec_emoji = "⚡ MARKET (Execute Now)"
        elif execution_type == "LIMIT":
            exec_emoji = "📋 LIMIT (Place Order & Wait)"
        else:
            exec_emoji = execution_type

        signal_conf = signal_result.get("confidence", 0)
        signal_bias = signal_result.get("suggested_bias", "N/A")

        risks_text = " | ".join(key_risks[:3]) if key_risks else "N/A"

        # Format realtime price
        price_text = f"${realtime_price:,.2f}" if realtime_price else "N/A"

        text = (
            f"📊 <b>DECISION — {pair}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"<b>Action:</b> {action_emoji}\n"
            f"<b>Confidence:</b> {confidence}\n"
            f"<b>Bias:</b> {bias}\n"
            f"<b>Timeframe:</b> {timeframe}\n"
            f"<b>Execution:</b> {exec_emoji}\n"
            f"\n"
            f"<b>Realtime Price:</b> {price_text}\n"
            f"<b>Entry Zone:</b> {entry_zone}\n"
            f"<b>Target:</b> {target}\n"
            f"<b>Stop Loss:</b> {stop_loss}\n"
            f"<b>Risk/Reward:</b> {risk_reward}\n"
            f"\n"
            f"<b>Expected Move:</b> {expected_move}\n"
            f"<b>Reason:</b> {reason}\n"
            f"<b>Invalid if:</b> {invalidated_if}\n"
            f"<b>Key Risks:</b> {risks_text}\n"
            f"\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Signal:</b> {signal_bias} ({signal_conf})\n"
            f"<i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>"
        )

        return self.send_message(text)

    def notify_order_placed(
        self, pair: str, action: str, decision: Dict, realtime_price: float = 0.0
    ) -> bool:
        """
        Kirim notifikasi saat order berhasil ditempatkan di Binance Futures.
        """
        from utils.entry_calculator import parse_entry_midpoint, parse_price

        entry_zone = decision.get("entry_zone", "N/A")
        entry_planned = parse_entry_midpoint(entry_zone, realtime_price)
        sl_price = parse_price(decision.get("stop_loss", ""), 0.0)
        tp_price = parse_price(decision.get("target", ""), 0.0)
        execution_type = decision.get("execution_type", "LIMIT")
        risk_reward = decision.get("risk_reward", "N/A")

        action_emoji = "🟢" if action == "BUY" else "🔴"
        exec_emoji = "⚡ MARKET" if execution_type == "MARKET" else "📋 LIMIT"

        text = (
            f"✅ <b>ORDER PLACED — {pair}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Action:</b> {action_emoji} {action} ({exec_emoji})\n"
            f"<b>Entry Planned:</b> ${entry_planned:,.2f}\n"
            f"<b>Realtime Price:</b> ${realtime_price:,.2f}\n"
            f"<b>Stop Loss:</b> ${sl_price:,.2f}\n"
            f"<b>Target:</b> ${tp_price:,.2f}\n"
            f"<b>R/R:</b> {risk_reward}\n"
            f"<i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>"
        )

        return self.send_message(text)

    def notify_running_trades(self) -> bool:
        """
        Kirim daftar trade yang sedang RUNNING (dipanggil oleh /trades command).
        """
        try:
            from service.trade.trade_guard import TradeGuard
            from datetime import datetime

            trades = TradeGuard.get_all_running_trades()

            if not trades:
                return self.send_message("📂 <b>RUNNING TRADES</b>\n━━━━━━━━━━━━━━━━━━━━\n<i>Tidak ada trade yang sedang berjalan.</i>")

            # Get real-time P/L from exchange
            try:
                from service.exchange.binance_futures_client import BinanceFuturesClient
                exchange = BinanceFuturesClient()
            except Exception:
                exchange = None

            lines = ["📂 <b>RUNNING TRADES</b>", "━━━━━━━━━━━━━━━━━━━━"]
            for i, t in enumerate(trades, 1):
                duration = ""
                if t.opened_at:
                    delta = datetime.utcnow() - t.opened_at
                    hours, remainder = divmod(int(delta.total_seconds()), 3600)
                    minutes = remainder // 60
                    duration = f" | {hours}j {minutes}m"

                # Get real-time P/L and unrealized P/L from exchange
                unrealized_pnl = 0.0
                if exchange and t.entry_price and t.entry_price > 0:
                    try:
                        position = exchange.get_position_pnl(t.pair)
                        if position:
                            unrealized_pnl = float(position.get("unrealizedPnl", 0))
                    except Exception:
                        pass

                # Calculate margin used
                margin_used = 0.0
                if t.entry_price and t.quantity and t.leverage:
                    margin_used = (t.entry_price * t.quantity) / t.leverage

                pnl_emoji = "🟢" if unrealized_pnl >= 0 else "🔴"
                pnl_text = f"{pnl_emoji} P/L: ${unrealized_pnl:+.2f}" if unrealized_pnl != 0 else ""

                action_emoji = "🟢" if t.side == "BUY" else "🔴"
                entry_text = f"${t.entry_price:,.2f}" if t.entry_price and t.entry_price > 0 else "⏳ Pending"

                lines.append(
                    f"\n<b>{i}. {t.pair}</b> {action_emoji} {t.side}{duration}\n"
                    f"   Entry: {entry_text}\n"
                    f"   SL: ${t.stop_loss_price:,.2f} | TP: ${t.target_price:,.2f}\n"
                    f"   Margin: ${margin_used:,.2f} | Qty: {t.quantity} | Lev: {t.leverage}x\n"
                    f"   {pnl_text}"
                )

            return self.send_message("\n".join(lines))

        except Exception as e:
            logger.error(f"Failed to get running trades: {e}")
            return self.send_message("❌ Gagal mengambil data running trades.")
