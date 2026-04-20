"""
features/context_builder.py

Modul utama untuk membangun FULL context yang siap dikirim ke LLM.
Menggabungkan:
  - Technical  : Daily Bias + Trend (H1) + Momentum (M15) + Volatility (M5) + Price Action (M5)
  - Sentiment  : Hasil SentimentEngine (LLM News/Social + Fear & Greed + Economic)
  - Derivatives: Funding Rate + Open Interest per pair
  - Liquidity  : Swing Pool + Sweep per pair
  - Correlation: Korelasi antar pair (global)
"""

import pandas as pd
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

from features.technical.daily_bias import get_daily_bias
from features.technical.trend import calculate_trend_features
from features.technical.momentum import calculate_momentum_features
from features.technical.volatility import calculate_volatility_features
from features.technical.price_action import calculate_price_action_features
from features.derivatives.derivatives import DerivativesEngine
from features.liquidity.liquidity import LiquidityEngine

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Label helpers
# ─────────────────────────────────────────────


def _sentiment_to_score(label: str) -> int:
    """Konversi label sentiment ke skor numerik 0-8."""
    mapping = {
        "Very Bullish": 8,
        "Strong Bullish": 7,
        "Bullish": 6,
        "Moderate Bullish": 5,
        "Neutral": 4,
        "Moderate Bearish": 3,
        "Bearish": 2,
        "Strong Bearish": 1,
        "Very Bearish": 0,
    }
    for key in mapping:
        if key.lower() in label.lower():
            return mapping[key]
    return 4  # default Neutral


def _score_to_bias_label(score: float) -> str:
    """Konversi skor weighted ke label final bias."""
    if score >= 7.0:
        return "Strong Bullish"
    if score >= 5.5:
        return "Moderate Bullish"
    if score >= 4.5:
        return "Neutral"
    if score >= 3.0:
        return "Moderate Bearish"
    return "Strong Bearish"


# ─────────────────────────────────────────────
#  ContextBuilder
# ─────────────────────────────────────────────


