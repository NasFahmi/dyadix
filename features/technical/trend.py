"""
features/technical/trend.py

Modul untuk menghitung indikator Trend pada berbagai timeframe.
Fokus utama: H1 (trend & structure), tapi bisa dipakai di semua TF.
"""

import pandas as pd
import pandas_ta as ta
from typing import Dict
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class TrendEngine:
    """
    Engine untuk menghitung semua indikator Trend:
    - Moving Averages (SMA & EMA)
    - Supertrend (sangat direkomendasikan untuk crypto)
    - ADX (trend strength)
    """

    @staticmethod
    def calculate(df: pd.DataFrame, timeframe: str = "1h") -> pd.DataFrame:
        """
        Hitung semua trend indicators.

        Parameters:
            df: DataFrame aggregated (open, high, low, close, volume)
            timeframe: "5m", "15m", "1h" → mempengaruhi parameter indikator

        Returns:
            DataFrame dengan kolom indikator trend
        """
        if df.empty or len(df) < 50:
            logger.warning(f"Data tidak cukup untuk trend calculation di {timeframe}")
            return df

        df = df.copy()

        # ==================== MOVING AVERAGES ====================
        # Short & Medium term (lebih responsif)
        df["sma_20"] = ta.sma(df["close"], length=20)
        df["sma_50"] = ta.sma(df["close"], length=50)

        # Long term (structure)
        df["ema_50"] = ta.ema(df["close"], length=50)
        df["ema_200"] = ta.ema(df["close"], length=200)

        # ==================== SUPERTREND ====================
        # Supertrend sangat bagus untuk crypto karena mengikuti volatility
        supertrend = ta.supertrend(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            length=10,  # periode ATR
            multiplier=3.0,  # multiplier standar untuk crypto
        )

        # Kolom Supertrend mengembalikan: SUPERTREND_10_3.0, SUPERTd_10_3.0, SUPERTl_10_3.0
        df["supertrend"] = supertrend["SUPERT_10_3.0"]
        df["supertrend_direction"] = supertrend[
            "SUPERTd_10_3.0"
        ]  # 1 = uptrend, -1 = downtrend

        # Buat kolom simple "supertrend_trend"
        df["supertrend_trend"] = df["supertrend_direction"].map(
            {1: "Bullish", -1: "Bearish"}
        )

        # ==================== ADX (Trend Strength) ====================
        adx = ta.adx(high=df["high"], low=df["low"], close=df["close"], length=14)
        df["adx"] = adx["ADX_14"]
        df["plus_di"] = adx["DMP_14"]  # +DI
        df["minus_di"] = adx["DMN_14"]  # -DI

        # ==================== TREND REGIME CLASSIFICATION ====================
        # Kombinasi Supertrend + ADX + Price Position
        conditions = [
            (df["supertrend_trend"] == "Bullish") & (df["adx"] > 25),
            (df["supertrend_trend"] == "Bearish") & (df["adx"] > 25),
            (df["adx"] <= 25),
        ]
        choices = ["Strong Uptrend", "Strong Downtrend", "Sideways/Choppy"]

        df["trend_regime"] = pd.Series(
            pd.Categorical.from_codes(
                pd.cut(
                    df["adx"], bins=[0, 25, 100], labels=[2, 0, 1], right=False
                ).cat.codes,
                categories=choices,
            )
        )

        # Override dengan Supertrend jika ADX sedang
        df.loc[
            (df["adx"] <= 25) & (df["supertrend_trend"] == "Bullish"), "trend_regime"
        ] = "Weak Uptrend"
        df.loc[
            (df["adx"] <= 25) & (df["supertrend_trend"] == "Bearish"), "trend_regime"
        ] = "Weak Downtrend"

        # ==================== PRICE POSITION ====================
        df["price_vs_ema50"] = df["close"] > df["ema_50"]
        df["price_vs_ema200"] = df["close"] > df["ema_200"]
        df["price_vs_supertrend"] = df["close"] > df["supertrend"]

        logger.debug(
            f"Trend indicators calculated for {timeframe} | "
            f"Latest regime: {df['trend_regime'].iloc[-1]}"
        )

        return df

    @staticmethod
    def get_latest_summary(df_with_trend: pd.DataFrame, timeframe: str = "1h") -> Dict:
        """
        Buat ringkasan trend untuk LLM (sangat penting untuk context).
        """
        if df_with_trend.empty:
            return {"error": "No data"}

        latest = df_with_trend.iloc[-1]

        summary = {
            "timeframe": timeframe,
            "current_price": round(float(latest["close"]), 2),
            "trend_regime": str(latest["trend_regime"]),
            "supertrend_trend": str(latest.get("supertrend_trend", "Neutral")),
            "adx": round(float(latest.get("adx", 0)), 2),
            "trend_strength": "Strong" if float(latest.get("adx", 0)) > 25 else "Weak",
            # Position relative to key MAs
            "above_ema50": bool(latest.get("price_vs_ema50", False)),
            "above_ema200": bool(latest.get("price_vs_ema200", False)),
            "above_supertrend": bool(latest.get("price_vs_supertrend", False)),
            # Distance to Supertrend
            "distance_to_supertrend_pct": round(
                float(
                    (latest["close"] - latest.get("supertrend", latest["close"]))
                    / latest["close"]
                    * 100
                ),
                2,
            )
            if "supertrend" in latest
            else 0.0,
            "calculated_at": datetime.utcnow().isoformat(),
        }

        return summary


# Helper function
def calculate_trend_features(
    df: pd.DataFrame, timeframe: str = "1h"
) -> tuple[pd.DataFrame, Dict]:
    """
    Fungsi utama yang dipanggil dari pipeline.
    Return: (df_with_features, latest_summary)
    """
    df_result = TrendEngine.calculate(df, timeframe)
    summary = TrendEngine.get_latest_summary(df_result, timeframe)
    return df_result, summary
