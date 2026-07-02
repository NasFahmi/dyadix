"""
pipelines/main_pipeline.py

Pipeline utama Dyadix:
  1. Fetch market data (OHLCV semua pair)
  2. Build sentiment context (news + social + F&G + economic)
  3. Analyze sentiment via LLM
  4. Build full aggregated context (technical + sentiment + derivatives + liquidity + correlation)
  5. Kirim ke Decision LLM → structured trading decision
"""

import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any
from llm.factory import get_decision_llm
from llm.system_prompt import SystemPrompt
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class MainPipeline:
    """
    Pipeline utama yang mengorkestrasi seluruh alur analisis:
    market data → sentiment → full context → decision LLM.
    """

    MARKET_DATA_LIMIT = 250  # candle per timeframe

    def __init__(self):
        from service.market.market_service import MarketService
        from features.context_builder import ContextBuilder

        self.market_service = MarketService()
        self.context_builder = ContextBuilder()
        
        from pipelines.decision_logger import DecisionLogger
        from pipelines.signal_detector import SignalDetector
        from config.settings import get_config

        config = get_config()
        detector_config = config.get("signal_detector", {})
        screening_config = config.get("screening", {})

        self.decision_logger = DecisionLogger()
        self.signal_detector = SignalDetector(
            min_confidence=detector_config.get("min_confidence", 0.55),
            divergence_threshold=detector_config.get("divergence_threshold", 0.15),
        )
        self.max_tradeable = screening_config.get("max_tradeable", 3)

        # Pastikan timeframe 1d selalu ada untuk daily bias
        if "1d" not in self.market_service.timeframes:
            self.market_service.timeframes.append("1d")

    # ─────────────────────────────────────────────────────────────────
    #  ENTRY POINT
    # ─────────────────────────────────────────────────────────────────

    def run(self, ignore_session: bool = False) -> Dict[str, Any]:
        """
        Jalankan pipeline lengkap untuk semua pair yang terdaftar di settings.yml.
        Returns dict {pair: {"full_context": ..., "decision": ...}}
        """
        logger.info("=" * 60)
        logger.info("  Dyadix Main Pipeline Started")
        logger.info("=" * 60)

        # ── Step 0: Check Active Session ──────────────────────────────
        if not ignore_session:
            from config.settings import get_config
            from utils.session_checker import is_active_session
            
            config = get_config()
            trading_config = config.get("trading", {})
            active_session = trading_config.get("active_session", "all")
            
            if not is_active_session(active_session):
                logger.info(f"⏳ Outside active session ('{active_session}'). Pipeline aborted.")
                return {"error": f"Outside active session ('{active_session}')"}


        # ── Step 1: Market data ───────────────────────────────────────
        logger.info("[1/5] Fetching market data...")
        market_data = self.market_service.fetch_ohlcv_all(limit=self.MARKET_DATA_LIMIT)

        # ── Step 2: Sentiment context (global, berlaku untuk semua pair) ──
        logger.info("[2/5] Building sentiment context...")
        sentiment_result = self._build_sentiment(market_data)

        # ── Step 3: Correlation ───────────────────────────────────────
        logger.info("[3/5] Calculating correlation...")
        correlation_data = self._build_correlation(market_data)

        # ── Step 4: Derivatives (mock — ganti dengan live service nanti) ──
        logger.info("[4/5] Building derivatives data...")
        derivatives_data = self._build_mock_derivatives(market_data)

        # ── Step 5: Full context aggregation per pair ─────────────────
        logger.info("[5/5] Aggregating full context per pair...")
        from features.context_builder import build_full_context

        full_contexts = build_full_context(
            market_data=market_data,
            sentiment_result=sentiment_result,
            derivatives_data=derivatives_data,
            correlation_data=correlation_data,
            target_pairs=self.market_service.pairs,
        )

        # ── Step 6: Signal Pre-Scoring Filter & Decision LLM per pair ──
        results: Dict[str, Any] = {}
        evaluated_candidates = []

        for pair, ctx in full_contexts.items():
            if "error" in ctx and "technical" not in ctx:
                logger.error(f"  ❌ {pair} context error: {ctx.get('error')}")
                results[pair] = ctx
                continue

            # Signal Detection Assessment
            signal_result = self.signal_detector.detect(ctx)

            if not signal_result["has_potential_signal"]:
                logger.info(
                    f"  ⏭ {pair} → No signal "
                    f"(confidence {signal_result['confidence']}, "
                    f"bull={signal_result['scores']['bullish']}, "
                    f"bear={signal_result['scores']['bearish']})"
                )
                results[pair] = {"full_context": ctx, "signal_skipped": True, "reason": "No signal / Below confidence threshold"}
                continue

            evaluated_candidates.append((pair, ctx, signal_result))

        # Sort candidate pairs by signal confidence score (descending)
        evaluated_candidates.sort(key=lambda x: x[2]["confidence"], reverse=True)
        selected_tradeables = evaluated_candidates[: self.max_tradeable]

        if evaluated_candidates:
            logger.info(
                f"🎯 Signal Pre-Scoring Filter: Selected {len(selected_tradeables)} tradeable pairs "
                f"(out of {len(evaluated_candidates)} signals found, max_tradeable={self.max_tradeable})"
            )
        else:
            logger.info("ℹ️ No pairs passed Signal Detector confidence threshold in this run.")

        for pair, ctx, signal_result in selected_tradeables:
            # Tambah LLM-generated candle summary & market snapshot hanya untuk tradeable pairs
            ctx = self._inject_candle_summary(ctx, market_data.get(pair, {}))
            ctx = self._inject_market_snapshot(ctx, market_data.get(pair, {}))

            # Inject signal detector result into context
            ctx["signal_detector_result"] = {
                "suggested_bias": signal_result.get("suggested_bias"),
                "signal_type": signal_result.get("signal_type"),
                "confidence": signal_result.get("confidence"),
                "reasons": signal_result.get("reasons", []),
            }

            logger.info(f"  ⚙  Invoking LangGraph Trading Workflow for {pair}...")
            
            # Map full context to DyadixState
            initial_state = {
                "symbol": pair,
                "realtime_price": ctx.get("current_price", 0.0),
                "current_market_session": ctx.get("current_market_session", "Unknown"),
                "market_data": ctx.get("technical", {}),
                "sentiment_data": ctx.get("sentiment", {}),
                "derivatives_data": ctx.get("derivatives", {}),
                "liquidity_data": ctx.get("liquidity", {}),
                "correlation_data": ctx.get("correlation", {}),
                "microstructure_data": ctx.get("microstructure", {}),
                "signal_detector_result": ctx.get("signal_detector_result", {}),
                "errors": []
            }
            if "current_price" not in initial_state["market_data"] and "current_price" in ctx:
                initial_state["market_data"]["current_price"] = ctx["current_price"]
                
            from workflows.trading_workflow import create_trading_workflow
            workflow = create_trading_workflow()
            workflow_result = workflow.invoke(initial_state)
            
            decision = workflow_result.get("final_decision", {})

            results[pair] = {
                "full_context": ctx,
                "decision": decision,
            }

            # ── Save Decision to Database ─────────────────────────────
            self.decision_logger.log_decision(pair, signal_result, decision, ctx)

            logger.info(
                f"  ✅ {pair} → {decision.get('decision')} | "
                f"Confidence: {decision.get('confidence')} | "
                f"Bias: {decision.get('bias')} | "
                f"Reason: {decision.get('reason')}"
            )

        return results

    # ─────────────────────────────────────────────────────────────────
    #  STEP IMPLEMENTATIONS
    # ─────────────────────────────────────────────────────────────────

    def _build_sentiment(self, market_data: Dict) -> Dict:
        """Fetch sentiment data lalu analyze via LLM → SentimentEngine."""
        from features.sentiment.sentiment_context_builder import build_sentiment_context
        from features.sentiment.news_social_analysis import analyze_news_social_with_llm
        from features.sentiment.sentiment_engine import SentimentEngine

        sentiment_ctx = build_sentiment_context(
            news_limit=15,
            reddit_limit_per_sub=5,
            twitter_limit_per_user=5,
            eco_days_ahead=7,
            eco_days_back=1,
        )

        llm_result = analyze_news_social_with_llm(
            news_list=sentiment_ctx.get("news", []),
            twitter_data=sentiment_ctx.get("social", {}).get("twitter", {}),
            reddit_data=sentiment_ctx.get("social", {}).get("reddit", {}),
            fear_greed=sentiment_ctx.get("fear_and_greed"),
        )

        result = SentimentEngine.aggregate(
            llm_result=llm_result,
            fear_greed_data=sentiment_ctx.get("fear_and_greed"),
            economic_data=sentiment_ctx.get("economic_calendar"),
        )



        return result

    def _build_correlation(self, market_data: Dict) -> Dict:
        """Hitung return-based correlation antar pair."""
        from features.correlation.correlation import calculate_correlation

        result = calculate_correlation(market_data, timeframe="1h", lookback=120)
        if result.get("error"):
            logger.warning(f"Correlation skipped: {result['error']}")
            return {}
        return result

    def _build_mock_derivatives(self, market_data: Dict) -> Dict:
        """
        Generate proxy derivatives data dari close prices.
        Ganti blok ini dengan live Binance/Bybit futures service jika sudah tersedia.
        """
        from config.settings import get_config
        config = get_config()
        mode = config.get("trading", {}).get("mode", "scalping").lower()
        tf_mock = "15m" if mode == "swing" else "5m"

        derivatives: Dict[str, Dict] = {}
        for pair, tf_data in market_data.items():
            df_mock = tf_data.get(tf_mock, {}).get("aggregated", pd.DataFrame())
            if df_mock.empty:
                continue

            tail = df_mock.tail(24).copy().reset_index(drop=True)

            if "timestamp" in tail.columns:
                ts_base = pd.to_datetime(tail["timestamp"])
            else:
                now_ts = datetime.utcnow()
                ts_base = pd.Series(
                    [now_ts - timedelta(hours=(23 - i)) for i in range(24)]
                )

            funding_rates = np.linspace(0.00005, 0.00015, 24)
            df_funding = pd.DataFrame(
                {"timestamp": ts_base, "funding_rate": funding_rates}
            )

            closes = (
                tail["close"].values
                if "close" in tail.columns
                else np.linspace(70000, 72000, 24)
            )
            open_interests = np.linspace(closes.min() * 0.8, closes.max() * 0.9, 24)
            df_oi = pd.DataFrame(
                {
                    "timestamp": ts_base,
                    "open_interest": open_interests,
                    "oi_change": np.random.normal(0, 1, 24),
                    "close": closes,
                }
            )

            derivatives[pair] = {
                "funding_rate": df_funding,
                "open_interest": df_oi,
            }
        return derivatives

    def _inject_candle_summary(self, ctx: Dict, tf_data: Dict) -> Dict:
        """
        Panggil LLM summarizer untuk mengubah 10 raw candles terakhir
        menjadi narasi singkat per timeframe.
        """
        try:
            from features.candle.candles_summary import CandleSummaryEngine
            summary_result = CandleSummaryEngine.summarize(tf_data, n=10)
            ctx["candle_summary"] = summary_result.get("summaries", {})
        except Exception as e:
            logger.warning(f"Candle summary build failed: {e}")
            ctx["candle_summary"] = {}
        return ctx


    # ─────────────────────────────────────────────────────────────────
    #  DECISION LLM
    def _inject_market_snapshot(self, ctx: Dict, tf_data: Dict) -> Dict:
        """
        Tambahkan MarketSnapshot ke context — ringkasan candle M3/M5/M15/H1
        dengan last_candle, candle summary, RSI, ATR, dan trend regime.
        """
        try:
            from features.snapshot.market_snapshot import build_market_snapshot

            snapshot = build_market_snapshot(tf_data)
            ctx["market_snapshot"] = snapshot
        except Exception as e:
            logger.warning(f"Market snapshot build failed: {e}")
            ctx["market_snapshot"] = {}
        return ctx

    # ─────────────────────────────────────────────────────────────────

    def _call_decision_llm(self, full_context: Dict) -> Dict:
        """Kirim full context ke Decision LLM via factory (Gemini / Groq / Local)."""

        system_prompt = SystemPrompt().get_system_prompt_decision()

        user_input = (
            f"Full Market Context:\n"
            f"{json.dumps(full_context, indent=2, ensure_ascii=False, default=str)}"
        )

        # JSON schema untuk structured output
        decision_schema = {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["BUY", "SELL", "HOLD", "WAIT"],
                    "description": "Trading decision",
                },
                "rr_calculation": {
                    "type": "string",
                    "description": "Step-by-step mathematical calculation for SL and Target based on ATR to ensure minimum 1:3.0 Risk/Reward ratio.",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Confidence level from 0.0 to 1.0",
                },
                "bias": {
                    "type": "string",
                    "enum": [
                        "Strong Bullish",
                        "Moderate Bullish",
                        "Neutral",
                        "Moderate Bearish",
                        "Strong Bearish",
                    ],
                },
                "recommended_timeframe": {
                    "type": "string",
                    "enum": ["M5", "M15", "H1", "Swing"],
                },
                "entry_zone": {
                    "type": "string",
                    "maxLength": 80,
                    "description": "Entry zone or condition",
                },
                "invalidated_if": {
                    "type": "string",
                    "maxLength": 100,
                    "description": "Condition that invalidates the setup",
                },
                "target": {
                    "type": "string",
                    "maxLength": 80,
                    "description": "Target price or zone",
                },
                "stop_loss": {
                    "type": "string",
                    "maxLength": 80,
                    "description": "Stop loss level",
                },
                "risk_reward": {
                    "type": "string",
                    "maxLength": 20,
                    "description": "Risk to reward ratio (example: 1:3.0)",
                },
                "execution_type": {
                    "type": "string",
                    "enum": ["MARKET", "LIMIT"],
                    "description": "MARKET if realtime_price is inside entry_zone, LIMIT if entry_zone requires a pullback",
                },
                "expected_move": {
                    "type": "string",
                    "maxLength": 100,
                    "description": "Expected price movement with timeframe (example: '+2.8% to +4.2% dalam 12 jam')",
                },
                "reason": {
                    "type": "string",
                    "maxLength": 75,
                    "description": "Short, clear, and professional reasoning",
                },
                "key_risks": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 80},
                    "minItems": 1,
                    "maxItems": 3,
                    "description": "List of key risks (maximum 3)",
                },
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
                "execution_type",
                "expected_move",
                "reason",
                "key_risks",
            ],
            "additionalProperties": False,
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
                print('==================result=================')
                print(result)
                print('==================result=================')
                if result and "error" not in result and "decision" in result:
                    logger.info(f"  🤖 Decision LLM Response (Structured):\n{json.dumps(result, indent=2, ensure_ascii=False)}")
                    return result
                
                logger.warning(
                    "structured_generate tidak mengembalikan keputusan valid, fallback ke generate()"
                )
                if result:
                    logger.warning(f"structured_generate result: {json.dumps(result, indent=2, ensure_ascii=False)}")
            except Exception as e:
                logger.warning(
                    f"structured_generate gagal ({e}), fallback ke generate()"
                )

            # Fallback ke generate() biasa
            raw = llm.generate(system_prompt=system_prompt, user_input=user_input)
            logger.info(f"  🤖 Decision LLM Response (Raw Generate):\n{json.dumps(raw, indent=2, ensure_ascii=False)}")
            
            content = raw.get("content", "").strip()

            # Bersihkan markdown
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            # Cari JSON object
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                content = content[start : end + 1]

            try:
                parsed = json.loads(content.strip())
                logger.info(f"  🤖 Decision LLM parsed response successfully.")
                return parsed
            except json.JSONDecodeError as e:
                logger.error(f"Decision LLM tidak mengembalikan JSON yang valid: {e}")
                logger.error(f"Content yang gagal di-parse:\n{content}")
                return self._fallback_decision()

        except Exception as e:
            logger.error(f"Failed to call Decision LLM: {e}", exc_info=True)
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
        }
