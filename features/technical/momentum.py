"""
features/technical/momentum.py

Fokus utama: M15 (Momentum Confirmation)
Secondary: M5 (Early Momentum Signal)
"""

import pandas as pd
import pandas_ta as ta
from typing import Dict, Tuple
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MomentumEngine:
    @staticmethod
    def calculate(df: pd.DataFrame, timeframe: str = "15m") -> pd.DataFrame:
        """Hitung momentum indicators"""
        if df.empty or len(df) < 30:
            logger.warning(f"Data tidak cukup untuk momentum di {timeframe}")
            return df

        df = df.copy()

        # Core Momentum Indicators
        df["rsi"] = ta.rsi(df["close"], length=14)

        macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
        df = pd.concat([df, macd], axis=1)
        df["macd_histogram"] = df["MACD_12_26_9"] - df["MACDs_12_26_9"]

        # Stochastic RSI (sangat bagus untuk crypto)
        stoch = ta.stochrsi(df["close"], length=14, rsi_length=14, k=3, d=3)
        df = pd.concat([df, stoch], axis=1)

        df["cci"] = ta.cci(df["high"], df["low"], df["close"], length=20)

        # Regime classification (khusus untuk summary)
        df["rsi_regime"] = pd.cut(
            df["rsi"],
            bins=[0, 30, 45, 55, 70, 100],
            labels=["Oversold", "Bearish", "Neutral", "Bullish", "Overbought"],
        )

        return df

    @staticmethod
    def get_latest_summary(df: pd.DataFrame, timeframe: str = "15m") -> Dict:
        if df.empty:
            return {"error": "No data"}

        latest = df.iloc[-1]

        summary = {
            "timeframe": timeframe,
            # RSI Group (paling penting)
            "rsi": round(float(latest.get("rsi", 50)), 2),
            "rsi_regime": str(latest.get("rsi_regime", "Neutral")),
            # MACD Group
            "macd_histogram": round(float(latest.get("macd_histogram", 0)), 4),
            "macd_line": round(float(latest.get("MACD_12_26_9", 0)), 4),
            "macd_signal_line": round(float(latest.get("MACDs_12_26_9", 0)), 4),
            "macd_crossover": "Bullish"
            if latest.get("MACD_12_26_9", 0) > latest.get("MACDs_12_26_9", 0)
            else "Bearish",
            # Stochastic RSI
            "stoch_rsi_k": round(float(latest.get("STOCHRSIk_14_14_3_3", 50)), 2),
            "stoch_rsi_d": round(float(latest.get("STOCHRSId_14_14_3_3", 50)), 2),
            # CCI dengan handling nilai ekstrem
            "cci": round(float(latest.get("cci", 0)), 2),
            # Overall Momentum Bias
            "momentum_bias": "Bullish"
            if (latest.get("macd_histogram", 0) > 0 and latest.get("rsi", 50) > 50)
            else "Bearish"
            if (latest.get("macd_histogram", 0) < 0 and latest.get("rsi", 50) < 50)
            else "Neutral",
            "calculated_at": datetime.utcnow().isoformat(),
        }

        return summary


# Helper
def calculate_momentum_features(
    df: pd.DataFrame, timeframe: str = "15m"
) -> Tuple[pd.DataFrame, Dict]:
    df_result = MomentumEngine.calculate(df, timeframe)
    summary = MomentumEngine.get_latest_summary(df_result, timeframe)
    return df_result, summary
