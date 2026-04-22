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
from typing import Dict, Optional
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
        self, pair: str, signal_result: Dict, decision: Dict
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

        signal_conf = signal_result.get("confidence", 0)
        signal_bias = signal_result.get("suggested_bias", "N/A")

        risks_text = " | ".join(key_risks[:3]) if key_risks else "N/A"

        text = (
            f"📊 <b>DECISION — {pair}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"<b>Action:</b> {action_emoji}\n"
            f"<b>Confidence:</b> {confidence}\n"
            f"<b>Bias:</b> {bias}\n"
            f"<b>Timeframe:</b> {timeframe}\n"
            f"\n"
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
