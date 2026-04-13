"""
features/technical/price_action.py

Modul untuk mendeteksi Price Action patterns dan struktur harga.
Fokus utama: M5 & M15 (candle patterns, swing points, dan key levels)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class PriceActionEngine:
    """
    Engine untuk mendeteksi berbagai Price Action patterns.
    """

    @staticmethod
    def calculate(df: pd.DataFrame, timeframe: str = "5m") -> pd.DataFrame:
        """
        Hitung price action features dan pattern detection.
        """
        if df.empty or len(df) < 20:
            logger.warning(f"Data tidak cukup untuk price action di {timeframe}")
            return df

        df = df.copy()

        # ==================== BASIC CANDLE INFORMATION ====================
        df["body"] = df["close"] - df["open"]
        df["body_abs"] = abs(df["body"])
        df["upper_shadow"] = df["high"] - df[["open", "close"]].max(axis=1)
        df["lower_shadow"] = df[["open", "close"]].min(axis=1) - df["low"]
        df["range"] = df["high"] - df["low"]

        # Candle type
        df["candle_type"] = np.where(
            df["body"] > 0, "Bullish", np.where(df["body"] < 0, "Bearish", "Doji")
        )

        # ==================== CANDLE PATTERNS ====================
        # 1. Pinbar / Hammer / Shooting Star
        df["is_pinbar"] = (
            (df["lower_shadow"] > 2 * df["body_abs"])
            & (df["upper_shadow"] < 0.3 * df["body_abs"])
        ) | (
            (df["upper_shadow"] > 2 * df["body_abs"])
            & (df["lower_shadow"] < 0.3 * df["body_abs"])
        )

        # 2. Hammer (bullish reversal)
        df["is_hammer"] = (
            (df["lower_shadow"] > 2 * df["body_abs"])
            & (df["upper_shadow"] < 0.3 * df["body_abs"])
            & (df["body"] > 0)
        )

        # 3. Shooting Star (bearish reversal)
        df["is_shooting_star"] = (
            (df["upper_shadow"] > 2 * df["body_abs"])
            & (df["lower_shadow"] < 0.3 * df["body_abs"])
            & (df["body"] < 0)
        )

        # 4. Engulfing
        prev_body = df["body"].shift(1)
        prev_open = df["open"].shift(1)
        prev_close = df["close"].shift(1)

        df["is_bullish_engulfing"] = (
            (df["body"] > 0)
            & (prev_body < 0)
            & (df["close"] > prev_open)
            & (df["open"] < prev_close)
        )

        df["is_bearish_engulfing"] = (
            (df["body"] < 0)
            & (prev_body > 0)
            & (df["close"] < prev_open)
            & (df["open"] > prev_close)
        )

        # 5. Inside Bar
        df["is_inside_bar"] = (df["high"] < df["high"].shift(1)) & (
            df["low"] > df["low"].shift(1)
        )

        # ==================== SWING HIGH & SWING LOW ====================
        # Simple swing detection (last 5 candles)
        window = 5
        df["swing_high"] = (
            df["high"] == df["high"].rolling(window=window, center=True).max()
        )
        df["swing_low"] = (
            df["low"] == df["low"].rolling(window=window, center=True).min()
        )

        # Last swing levels
        last_swing_high = (
            df[df["swing_high"]]["high"].iloc[-1] if any(df["swing_high"]) else None
        )
        last_swing_low = (
            df[df["swing_low"]]["low"].iloc[-1] if any(df["swing_low"]) else None
        )

        df["last_swing_high"] = last_swing_high
        df["last_swing_low"] = last_swing_low

        # ==================== STRUCTURE (Break of Structure) ====================
        # Simple BOS (Break of Structure)
        df["bos_bullish"] = df["high"] > df["high"].shift(1).rolling(10).max()
        df["bos_bearish"] = df["low"] < df["low"].shift(1).rolling(10).max()

        logger.debug(
            f"Price Action calculated for {timeframe} | "
            f"Latest candle: {df['candle_type'].iloc[-1]} | "
            f"Pinbar: {df['is_pinbar'].iloc[-1]}"
        )

        return df

    @staticmethod
    def get_latest_summary(df: pd.DataFrame, timeframe: str = "5m") -> Dict:
        """
        Ringkasan Price Action yang ringkas dan actionable untuk LLM.
        """
        if df.empty:
            return {"error": "No data"}

        latest = df.iloc[-1]

        summary = {
            "timeframe": timeframe,
            "current_candle_type": str(latest.get("candle_type", "Neutral")),
            "body_size_pct": round(
                float(latest.get("body_abs", 0) / latest.get("range", 1) * 100), 2
            )
            if latest.get("range", 0) > 0
            else 0.0,
            # Key Patterns
            "is_pinbar": bool(latest.get("is_pinbar", False)),
            "is_hammer": bool(latest.get("is_hammer", False)),
            "is_shooting_star": bool(latest.get("is_shooting_star", False)),
            "is_bullish_engulfing": bool(latest.get("is_bullish_engulfing", False)),
            "is_bearish_engulfing": bool(latest.get("is_bearish_engulfing", False)),
            "is_inside_bar": bool(latest.get("is_inside_bar", False)),
            # Swing Levels
            "last_swing_high": round(float(latest.get("last_swing_high", 0)), 4)
            if pd.notna(latest.get("last_swing_high"))
            else None,
            "last_swing_low": round(float(latest.get("last_swing_low", 0)), 4)
            if pd.notna(latest.get("last_swing_low"))
            else None,
            # Structure
            "recent_bos_bullish": bool(latest.get("bos_bullish", False)),
            "recent_bos_bearish": bool(latest.get("bos_bearish", False)),
            # Interpretation
            "pa_bias": "Bullish Reversal"
            if latest.get("is_hammer") or latest.get("is_bullish_engulfing")
            else "Bearish Reversal"
            if latest.get("is_shooting_star") or latest.get("is_bearish_engulfing")
            else "Neutral",
            "calculated_at": datetime.utcnow().isoformat(),
        }

        return summary


# Helper function
def calculate_price_action_features(
    df: pd.DataFrame, timeframe: str = "5m"
) -> Tuple[pd.DataFrame, Dict]:
    """
    Fungsi utama untuk dipanggil dari pipeline.
    """
    df_result = PriceActionEngine.calculate(df, timeframe)
    summary = PriceActionEngine.get_latest_summary(df_result, timeframe)
    return df_result, summary
