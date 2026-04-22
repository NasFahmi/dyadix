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

        # Pastikan timeframe 1d selalu ada untuk daily bias
        if "1d" not in self.market_service.timeframes:
            self.market_service.timeframes.append("1d")

    # ─────────────────────────────────────────────────────────────────
    #  ENTRY POINT
    # ─────────────────────────────────────────────────────────────────

    def run(self) -> Dict[str, Any]:
        """
        Jalankan pipeline lengkap untuk semua pair yang terdaftar di settings.yml.
        Returns dict {pair: {"full_context": ..., "decision": ...}}
        """
        logger.info("=" * 60)
        logger.info("  Dyadix Main Pipeline Started")
        logger.info("=" * 60)

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

        # ── Decision LLM per pair ─────────────────────────────────────
        results: Dict[str, Any] = {}
        for pair, ctx in full_contexts.items():
            if "error" in ctx:
                logger.error(f"  ❌ {pair} context error: {ctx['error']}")
                results[pair] = ctx
                continue

            # Tambah last_candles ke context agar LLM bisa baca candlestick terbaru
            ctx = self._inject_last_candles(ctx, market_data.get(pair, {}))

            # Tambah market snapshot (ringkasan candle M5/M15/H1 untuk precision entry)
            ctx = self._inject_market_snapshot(ctx, market_data.get(pair, {}))

            # Debug: Print full context before sending to LLM
            print("\n" + "=" * 60)
            print(f" DEBUG: PROMPTING DECISION LLM FOR {pair}")
            print("=" * 60)
            print(json.dumps(ctx, indent=2, default=str, ensure_ascii=True))
            print("=" * 60 + "\n")

            logger.info(f"  ⚙  Calling Decision LLM for {pair}...")
            decision = self._call_decision_llm(ctx)

            results[pair] = {
                "full_context": ctx,
                "decision": decision,
            }

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

        return SentimentEngine.aggregate(
            llm_result=llm_result,
            fear_greed_data=sentiment_ctx.get("fear_and_greed"),
            economic_data=sentiment_ctx.get("economic_calendar"),
        )

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
        Generate proxy derivatives data dari M5 close prices.
        Ganti blok ini dengan live Binance/Bybit futures service jika sudah tersedia.
        """
        derivatives: Dict[str, Dict] = {}
        for pair, tf_data in market_data.items():
            df_m5 = tf_data.get("5m", {}).get("aggregated", pd.DataFrame())
            if df_m5.empty:
                continue

            tail = df_m5.tail(24).copy().reset_index(drop=True)

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

    def _inject_last_candles(self, ctx: Dict, tf_data: Dict, n: int = 10) -> Dict:
        """
        Tambahkan data candlestick terbaru (OHLCV) ke dalam context
        agar decision LLM bisa membaca struktur candle terakhir.
        """
        last_candles: Dict[str, Any] = {}
        for tf in ["3m", "5m", "15m", "1h"]:
            df = tf_data.get(tf, {}).get("aggregated", pd.DataFrame())
            if df.empty:
                continue
            tail = df.tail(n).copy()
            # Pastikan serializable
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
                "key_risks"
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
                    "structured_generate tidak mengembalikan keputusan valid, fallback ke generate()"
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
            # Cari JSON object
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                content = content[start : end + 1]

            try:
                return json.loads(content.strip())
            except json.JSONDecodeError:
                logger.error("Decision LLM tidak mengembalikan JSON yang valid")
                logger.debug(f"Raw LLM output: {content[:300]}")
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
        }
