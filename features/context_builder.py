"""
aggregation/context_builder.py

Modul utama untuk membangun context teknikal yang siap dikirim ke LLM.
Menggabungkan: Daily Bias + Trend (H1) + Momentum (M15) + Volatility (M5) + Price Action (M5)
"""

import pandas as pd
from typing import Dict, Any
import logging
from datetime import datetime

from features.technical.daily_bias import get_daily_bias
from features.technical.trend import calculate_trend_features
from features.technical.momentum import calculate_momentum_features
from features.technical.volatility import calculate_volatility_features
from features.technical.price_action import calculate_price_action_features

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Class utama untuk membangun technical context yang ringkas dan actionable.
    """

    def __init__(self):
        self.name = "Technical Context Builder"

    def build_technical_context(self, market_data: Dict) -> Dict:
        """
        Membangun context teknikal untuk semua pair.

        Parameters:
            market_data: Dict hasil dari MarketService.fetch_ohlcv_all()
                Contoh struktur:
                {
                    "BTCUSDT": {
                        "5m":  {"aggregated": df},
                        "15m": {"aggregated": df},
                        "1h":  {"aggregated": df},
                        "1d":  {"aggregated": df}   # optional
                    },
                    ...
                }

        Returns:
            Dict berisi context teknikal yang siap dikirim ke LLM
        """
        technical_context = {}

        for pair, tf_data in market_data.items():
            try:
                # Ambil DataFrame aggregated per timeframe
                df_1h = tf_data.get("1h", {}).get("aggregated", pd.DataFrame())
                df_15m = tf_data.get("15m", {}).get("aggregated", pd.DataFrame())
                df_5m = tf_data.get("5m", {}).get("aggregated", pd.DataFrame())
                df_daily = tf_data.get("1d", {}).get("aggregated", pd.DataFrame())

                # ==================== HITUNG SETIAP ENGINE ====================

                # 1. Daily Bias
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

                # 2. Trend (H1)
                _, trend_summary = calculate_trend_features(df_1h, timeframe="1h")

                # 3. Momentum (M15)
                _, momentum_summary = calculate_momentum_features(
                    df_15m, timeframe="15m"
                )

                # 4. Volatility (M5)
                _, volatility_summary = calculate_volatility_features(
                    df_5m, timeframe="5m"
                )

                # 5. Price Action (M5)
                _, pa_summary = calculate_price_action_features(df_5m, timeframe="5m")

                # ==================== GABUNGKAN MENJADI SATU CONTEXT ====================
                pair_context = {
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
                    # Ringkasan keseluruhan (untuk membantu LLM)
                    "overall_technical_bias": self._get_overall_bias(
                        daily_bias, trend_summary, momentum_summary, pa_summary
                    ),
                    "key_levels": {
                        "pd_high": daily_bias.get("previous_day_high"),
                        "pd_low": daily_bias.get("previous_day_low"),
                        "last_swing_high": pa_summary.get("last_swing_high"),
                        "last_swing_low": pa_summary.get("last_swing_low"),
                    },
                }

                technical_context[pair] = pair_context

                logger.info(f"✅ Technical context built successfully for {pair}")

            except Exception as e:
                logger.error(f"❌ Failed to build technical context for {pair}: {e}")
                technical_context[pair] = {
                    "pair": pair,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                }

        return technical_context

    def _get_overall_bias(
        self, daily_bias: Dict, trend: Dict, momentum: Dict, pa: Dict
    ) -> str:
        """
        Logic sederhana untuk menentukan overall technical bias.
        Bisa dikembangkan lebih kompleks nanti.
        """
        daily = daily_bias.get("bias", "Neutral")
        trend_regime = trend.get("trend_regime", "Neutral")
        momentum_bias = momentum.get("momentum_bias", "Neutral")
        pa_bias = pa.get("pa_bias", "Neutral")

        scores = {"Bullish": 0, "Bearish": 0, "Neutral": 0}

        # Bobot sederhana
        if daily == "Bullish":
            scores["Bullish"] += 3
        elif daily == "Bearish":
            scores["Bearish"] += 3

        if "Uptrend" in trend_regime or "Bullish" in trend_regime:
            scores["Bullish"] += 2
        elif "Downtrend" in trend_regime or "Bearish" in trend_regime:
            scores["Bearish"] += 2

        if momentum_bias == "Bullish":
            scores["Bullish"] += 2
        elif momentum_bias == "Bearish":
            scores["Bearish"] += 2

        if "Bullish" in pa_bias:
            scores["Bullish"] += 1
        elif "Bearish" in pa_bias:
            scores["Bearish"] += 1

        # Tentukan pemenang
        if scores["Bullish"] > scores["Bearish"] + 1:
            return "Strong Bullish"
        elif scores["Bearish"] > scores["Bullish"] + 1:
            return "Strong Bearish"
        elif scores["Bullish"] > scores["Bearish"]:
            return "Moderate Bullish"
        elif scores["Bearish"] > scores["Bullish"]:
            return "Moderate Bearish"
        else:
            return "Neutral"

    def build_full_context(
        self,
        market_data: Dict,
        sentiment_context: Dict = None,
        economic_context: Dict = None,
    ) -> Dict:
        """
        (Opsional) Gabungkan technical context dengan sentiment & economic.
        """
        technical = self.build_technical_context(market_data)

        full_context = {
            "timestamp": datetime.utcnow().isoformat(),
            "technical": technical,
        }

        if sentiment_context:
            full_context["sentiment"] = sentiment_context
        if economic_context:
            full_context["economic"] = economic_context

        return full_context


# Helper function untuk kemudahan import
def build_technical_context(market_data: Dict) -> Dict:
    """Helper function"""
    builder = ContextBuilder()
    return builder.build_technical_context(market_data)
