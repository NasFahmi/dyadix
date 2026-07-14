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
import html
from typing import Dict, Optional, Callable
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def escape_html(val) -> str:
    """Escape HTML special characters to prevent Telegram parse errors."""
    if val is None:
        return ""
    if not isinstance(val, str):
        val = str(val)
    return html.escape(val, quote=False)


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
                            elif text == "/history":
                                command_callback("history")
                                
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
        bias = escape_html(signal_result.get("suggested_bias", "Unknown"))
        signal_type = escape_html(signal_result.get("signal_type", "N/A"))
        reasons = signal_result.get("reasons", [])
        scores = signal_result.get("scores", {})

        # Emoji berdasarkan bias
        emoji = "🟢" if "Bullish" in bias else "🔴" if "Bearish" in bias else "⚪"

        reasons_text = "\n".join(f"  • {escape_html(r)}" for r in reasons[:6])

        text = (
            f"{emoji} <b>SIGNAL DETECTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Pair:</b> {escape_html(pair)}\n"
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
        action = escape_html(decision.get("decision", "N/A"))
        confidence = decision.get("confidence", "N/A")
        bias = escape_html(decision.get("bias", "N/A"))
        timeframe = escape_html(decision.get("recommended_timeframe", "N/A"))
        entry_zone = escape_html(decision.get("entry_zone", "N/A"))
        target = escape_html(decision.get("target", "N/A"))
        stop_loss = escape_html(decision.get("stop_loss", "N/A"))
        risk_reward = escape_html(decision.get("risk_reward", "N/A"))
        execution_type = escape_html(decision.get("execution_type", "N/A"))
        expected_move = escape_html(decision.get("expected_move", "N/A"))
        reason = escape_html(decision.get("reason", "N/A"))
        invalidated_if = escape_html(decision.get("invalidated_if", "N/A"))
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
        signal_bias = escape_html(signal_result.get("suggested_bias", "N/A"))

        risks_text = " | ".join(escape_html(r) for r in key_risks[:3]) if key_risks else "N/A"

        # Format realtime price
        price_text = f"${realtime_price:,.2f}" if realtime_price else "N/A"

        text = (
            f"📊 <b>DECISION — {escape_html(pair)}</b>\n"
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

        success = self.send_message(text)
        
        # Kirim debug details LLM jika enabled
        if self.enabled:
            import json
            try:
                # 1. Response dari verdict (signal_result)
                verdict_str = json.dumps(signal_result, indent=2, ensure_ascii=False)
                
                # 2. Payload final decision
                payload_str = decision.get("raw_payload", "N/A")
                try:
                    payload_json = json.loads(payload_str)
                    payload_str = json.dumps(payload_json, indent=2, ensure_ascii=False)
                except Exception:
                    pass
                    
                # 3. Response final decision (raw response)
                response_str = decision.get("raw_response", "N/A")
                
                # 4. Hasil final decision
                clean_decision = {k: v for k, v in decision.items() if k not in ["raw_payload", "raw_response"]}
                hasil_str = json.dumps(clean_decision, indent=2, ensure_ascii=False)
                
                # Potong agar tidak melebihi limit Telegram (4096 karakter)
                debug_text = (
                    f"🔍 <b>LLM DECISION DETAILS — {escape_html(pair)}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"<b>1. Verdict / Signal Result:</b>\n"
                    f"<pre><code class=\"language-json\">{escape_html(verdict_str)}</code></pre>\n\n"
                    f"<b>2. Payload Final Decision (Context):</b>\n"
                    f"<pre><code class=\"language-json\">{escape_html(payload_str[:1500])}{'...' if len(payload_str) > 1500 else ''}</code></pre>\n\n"
                    f"<b>3. Response Final Decision (Raw):</b>\n"
                    f"<pre><code>{escape_html(response_str[:1000])}{'...' if len(response_str) > 1000 else ''}</code></pre>\n\n"
                    f"<b>4. Hasil Final Decision (Parsed):</b>\n"
                    f"<pre><code class=\"language-json\">{escape_html(hasil_str)}</code></pre>"
                )
                self.send_message(debug_text)
            except Exception as e:
                logger.error(f"Failed to send decision details to Telegram: {e}")
                
        return success

    def notify_pre_decision_verdict(self, symbol: str, context: Dict) -> bool:
        """
        Kirim log/analisis ringkas dari para analyst sebelum memanggil Decision LLM.
        """
        if not self.enabled:
            return False

        # Extract data dengan safe fallbacks
        realtime_price = context.get("realtime_price", 0.0)
        
        def format_price(val):
            if val is None or val == "N/A":
                return "N/A"
            try:
                num = float(val)
                if num == 0.0:
                    return "N/A"
                return f"${num:,.5f}" if num < 1.0 else f"${num:,.2f}"
            except Exception:
                return escape_html(val)

        price_text = format_price(realtime_price)
        session = escape_html(context.get("current_market_session", "Unknown"))
        
        consensus = context.get("consensus_verdict", {})
        consensus_bias = escape_html(consensus.get("consensus_bias", "N/A"))
        consensus_conf = consensus.get("consensus_confidence", "N/A")
        regime = escape_html(consensus.get("market_regime", "NORMAL"))
        
        # Individual analysts
        tech = context.get("technical_analyst_verdict", {})
        liq = context.get("liquidity_analyst_verdict", {})
        deriv = context.get("derivatives_analyst_verdict", {})
        sent = context.get("sentiment_analyst_verdict", {})
        
        tech_bias = escape_html(tech.get("bias", "N/A"))
        tech_conf = tech.get("confidence", "N/A")
        
        liq_bias = escape_html(liq.get("bias", "N/A"))
        liq_conf = liq.get("confidence", "N/A")
        
        deriv_bias = escape_html(deriv.get("bias", "N/A"))
        deriv_conf = deriv.get("confidence", "N/A")
        
        sent_bias = escape_html(sent.get("bias", "N/A"))
        sent_conf = sent.get("confidence", "N/A")
        
        # Risk Parameters
        risk = context.get("risk_manager_parameters", {})
        cleared = "✅ YES" if risk.get("cleared") else "❌ NO"
        entry_mid = format_price(risk.get("entry_midpoint"))
        sl = format_price(risk.get("stop_loss"))
        tp = format_price(risk.get("take_profit"))
        rr = escape_html(risk.get("risk_reward", "N/A"))
        
        # Reasons formatting
        reasons = consensus.get("aggregated_reasons", [])
        reasons_text = "\n".join(f"  • {escape_html(r)}" for r in reasons[:6]) if reasons else "  • N/A"

        # Emoji berdasarkan consensus bias
        emoji = "🟢" if "Bullish" in consensus_bias else "🔴" if "Bearish" in consensus_bias else "🟡"

        text = (
            f"{emoji} <b>PRE-DECISION STATE — {escape_html(symbol)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Price:</b> {price_text} | <b>Session:</b> {session}\n"
            f"<b>Consensus Bias:</b> {consensus_bias} ({consensus_conf})\n"
            f"<b>Regime:</b> {regime}\n"
            f"\n"
            f"<b>Analyst Verdicts:</b>\n"
            f"  • Technical: {tech_bias} ({tech_conf})\n"
            f"  • Liquidity: {liq_bias} ({liq_conf})\n"
            f"  • Derivatives: {deriv_bias} ({deriv_conf})\n"
            f"  • Sentiment: {sent_bias} ({sent_conf})\n"
            f"\n"
            f"<b>Risk Parameters:</b>\n"
            f"  • Cleared: {cleared}\n"
            f"  • Entry Midpoint: {entry_mid}\n"
            f"  • Stop Loss: {sl}\n"
            f"  • Take Profit: {tp}\n"
            f"  • Risk/Reward: {rr}\n"
            f"\n"
            f"<b>Consensus Reasons:</b>\n"
            f"{reasons_text}\n"
            f"\n"
            f"⏳ <i>Invoking final Decision LLM...</i>"
        )
        
        return self.send_message(text)

    def notify_order_placed(
        self, pair: str, action: str, decision: Dict, realtime_price: float = 0.0,
        actual_entry: Optional[float] = None
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
        risk_reward = escape_html(decision.get("risk_reward", "N/A"))

        action_emoji = "🟢" if action == "BUY" else "🔴"
        exec_emoji = "⚡ MARKET" if execution_type == "MARKET" else "📋 LIMIT"

        # Use actual entry price if available (for executed orders on testnet)
        entry_display = f"${actual_entry:,.2f}" if actual_entry and actual_entry > 0 else f"${entry_planned:,.2f}"
        entry_label = "Entry (Filled)" if actual_entry and actual_entry > 0 else "Entry Planned"

        text = (
            f"✅ <b>ORDER EXECUTED — {escape_html(pair)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Action:</b> {action_emoji} {escape_html(action)} ({exec_emoji})\n"
            f"<b>{entry_label}:</b> {entry_display}\n"
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
                from service.exchange.hyperliquid_client import HyperliquidClient
                exchange = HyperliquidClient()
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

    def notify_all_trades(self) -> bool:
        """
        Kirim daftar semua trades (RUNNING + CLOSED) dipanggil oleh /trades command.
        Menampilkan juga P/L untuk closed trades.
        """
        try:
            from service.trade.trade_guard import TradeGuard
            from datetime import datetime

            running = TradeGuard.get_all_running_trades()
            closed = TradeGuard.get_closed_trades(limit=10)

            # Get real-time P/L from exchange
            try:
                from service.exchange.hyperliquid_client import HyperliquidClient
                exchange = HyperliquidClient()
            except Exception:
                exchange = None

            lines = []

            # === RUNNING TRADES ===
            if running:
                lines.append("📂 <b>RUNNING TRADES</b>")
                lines.append("━━━━━━━━━━━━━━━━━━━━")

                for i, t in enumerate(running, 1):
                    duration = ""
                    if t.opened_at:
                        delta = datetime.utcnow() - t.opened_at
                        hours, remainder = divmod(int(delta.total_seconds()), 3600)
                        minutes = remainder // 60
                        duration = f" | {hours}j {minutes}m"

                    unrealized_pnl = 0.0
                    if exchange and t.entry_price and t.entry_price > 0:
                        try:
                            position = exchange.get_position_pnl(t.pair)
                            if position:
                                unrealized_pnl = float(position.get("unrealizedPnl", 0))
                        except Exception:
                            pass

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
            else:
                lines.append("📂 <b>RUNNING TRADES</b>\n━━━━━━━━━━━━━━━━━━━━\n<i>Tidak ada trade yang sedang berjalan.</i>")

            # === CLOSED TRADES ===
            if closed:
                lines.append("\n\n📕 <b>CLOSED TRADES</b> (Last 10)")
                lines.append("━━━━━━━━━━━━━━━━━━━━")

                total_pnl = 0.0
                for i, t in enumerate(closed, 1):
                    duration = ""
                    if t.opened_at and t.closed_at:
                        delta = t.closed_at - t.opened_at
                        hours, remainder = divmod(int(delta.total_seconds()), 3600)
                        minutes = remainder // 60
                        duration = f"{hours}j {minutes}m"

                    action_emoji = "🟢" if t.side == "BUY" else "🔴"

                    entry_display = f"${t.entry_price:,.2f}" if t.entry_price and t.entry_price > 0 else "N/A"
                    exit_display = f"${t.exit_price:,.2f}" if t.exit_price and t.exit_price > 0 else "N/A"

                    pnl = t.realized_pnl or 0.0
                    total_pnl += pnl
                    pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                    pnl_str = f"{pnl_emoji} ${pnl:+.2f}"

                    if t.status == "CLOSED_TP":
                        status_label = "✅ TP"
                    elif t.status == "CLOSED_SL":
                        status_label = "❌ SL"
                    else:
                        status_label = "⚪ CLOSED"

                    lines.append(
                        f"\n<b>{i}. {t.pair}</b> {action_emoji} {t.side} {status_label}\n"
                        f"   Entry: {entry_display} → Exit: {exit_display}\n"
                        f"   P/L: {pnl_str} | Durasi: {duration}\n"
                        f"   Qty: {t.quantity} | Lev: {t.leverage}x"
                    )

                total_emoji = "🟢" if total_pnl >= 0 else "🔴"
                lines.append(f"\n<b>Total Closed P/L:</b> {total_emoji} ${total_pnl:+.2f}")

            return self.send_message("\n".join(lines))

        except Exception as e:
            logger.error(f"Failed to get all trades: {e}")
            return self.send_message("❌ Gagal mengambil data trades.")
