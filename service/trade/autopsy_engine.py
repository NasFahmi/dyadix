"""
service/trade/autopsy_engine.py

Analisis pasca-trade menggunakan LLM Autopsy.
Dipanggil oleh TradeMonitor setelah trade kena Stop Loss.

Proses:
  1. Kumpulkan data: price action M5 selama trade berlangsung, berita relevan, korelasi BTC
  2. Susun payload autopsy
  3. Kirim ke LLM dengan system prompt autopsy
  4. Simpan hasil ke DB (kolom autopsy_analysis, autopsy_lesson)
  5. Kirim laporan ke Telegram
"""

import json
import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class AutopsyEngine:
    """
    Engine analisis post-trade Loss menggunakan LLM.
    """

    def __init__(self, telegram=None):
        self.telegram = telegram

    def run(self, trade) -> bool:
        """
        Jalankan analisis autopsy untuk satu trade yang kena SL.

        Args:
            trade: TradeRecord instance

        Returns:
            True jika berhasil, False jika gagal.
        """
        from config.settings import get_config
        config = get_config()

        autopsy_cfg = config.get("autopsy", {})
        if not autopsy_cfg.get("enabled", True):
            logger.info(f"Autopsy disabled in config, skipping for {trade.pair}")
            return False

        # Cek minimum loss threshold
        min_loss = autopsy_cfg.get("min_loss_usd", 1.0)
        if trade.realized_pnl and abs(trade.realized_pnl) < min_loss:
            logger.info(f"Autopsy skipped: PnL ${trade.realized_pnl:.2f} < threshold ${min_loss}")
            return False

        logger.info(f"Running autopsy for {trade.pair} trade {trade.id}...")

        # ── Kumpulkan data ────────────────────────────────────────────
        payload = self._build_payload(trade)

        # ── Panggil LLM Autopsy ───────────────────────────────────────
        analysis_text = self._call_autopsy_llm(payload)

        if not analysis_text:
            logger.error(f"Autopsy LLM returned empty for {trade.pair}")
            return False

        # ── Ekstrak [LESSON] dari analisis ───────────────────────────
        lesson = self._extract_lesson(analysis_text)

        # ── Simpan ke database ────────────────────────────────────────
        self._save_autopsy(trade.id, analysis_text, lesson)

        # ── Kirim ke Telegram ─────────────────────────────────────────
        if autopsy_cfg.get("notify_telegram", True) and self.telegram:
            self._send_telegram_autopsy(trade, analysis_text, lesson)

        logger.info(f"Autopsy completed for {trade.pair} trade {trade.id}")
        return True

    def _build_payload(self, trade) -> Dict[str, Any]:
        """Susun payload untuk LLM Autopsy."""

        # ── Price action selama trade berlangsung ─────────────────────
        price_action = self._get_price_action(
            pair=trade.pair,
            start_time=trade.opened_at,
            end_time=trade.closed_at or datetime.utcnow(),
        )

        # ── Korelasi BTC ──────────────────────────────────────────────
        btc_correlation = self._get_btc_correlation(trade)

        # ── Berita relevan ────────────────────────────────────────────
        news_events = self._get_relevant_news(
            start_time=trade.opened_at,
            end_time=trade.closed_at or datetime.utcnow(),
        )

        return {
            "original_plan": {
                "pair": trade.pair,
                "side": trade.side,
                "entry": trade.entry_price,
                "stop_loss": trade.stop_loss_price,
                "target": trade.target_price,
                "leverage": trade.leverage,
                "opened_at": trade.opened_at.isoformat() if trade.opened_at else None,
                "closed_at": trade.closed_at.isoformat() if trade.closed_at else None,
                "exit_price": trade.exit_price,
                "realized_pnl": trade.realized_pnl,
            },
            "price_action_during_trade": price_action,
            "external_events": news_events,
            "btc_correlation": btc_correlation,
            "market_behavior": {
                "volatility_index": "Unknown"  # Bisa diisi dari DataManager nanti
            },
        }

    def _get_price_action(self, pair: str, start_time: datetime, end_time: datetime) -> list:
        """Ambil OHLCV M5 selama trade berlangsung dari DataManager cache."""
        try:
            from service.exchange.binance_futures_client import BinanceFuturesClient
            from binance.client import Client
            import os

            client = Client(
                os.getenv("BINANCE_API_KEY", ""),
                os.getenv("BINANCE_SECRET_KEY", ""),
                testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true"
            )

            start_ms = int(start_time.timestamp() * 1000)
            end_ms = int(end_time.timestamp() * 1000)

            klines = client.futures_klines(
                symbol=pair,
                interval="5m",
                startTime=start_ms,
                endTime=end_ms,
                limit=100,
            )

            candles = []
            for k in klines:
                candles.append({
                    "time": datetime.utcfromtimestamp(k[0] / 1000).strftime("%H:%M"),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            return candles

        except Exception as e:
            logger.warning(f"Could not fetch price action for autopsy: {e}")
            return []

    def _get_btc_correlation(self, trade) -> Dict[str, Any]:
        """Hitung pergerakan BTC selama trade berlangsung."""
        try:
            if trade.pair == "BTCUSDT":
                return {"note": "Trade is BTCUSDT itself"}

            from binance.client import Client
            import os

            client = Client(
                os.getenv("BINANCE_API_KEY", ""),
                os.getenv("BINANCE_SECRET_KEY", ""),
                testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true"
            )

            if not trade.opened_at or not trade.closed_at:
                return {}

            start_ms = int(trade.opened_at.timestamp() * 1000)
            end_ms = int(trade.closed_at.timestamp() * 1000)

            btc_klines = client.futures_klines(
                symbol="BTCUSDT", interval="5m",
                startTime=start_ms, endTime=end_ms, limit=2
            )
            pair_klines = client.futures_klines(
                symbol=trade.pair, interval="5m",
                startTime=start_ms, endTime=end_ms, limit=2
            )

            if btc_klines and pair_klines:
                btc_open = float(btc_klines[0][1])
                btc_close = float(btc_klines[-1][4])
                pair_open = float(pair_klines[0][1])
                pair_close = float(pair_klines[-1][4])

                btc_move = round((btc_close - btc_open) / btc_open * 100, 2)
                pair_move = round((pair_close - pair_open) / pair_open * 100, 2)

                return {"btc_move_pct": btc_move, "pair_move_pct": pair_move}

        except Exception as e:
            logger.warning(f"Could not fetch BTC correlation for autopsy: {e}")

        return {}

    def _get_relevant_news(self, start_time: datetime, end_time: datetime) -> list:
        """Ambil berita dari cache yang timestamp-nya masuk rentang trade."""
        try:
            import os, json
            from pathlib import Path

            cache_dir = Path("cache/news")
            news_items = []

            for cache_file in cache_dir.glob("*.json"):
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    articles = data.get("content", [])
                    for article in articles:
                        fetched_at_str = article.get("fetched_at", "")
                        if fetched_at_str:
                            fetched_at = datetime.fromisoformat(fetched_at_str)
                            if start_time <= fetched_at <= end_time:
                                news_items.append({
                                    "time": fetched_at.strftime("%H:%M UTC"),
                                    "headline": article.get("title", ""),
                                    "source": article.get("source", ""),
                                })
                except Exception:
                    continue

            return news_items[:10]  # Maks 10 berita

        except Exception as e:
            logger.warning(f"Could not fetch news for autopsy: {e}")
            return []

    def _call_autopsy_llm(self, payload: Dict[str, Any]) -> Optional[str]:
        """Kirim payload ke LLM dengan system prompt autopsy."""
        try:
            from llm.factory import get_autopsy_llm
            from llm.system_prompt import SystemPrompt

            llm = get_autopsy_llm()
            system_prompt = SystemPrompt().get_system_prompt_autopsy()
            user_input = (
                "Analyze this failed trade and provide your autopsy:\n\n"
                f"{json.dumps(payload, indent=2, default=str)}"
            )

            result = llm.generate(system_prompt=system_prompt, user_input=user_input)
            return result.get("content", "").strip()

        except Exception as e:
            logger.error(f"Autopsy LLM call failed: {e}")
            return None

    def _extract_lesson(self, analysis_text: str) -> str:
        """Ekstrak bagian [LESSON] dari teks analisis."""
        match = re.search(r"\[LESSON\]:\s*(.+?)(?:\n|$)", analysis_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

    def _save_autopsy(self, trade_id: str, analysis: str, lesson: str):
        """Simpan hasil autopsy ke kolom di tabel trades."""
        try:
            from data.database import SessionFactory
            from data.models import TradeRecord

            with SessionFactory() as session:
                trade = session.query(TradeRecord).filter_by(id=trade_id).first()
                if trade:
                    trade.autopsy_analysis = analysis
                    trade.autopsy_lesson = lesson
                    session.commit()
        except Exception as e:
            logger.error(f"Error saving autopsy to DB: {e}")

    def _send_telegram_autopsy(self, trade, analysis_text: str, lesson: str):
        """Kirim laporan autopsy ke Telegram."""
        if not self.telegram:
            return

        pnl_str = f"-${abs(trade.realized_pnl):.2f}" if trade.realized_pnl else "N/A"

        # Potong teks analisis (maks 800 karakter untuk Telegram)
        analysis_short = analysis_text
        lesson_tag = f"\n[LESSON]: {lesson}" if lesson else ""
        # Hapus [LESSON] dari body agar tidak duplikat
        body = re.sub(r"\[LESSON\]:.*", "", analysis_short, flags=re.IGNORECASE).strip()
        if len(body) > 700:
            body = body[:700] + "..."

        text = (
            f"🔬 <b>TRADE AUTOPSY — {trade.pair}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Entry:</b> ${trade.entry_price:,.2f} | "
            f"<b>SL:</b> ${trade.stop_loss_price:,.2f} | "
            f"<b>PnL:</b> {pnl_str}\n\n"
            f"📋 <b>Analysis:</b>\n"
            f"{body}\n\n"
            f"💡 <b>[LESSON]:</b> {lesson or 'N/A'}"
        )

        self.telegram.send_message(text)