class ContextBuilder:
    """
    Class utama untuk membangun full aggregated context per pair.
    """

    def __init__(self):
        self.name = "Full Context Builder"

    # ── 1. Technical only (backward compat) ──────────────────────────────────

    def build_technical_context(self, market_data: Dict) -> Dict:
        """
        Membangun context teknikal untuk semua pair.

        Parameters:
            market_data: Dict hasil dari MarketService.fetch_ohlcv_all()
        Returns:
            Dict {pair: technical_context}
        """
        technical_context = {}
        for pair, tf_data in market_data.items():
            try:
                pair_ctx = self._build_pair_technical(pair, tf_data)
                technical_context[pair] = pair_ctx
                logger.info(f"✅ Technical context built for {pair}")
            except Exception as e:
                logger.error(f"❌ Failed to build technical context for {pair}: {e}")
                technical_context[pair] = {
                    "pair": pair,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                }
        return technical_context

    # ── 2. Full aggregation ───────────────────────────────────────────────────

    def build_full_context(
        self,
        market_data: Dict,
        sentiment_result: Dict = None,
        derivatives_data: Dict = None,
        correlation_data: Dict = None,
        target_pairs: Optional[List[str]] = None,
    ) -> Dict:
        """
        Membangun full context per pair dengan semua engine terintegrasi.

        Parameters:
            market_data      : hasil MarketService.fetch_ohlcv_all()
            sentiment_result : hasil SentimentEngine.aggregate() — bersifat global
            derivatives_data : {pair: {"funding_rate": df, "open_interest": df}}
            correlation_data : hasil CorrelationEngine.calculate()
            target_pairs     : List pair yang ingin dibangun context-nya (jika None, semua di market_data)

        Returns:
            { ... }
        """
        full_context: Dict[str, Any] = {}

        for pair, tf_data in market_data.items():
            # Filter hanya pair yang ingin ditradingkan (target_pairs)
            if target_pairs is not None and pair not in target_pairs:
                continue
            try:
                # ── technical ─────────────────────────────────────────────
                tech = self._build_pair_technical(pair, tf_data)

                # ── sentiment (global, di-inject ke semua pair) ───────────
                sentiment = sentiment_result or {}

                # ── derivatives per pair ──────────────────────────────────
                pair_deriv_data = (derivatives_data or {}).get(pair, {})
                if pair_deriv_data:
                    derivatives = DerivativesEngine.calculate(pair_deriv_data, pair)
                else:
                    derivatives = {}

                # ── liquidity per pair ────────────────────────────────────
                df_5m = tf_data.get("5m", {}).get("aggregated", pd.DataFrame())
                daily_bias_raw = tech.get("daily_bias", {})
                if not df_5m.empty:
                    liq_result = LiquidityEngine.calculate(
                        df=df_5m, daily_bias=daily_bias_raw, timeframe="5m"
                    )
                    liquidity = LiquidityEngine.get_latest_summary(liq_result)
                else:
                    liquidity = {"error": "No 5m data for liquidity"}

                # ── correlation (global, beri slice per pair) ─────────────
                correlation = {}
                if correlation_data and not correlation_data.get("error"):
                    btc_corr = correlation_data.get("btc_correlation", {})
                    correlation = {
                        "btc_correlation": btc_corr.get(pair),
                        "insights": correlation_data.get("insights", []),
                    }

                # ── final_bias (weighted) ─────────────────────────────────
                final_bias = self._compute_final_bias(
                    tech, sentiment, derivatives, liquidity
                )

                # ── key_levels (gabungan technical + liquidity) ───────────
                key_levels = self._merge_key_levels(tech, liquidity)

                # ── overall_context_summary ───────────────────────────────
                summary = self._generate_summary(
                    pair, tech, sentiment, derivatives, liquidity, final_bias
                )

                full_context[pair] = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "pair": pair,
                    "technical": {
                        "daily_bias": tech.get("daily_bias"),
                        "trend_h1": tech.get("trend_h1"),
                        "momentum_m15": tech.get("momentum_m15"),
                        "volatility_m5": tech.get("volatility_m5"),
                        "price_action_m5": tech.get("price_action_m5"),
                        "overall_technical_bias": tech.get("overall_technical_bias"),
                    },
                    "sentiment": sentiment,
                    "derivatives": derivatives,
                    "liquidity": liquidity,
                    "correlation": correlation,
                    "overall_context_summary": summary,
                    "final_bias": final_bias,
                    "key_levels": key_levels,
                }

                logger.info(
                    f"✅ Full context built for {pair} → final_bias: {final_bias}"
                )

            except Exception as e:
                logger.error(f"❌ Failed to build full context for {pair}: {e}")
                full_context[pair] = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "pair": pair,
                    "error": str(e),
                }

        return full_context

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_pair_technical(self, pair: str, tf_data: Dict) -> Dict:
        """Hitung semua engine teknikal untuk satu pair."""
        df_1h = tf_data.get("1h", {}).get("aggregated", pd.DataFrame())
        df_15m = tf_data.get("15m", {}).get("aggregated", pd.DataFrame())
        df_5m = tf_data.get("5m", {}).get("aggregated", pd.DataFrame())
        df_3m = tf_data.get("3m", {}).get("aggregated", pd.DataFrame())
        df_daily = tf_data.get("1d", {}).get("aggregated", pd.DataFrame())

        # Daily Bias
        daily_bias = (
            get_daily_bias(df_daily, pair)
            if not df_daily.empty
            else {
                "bias": "Neutral",
                "strength": "Unknown",
                "previous_day_high": None,
                "previous_day_low": None,
                "previous_day_close": None,
            }
        )

        # Trend H1
        df_1h_new, trend_summary = (
            calculate_trend_features(df_1h, timeframe="1h")
            if not df_1h.empty
            else (pd.DataFrame(), {})
        )
        if not df_1h_new.empty:
            tf_data["1h"]["aggregated"] = df_1h_new

        # Momentum M15
        df_15m_new, momentum_summary = (
            calculate_momentum_features(df_15m, timeframe="15m")
            if not df_15m.empty
            else (pd.DataFrame(), {})
        )
        if not df_15m_new.empty:
            tf_data["15m"]["aggregated"] = df_15m_new

        # Volatility M5
        df_5m_new, volatility_summary = (
            calculate_volatility_features(df_5m, timeframe="5m")
            if not df_5m.empty
            else (pd.DataFrame(), {})
        )
        if not df_5m_new.empty:
            tf_data["5m"]["aggregated"] = df_5m_new

        # Momentum M5 (Baru ditambahkan agar snapshot M5 punya RSI)
        df_5m_mom, _ = (
            calculate_momentum_features(tf_data["5m"]["aggregated"], timeframe="5m")
            if not tf_data.get("5m", {}).get("aggregated", pd.DataFrame()).empty
            else (pd.DataFrame(), {})
        )
        if not df_5m_mom.empty:
            tf_data["5m"]["aggregated"] = df_5m_mom

        # Price Action M5
        df_5m_pa, pa_summary = (
            calculate_price_action_features(tf_data["5m"]["aggregated"], timeframe="5m")
            if not tf_data.get("5m", {}).get("aggregated", pd.DataFrame()).empty
            else (pd.DataFrame(), {})
        )
        if not df_5m_pa.empty:
            tf_data["5m"]["aggregated"] = df_5m_pa

        # Optional: M3 Momentum/Volatility calculation (agar Snapshot tidak null)
        if not df_3m.empty:
            df_3m_new, _ = calculate_momentum_features(df_3m, timeframe="3m")
            tf_data["3m"]["aggregated"] = df_3m_new
            # Update volatility juga untuk ATR di M3 jika diperlukan
            df_3m_vol, _ = calculate_volatility_features(
                tf_data["3m"]["aggregated"], timeframe="3m"
            )
            tf_data["3m"]["aggregated"] = df_3m_vol

        overall_bias = self._get_overall_technical_bias(
            daily_bias, trend_summary, momentum_summary, pa_summary
        )

        return {
            "pair": pair,
            "timestamp": datetime.utcnow().isoformat(),
            "daily_bias": {
                "bias": daily_bias.get("bias", "Neutral"),
                "strength": daily_bias.get("strength", "Unknown"),
                "candle_pattern": daily_bias.get("candle_pattern", "Normal"),
                "previous_day_high": daily_bias.get("previous_day_high"),
                "previous_day_low": daily_bias.get("previous_day_low"),
                "previous_day_close": daily_bias.get("previous_day_close"),
                "previous_day_range": daily_bias.get("previous_day_range"),
            },
            "trend_h1": trend_summary,
            "momentum_m15": momentum_summary,
            "volatility_m5": volatility_summary,
            "price_action_m5": pa_summary,
            "overall_technical_bias": overall_bias,
            "key_levels": {
                "pd_high": daily_bias.get("previous_day_high"),
                "pd_low": daily_bias.get("previous_day_low"),
                "last_swing_high": pa_summary.get("last_swing_high"),
                "last_swing_low": pa_summary.get("last_swing_low"),
            },
        }

    def _get_overall_technical_bias(
        self, daily_bias: Dict, trend: Dict, momentum: Dict, pa: Dict
    ) -> str:
        """Weighted scoring untuk technical bias (sama seperti sebelumnya)."""
        scores = {"Bullish": 0, "Bearish": 0}

        daily = daily_bias.get("bias", "Neutral")
        if daily == "Bullish":
            scores["Bullish"] += 3
        elif daily == "Bearish":
            scores["Bearish"] += 3

        trend_regime = trend.get("trend_regime", "Neutral")
        if "Uptrend" in trend_regime or "Bullish" in trend_regime:
            scores["Bullish"] += 2
        elif "Downtrend" in trend_regime or "Bearish" in trend_regime:
            scores["Bearish"] += 2

        momentum_bias = momentum.get("momentum_bias", "Neutral")
        if momentum_bias == "Bullish":
            scores["Bullish"] += 2
        elif momentum_bias == "Bearish":
            scores["Bearish"] += 2

        pa_bias = pa.get("pa_bias", "Neutral")
        if "Bullish" in pa_bias:
            scores["Bullish"] += 1
        elif "Bearish" in pa_bias:
            scores["Bearish"] += 1

        b, be = scores["Bullish"], scores["Bearish"]
        if b > be + 1:
            return "Strong Bullish"
        if be > b + 1:
            return "Strong Bearish"
        if b > be:
            return "Moderate Bullish"
        if be > b:
            return "Moderate Bearish"
        return "Neutral"

    def _compute_final_bias(
        self,
        tech: Dict,
        sentiment: Dict,
        derivatives: Dict,
        liquidity: Dict,
    ) -> str:
        """
        Weighted final bias dari semua komponen:
        Technical  40%
        Sentiment  30%
        Derivatives 20%
        Liquidity  10%
        """
        tech_label = tech.get("overall_technical_bias", "Neutral")
        sent_label = sentiment.get("overall_sentiment", "Neutral")
        deriv_label = derivatives.get("derivatives_sentiment", "Neutral")
        liq_label = liquidity.get("liquidity_sentiment", "Neutral")

        tech_score = _sentiment_to_score(tech_label)
        sent_score = _sentiment_to_score(sent_label)
        deriv_score = _sentiment_to_score(deriv_label)
        liq_score = _sentiment_to_score(liq_label)

        weighted = (
            tech_score * 0.40
            + sent_score * 0.30
            + deriv_score * 0.20
            + liq_score * 0.10
        )
        return _score_to_bias_label(weighted)

    def _merge_key_levels(self, tech: Dict, liquidity: Dict) -> Dict:
        """Gabungkan key levels dari technical dan liquidity."""
        tech_levels = tech.get("key_levels", {})
        liq_levels = liquidity.get("key_levels", {})
        liq_pools = liquidity.get("liquidity_pools", {})

        return {
            "pd_high": tech_levels.get("pd_high"),
            "pd_low": tech_levels.get("pd_low"),
            "last_swing_high": tech_levels.get("last_swing_high"),
            "last_swing_low": tech_levels.get("last_swing_low"),
            "liquidity_pdh": liq_levels.get("pdh"),
            "liquidity_pdl": liq_levels.get("pdl"),
            "resistance_pools": [p["price"] for p in liq_pools.get("highs", [])],
            "support_pools": [p["price"] for p in liq_pools.get("lows", [])],
        }

    def _generate_summary(
        self,
        pair: str,
        tech: Dict,
        sentiment: Dict,
        derivatives: Dict,
        liquidity: Dict,
        final_bias: str,
    ) -> str:
        """Teks ringkas yang menggambarkan kondisi pasar saat ini untuk pair ini."""
        parts = []

        # Technical
        t_bias = tech.get("overall_technical_bias", "Neutral")
        trend = tech.get("trend_h1", {}).get("trend_regime", "Unknown")
        parts.append(f"{pair} secara teknikal {t_bias} dengan trend H1 {trend}")

        # Sentiment
        s_label = sentiment.get("overall_sentiment", "Neutral")
        s_score = sentiment.get("sentiment_score", 50)
        fg_val = sentiment.get("components", {}).get("fear_greed", {}).get("value")
        fg_str = f", F&G {fg_val}" if fg_val is not None else ""
        parts.append(f"Sentiment pasar {s_label} (skor {s_score}{fg_str})")

        # Derivatives
        d_label = derivatives.get("derivatives_sentiment", "")
        if d_label:
            fr = derivatives.get("funding_rate", {}).get("latest")
            fr_str = f" | funding rate {fr:.4%}" if fr is not None else ""
            parts.append(f"Derivatives {d_label}{fr_str}")

        # Liquidity
        liq_label = liquidity.get("liquidity_sentiment", "")
        if liq_label and liq_label != "Neutral":
            parts.append(f"Liquidity: {liq_label}")

        parts.append(f"→ Final Bias: {final_bias}")
        return " | ".join(parts)


# ─────────────────────────────────────────────
#  Module-level helpers
# ─────────────────────────────────────────────


def build_technical_context(market_data: Dict) -> Dict:
    """Helper backward-compatible untuk technical-only context."""
    return ContextBuilder().build_technical_context(market_data)


def build_full_context(
    market_data: Dict,
    sentiment_result: Dict = None,
    derivatives_data: Dict = None,
    correlation_data: Dict = None,
    target_pairs: Optional[List[str]] = None,
) -> Dict:
    """Helper untuk full aggregated context."""
    return ContextBuilder().build_full_context(
        market_data=market_data,
        sentiment_result=sentiment_result,
        derivatives_data=derivatives_data,
        correlation_data=correlation_data,
        target_pairs=target_pairs,
    )
