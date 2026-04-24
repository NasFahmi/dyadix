"""
pipelines/loop_scheduler.py

Orchestrator utama Dyadix DSS — menjalankan bot secara continuous loop
dengan staggered data fetching dan signal detection sebagai gate LLM.

Alur setiap cycle:
  1. DataManager cek dan refresh data yang sudah stale
  2. ContextBuilder bangun full context per pair
  3. SignalDetector scoring cepat tanpa LLM
  4. Jika lolos threshold + tidak cooldown → panggil Decision LLM
  5. Log semua hasil ke DecisionLogger

Interval tick: 30 detik (configurable via settings.yml)
"""

import json
import time
import signal as signal_module
import logging
import sys
import pandas as pd
from typing import Dict, Any
from datetime import datetime
from llm.factory import get_decision_llm
from llm.system_prompt import SystemPrompt
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class LoopScheduler:
    """
    Main loop orchestrator — menjalankan DSS secara continuous
    dengan staggered data fetching dan signal detection.
    """

    def __init__(self):
        from config.settings import get_config
        from features.context_builder import ContextBuilder
        from pipelines.data_manager import DataManager
        from pipelines.signal_detector import SignalDetector
        from pipelines.decision_logger import DecisionLogger
        from bot.telegram import TelegramNotifier

        config = get_config()
        scheduler_config = config.get("scheduler", {})
        detector_config = config.get("signal_detector", {})

        self.tick_interval = scheduler_config.get("tick_interval", 60)

        self.data_manager = DataManager()
        self.context_builder = ContextBuilder()
        self.signal_detector = SignalDetector(
            min_confidence=detector_config.get("min_confidence", 0.65)
        )
        self.decision_logger = DecisionLogger(
            cooldown_seconds=detector_config.get("cooldown_seconds", 900)
        )
        self.telegram = TelegramNotifier()

        self.running = True
        self.cycle_count = 0
        self._start_time = None

    # ─────────────────────────────────────────────────────────────────────
    #  ENTRY POINT
    # ─────────────────────────────────────────────────────────────────────

    def start(self):
        """Start the infinite loop dengan graceful shutdown via Ctrl+C."""
        # Register signal handlers
        signal_module.signal(signal_module.SIGINT, self._handle_shutdown)
        signal_module.signal(signal_module.SIGTERM, self._handle_shutdown)

        self._start_time = time.time()

        print("\n" + "=" * 60)
        print("  🚀 DYADIX DSS — Continuous Mode Started")
        print("=" * 60)
        print(f"  Tick interval : {self.tick_interval}s")
        print(f"  Pairs         : {', '.join(self.data_manager.pairs)}")
        print(f"  Min confidence: {self.signal_detector.min_confidence}")
        print(f"  Cooldown      : {self.decision_logger.cooldown_seconds}s")
        print(f"  Press Ctrl+C to stop gracefully")
        print("=" * 60 + "\n")

        logger.info("Dyadix DSS started — running continuously...")

        while self.running:
            self.cycle_count += 1
            cycle_start = time.time()

            try:
                self._run_cycle()
            except Exception as e:
                logger.error(f"❌ Cycle {self.cycle_count} error: {e}", exc_info=True)

            elapsed = time.time() - cycle_start
            sleep_time = max(0, self.tick_interval - elapsed)

            if self.running and sleep_time > 0:
                logger.debug(
                    f"💤 Cycle {self.cycle_count} done in {elapsed:.1f}s, "
                    f"sleeping {sleep_time:.1f}s..."
                )
                # Sleep in small increments untuk responsive shutdown
                self._interruptible_sleep(sleep_time)

        self._print_shutdown_summary()

    # ─────────────────────────────────────────────────────────────────────
    #  MAIN CYCLE
    # ─────────────────────────────────────────────────────────────────────

    def _run_cycle(self):
        """Satu siklus: refresh data → detect signals → call LLM jika ada signal."""
        logger.info(f"\n{'─' * 50}")
        logger.info(
            f"  Cycle #{self.cycle_count} started at {datetime.utcnow().strftime('%H:%M:%S')} UTC"
        )
        logger.info(f"{'─' * 50}")

        # ── Step 1: Refresh stale data ────────────────────────────────
        refreshed = self.data_manager.refresh_stale_data()

        # ── Step 2: Build context per pair ────────────────────────────
        market_data = self.data_manager.get_market_data()
        if not market_data:
            logger.warning("No market data available yet, skipping cycle")
            return

        sentiment_result = self.data_manager.get_sentiment_result()
        correlation_data = self.data_manager.get_correlation_data()
        derivatives_data = self.data_manager.get_derivatives_data()

        # Build full context menggunakan ContextBuilder
        from features.context_builder import build_full_context

        try:
            full_contexts = build_full_context(
                market_data=market_data,
                sentiment_result=sentiment_result,
                derivatives_data=derivatives_data,
                correlation_data=correlation_data,
                target_pairs=self.data_manager.pairs,
            )
        except Exception as e:
            logger.error(f"Failed to build full context: {e}")
            return

        # ── Step 3: Signal detection + LLM gate per pair ─────────────
        signals_found = 0
        llm_calls = 0

        for pair, ctx in full_contexts.items():
            if "error" in ctx and "technical" not in ctx:
                logger.error(f"  ❌ {pair} context error: {ctx.get('error')}")
                continue

            # ── Check if pair already has a running trade in DB ──
            if self._has_active_trade(pair):
                logger.info(f"  🚫 {pair} → Skipped: Active trade still running in database")
                continue

            # Inject last candles dan market snapshot
            ctx = self._inject_extra_context(ctx, market_data.get(pair, {}))

            # Signal Detection
            signal_result = self.signal_detector.detect(ctx)

            if not signal_result["has_potential_signal"]:
                logger.info(
                    f"  ⏭ {pair} → No signal "
                    f"(confidence {signal_result['confidence']}, "
                    f"bull={signal_result['scores']['bullish']}, "
                    f"bear={signal_result['scores']['bearish']})"
                )
                self.decision_logger.log_skip(pair, signal_result)
                continue

            signals_found += 1

            # Cooldown check
            if self.decision_logger.is_in_cooldown(pair):
                remaining = self.decision_logger.get_cooldown_remaining(pair)
                logger.info(
                    f"  ⏳ {pair} → Signal detected but in cooldown "
                    f"({remaining:.0f}s remaining)"
                )
                self.decision_logger.log_cooldown_skip(pair)
                continue

            # ── Call Decision LLM ─────────────────────────────────────
            logger.info(
                f"  🚀 {pair} → Signal! confidence={signal_result['confidence']} "
                f"| bias={signal_result['suggested_bias']} "
                f"| Calling LLM..."
            )

            # Notify Telegram: signal detected
            self.telegram.notify_signal_detected(pair, signal_result)

            # Inject realtime price & signal detector result into context
            realtime_price = self._fetch_realtime_price(pair)
            ctx["realtime_price"] = realtime_price
            ctx["signal_detector_result"] = {
                "suggested_bias": signal_result.get("suggested_bias"),
                "signal_type": signal_result.get("signal_type"),
                "confidence": signal_result.get("confidence"),
                "reasons": signal_result.get("reasons", []),
            }

            decision = self._call_decision_llm(ctx)
            llm_calls += 1

            self.decision_logger.log_decision(pair, signal_result, decision)

            # Notify Telegram: decision result (with realtime price)
            telegram_sent = self.telegram.notify_decision(pair, signal_result, decision, realtime_price)
            if telegram_sent:
                self.decision_logger.log_telegram_sent(pair, signal_result, decision, realtime_price)

            # Print decision
            self._print_decision(pair, signal_result, decision)

        # ── Cycle summary ─────────────────────────────────────────────
        logger.info(
            f"  📊 Cycle #{self.cycle_count} summary: "
            f"{len(full_contexts)} pairs scanned | "
            f"{signals_found} signals found | "
            f"{llm_calls} LLM calls made"
        )

    # ─────────────────────────────────────────────────────────────────────
    #  CONTEXT ENRICHMENT
    # ─────────────────────────────────────────────────────────────────────

    def _inject_extra_context(self, ctx: Dict, tf_data: Dict) -> Dict:
        """Inject last_candles dan market_snapshot ke context."""
        # Last candles
        ctx = self._inject_last_candles(ctx, tf_data)
        # Market snapshot
        ctx = self._inject_market_snapshot(ctx, tf_data)
        return ctx

    def _inject_last_candles(self, ctx: Dict, tf_data: Dict, n: int = 10) -> Dict:
        """Tambahkan data candlestick terbaru ke context."""
        last_candles: Dict[str, Any] = {}
        for tf in ["3m", "5m", "15m", "1h"]:
            df = tf_data.get(tf, {}).get("aggregated", pd.DataFrame())
            if df.empty:
                continue
            tail = df.tail(n).copy()
            for col in ["timestamp"]:
                if col in tail.columns:
                    tail[col] = tail[col].astype(str)
            cols = [
                c
                for c in ["timestamp", "open", "high", "low", "close", "volume"]
                if c in tail.columns
            ]
            last_candles[tf] = tail[cols].to_dict(orient="records")

        ctx["last_candles"] = last_candles
        return ctx

    def _inject_market_snapshot(self, ctx: Dict, tf_data: Dict) -> Dict:
        """Tambahkan MarketSnapshot ke context."""
        try:
            from features.snapshot.market_snapshot import build_market_snapshot

            snapshot = build_market_snapshot(tf_data)
            ctx["market_snapshot"] = snapshot
        except Exception as e:
            logger.warning(f"Market snapshot build failed: {e}")
            ctx["market_snapshot"] = {}
        return ctx

    # ─────────────────────────────────────────────────────────────────────
    #  DECISION LLM
    # ─────────────────────────────────────────────────────────────────────

    def _call_decision_llm(self, full_context: Dict) -> Dict:
        """Kirim full context ke Decision LLM via factory."""

        system_prompt = SystemPrompt().get_system_prompt_decision()

        user_input = (
            f"Full Market Context:\n"
            f"{json.dumps(full_context, indent=2, ensure_ascii=False, default=str)}"
        )

        decision_schema = {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["BUY", "SELL", "HOLD", "WAIT"],
                    "description": "Trading decision"
                },
                "rr_calculation": {
                    "type": "string",
                    "description": "Step-by-step mathematical calculation for SL and Target based on ATR to ensure minimum 1:1.5 Risk/Reward ratio."
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Confidence level from 0.0 to 1.0"
                },
                "bias": {
                    "type": "string",
                    "enum": [
                        "Strong Bullish",
                        "Moderate Bullish",
                        "Neutral",
                        "Moderate Bearish",
                        "Strong Bearish"
                    ]
                },
                "recommended_timeframe": {
                    "type": "string",
                    "enum": ["M5", "M15", "H1", "Swing"]
                },
                "entry_zone": {
                    "type": "string",
                    "maxLength": 80,
                    "description": "Entry zone or condition"
                },
                "invalidated_if": {
                    "type": "string",
                    "maxLength": 100,
                    "description": "Condition that invalidates the setup"
                },
                "target": {
                    "type": "string",
                    "maxLength": 80,
                    "description": "Target price or zone"
                },
                "stop_loss": {
                    "type": "string",
                    "maxLength": 80,
                    "description": "Stop loss level"
                },
                "risk_reward": {
                    "type": "string",
                    "maxLength": 20,
                    "description": "Risk to reward ratio (example: 1:2.5)"
                },
                "execution_type": {
                    "type": "string",
                    "enum": ["MARKET", "LIMIT"],
                    "description": "MARKET if realtime_price is inside entry_zone, LIMIT if entry_zone requires a pullback"
                },
                "expected_move": {
                    "type": "string",
                    "maxLength": 100,
                    "description": "Expected price movement with timeframe (example: '+2.8% to +4.2% dalam 12 jam')"
                },
                "reason": {
                    "type": "string",
                    "maxLength": 75,
                    "description": "Short, clear, and professional reasoning"
                },
                "key_risks": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "maxLength": 80
                    },
                    "minItems": 1,
                    "maxItems": 3,
                    "description": "List of key risks (maximum 3)"
                }
            },
            "required": [
                "decision",
                "rr_calculation",
                "confidence",
                "bias",
                "recommended_timeframe",
                "entry_zone",
                "invalidated_if",
                "target",
                "stop_loss",
                "risk_reward",
                "expected_move",
                "reason",
                "key_risks",
                "execution_type"
            ],
            "additionalProperties": False
        }

        try:
            llm = get_decision_llm()
            provider = type(llm).__name__
            logger.info(f"  🤖 Decision LLM provider: {provider}")

            # Coba structured_generate dulu
            try:
                result = llm.structured_generate(
                    system_prompt=system_prompt,
                    user_input=user_input,
                    json_schema=decision_schema,
                )
                if result and "error" not in result and "decision" in result:
                    return result
                logger.warning(
                    "structured_generate tidak mengembalikan keputusan valid, "
                    "fallback ke generate()"
                )
            except Exception as e:
                logger.warning(
                    f"structured_generate gagal ({e}), fallback ke generate()"
                )

            # Fallback ke generate() biasa
            raw = llm.generate(system_prompt=system_prompt, user_input=user_input)
            content = raw.get("content", "").strip()

            # Bersihkan markdown
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                content = content[start : end + 1]

            try:
                return json.loads(content.strip())
            except json.JSONDecodeError:
                logger.error("Decision LLM tidak mengembalikan JSON yang valid")
                return self._fallback_decision()

        except Exception as e:
            logger.error(f"Failed to call Decision LLM: {e}")
            return self._fallback_decision()

    def _fallback_decision(self) -> Dict:
        return {
            "decision": "WAIT",
            "confidence": 0.3,
            "bias": "Neutral",
            "recommended_timeframe": "H1",
            "entry_zone": "Wait for better setup",
            "invalidated_if": "N/A",
            "target": "N/A",
            "stop_loss": "N/A",
            "risk_reward": "N/A",
            "expected_move": "N/A",
            "reason": "LLM response invalid or timeout — manual review required",
            "key_risks": ["LLM unavailable", "Low confidence"],
            "execution_type": "LIMIT",
        }

    # ─────────────────────────────────────────────────────────────────────
    #  OUTPUT & DISPLAY
    # ─────────────────────────────────────────────────────────────────────

    def _print_decision(self, pair: str, signal_result: Dict, decision: Dict) -> None:
        """Print decision dengan format yang mudah dibaca."""
        print(f"\n{'━' * 50}")
        print(f"  🎯 SIGNAL → {pair}")
        print(f"{'━' * 50}")
        print(f"  Signal confidence : {signal_result.get('confidence')}")
        print(f"  Signal bias       : {signal_result.get('suggested_bias')}")
        print(f"  Signal reasons    : {', '.join(signal_result.get('reasons', []))}")
        print(f"{'─' * 50}")
        print(f"  Decision  : {decision.get('decision', 'N/A')}")
        print(f"  LLM Conf  : {decision.get('confidence', 'N/A')}")
        print(f"  Bias      : {decision.get('bias', 'N/A')}")
        print(f"  Timeframe : {decision.get('recommended_timeframe', 'N/A')}")
        print(f"  Entry Zone: {decision.get('entry_zone', 'N/A')}")
        print(f"  Target    : {decision.get('target', 'N/A')}")
        print(f"  Stop Loss : {decision.get('stop_loss', 'N/A')}")
        print(f"  RR Ratio  : {decision.get('risk_reward', 'N/A')}")
        print(f"  Exec Type : {decision.get('execution_type', 'N/A')}")
        print(f"  Reason    : {decision.get('reason', 'N/A')}")
        key_risks = decision.get("key_risks", [])
        if key_risks:
            print(f"  Key Risks : {' | '.join(key_risks)}")
        print(f"{'━' * 50}\n")

    def _print_shutdown_summary(self) -> None:
        """Print ringkasan ketika bot berhenti."""
        uptime = time.time() - self._start_time if self._start_time else 0
        summary = self.decision_logger.get_today_summary()

        print(f"\n{'=' * 60}")
        print("  🛑 DYADIX DSS — Shutdown Summary")
        print(f"{'=' * 60}")
        print(f"  Uptime       : {uptime / 60:.1f} minutes")
        print(f"  Total cycles : {self.cycle_count}")
        print(f"  LLM calls    : {summary.get('llm_calls', 0)}")
        print(f"  Decisions    : {summary.get('decisions', 0)}")
        print(f"  Skipped      : {summary.get('skips', 0)}")
        print(f"  Cooldown skip: {summary.get('cooldown_skips', 0)}")
        print(f"  Log file     : {self.decision_logger._get_today_filepath()}")
        print(f"{'=' * 60}\n")

    # ─────────────────────────────────────────────────────────────────────
    #  UTILITIES
    # ─────────────────────────────────────────────────────────────────────

    def _fetch_realtime_price(self, pair: str) -> float:
        """
        Ambil harga terbaru secara langsung dari exchange (bukan dari cache)
        untuk mengurangi latency pada entry zone.
        """
        try:
            exchange = self.data_manager.market_service.binance.exchange
            # Convert BTCUSDT → BTC/USDT format for ccxt
            base = pair.replace("USDT", "")
            symbol = f"{base}/USDT"
            ticker = exchange.fetch_ticker(symbol)
            price = ticker.get("last", 0.0)
            logger.debug(f"Realtime price for {pair}: {price}")
            return float(price)
        except Exception as e:
            logger.warning(f"Failed to fetch realtime price for {pair}: {e}")
            return 0.0

    def _handle_shutdown(self, signum, frame):
        """Handle Ctrl+C gracefully."""
        logger.info("\n⚠️  Shutdown signal received. Finishing current cycle...")
        self.running = False

    def _interruptible_sleep(self, seconds: float):
        """Sleep yang bisa di-interrupt oleh shutdown signal."""
        end_time = time.time() + seconds
        while time.time() < end_time and self.running:
            time.sleep(min(1.0, end_time - time.time()))

    def _has_active_trade(self, pair: str) -> bool:
        """Cek ke database apakah ada trade yang statusnya RUNNING untuk pair ini."""
        try:
            from db.database import SessionLocal
            from db.models import Trade, TradeStatus
            
            db = SessionLocal()
            try:
                active_trade = db.query(Trade).filter(
                    Trade.pair == pair,
                    Trade.status == TradeStatus.RUNNING
                ).first()
                return active_trade is not None
            except Exception as e:
                logger.error(f"Error checking active trade in DB: {e}")
                return False
            finally:
                db.close()
        except ImportError:
            return False
