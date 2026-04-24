"""
features/market_snapshot.py

Membuat Market Snapshot yang ringkas dan optimal untuk dikirim ke LLM Decision Engine.
Menggunakan timeframe: M3, M5, M15, H1.
"""

import pandas as pd
from typing import Dict, Any
import logging
from datetime import datetime

from features.technical.momentum import MomentumEngine
from features.technical.volatility import VolatilityEngine
from features.technical.trend import TrendEngine

logger = logging.getLogger(__name__)


class MarketSnapshotBuilder:
    """
    Membuat snapshot pasar yang ringkas dari berbagai timeframe.
    """

    @staticmethod
    def build(market_data: Dict) -> Dict[str, Any]:
        """
        market_data: dict dari MarketService untuk satu pair
        Contoh: market_data[pair] = {"5m": {...}, "15m": {...}, ...}
        """
        snapshot = {
            "current_price": None,
            "timestamp_utc": datetime.utcnow().isoformat(),
            "m3": {},
            "m5": {},
            "m15": {},
            "h1": {},
        }

        # ==================== M3 (Precision Entry) ====================
        df_m3 = MarketSnapshotBuilder._get_dataframe(market_data, "3m")
        if df_m3 is not None and not df_m3.empty:
            df_m3 = MomentumEngine.calculate(df_m3, "3m")
            last = df_m3.iloc[-1]
            snapshot["current_price"] = round(float(last["close"]), 4)
            snapshot["m3"] = {
                "last_candle": {
                    "open": round(float(last["open"]), 4),
                    "high": round(float(last["high"]), 4),
                    "low": round(float(last["low"]), 4),
                    "close": round(float(last["close"]), 4),
                },
                "last_6_candles_summary": MarketSnapshotBuilder._summarize_candles(
                    df_m3, 6
                ),
                "rsi": round(float(last.get("rsi", 50)), 2)
                if "rsi" in df_m3.columns
                else None,
            }

        # ==================== M5 (Short-term Confirmation) ====================
        df_m5 = MarketSnapshotBuilder._get_dataframe(market_data, "5m")
        if df_m5 is not None and not df_m5.empty:
            df_m5 = MomentumEngine.calculate(df_m5, "5m")
            df_m5 = VolatilityEngine.calculate(df_m5, "5m")
            last = df_m5.iloc[-1]
            snapshot["m5"] = {
                "last_candle": {
                    "open": round(float(last["open"]), 4),
                    "high": round(float(last["high"]), 4),
                    "low": round(float(last["low"]), 4),
                    "close": round(float(last["close"]), 4),
                },
                "last_5_candles_summary": MarketSnapshotBuilder._summarize_candles(
                    df_m5, 5
                ),
                "rsi": round(float(last.get("rsi", 50)), 2)
                if "rsi" in df_m5.columns
                else None,
                "atr": round(float(last.get("atr", 0)), 4)
                if "atr" in df_m5.columns
                else None,
            }

        # ==================== M15 (Momentum) ====================
        df_m15 = MarketSnapshotBuilder._get_dataframe(market_data, "15m")
        if df_m15 is not None and not df_m15.empty:
            df_m15 = MomentumEngine.calculate(df_m15, "15m")
            last = df_m15.iloc[-1]
            snapshot["m15"] = {
                "last_candle_close": round(float(last["close"]), 4),
                "rsi": round(float(last.get("rsi", 50)), 2)
                if "rsi" in df_m15.columns
                else None,
                "macd_histogram": round(float(last.get("macd_histogram", 0)), 4)
                if "macd_histogram" in df_m15.columns
                else None,
                "trend": "Bullish" if last.get("macd_histogram", 0) > 0 else "Bearish",
            }

        # ==================== H1 (Trend & Bias) ====================
        df_h1 = MarketSnapshotBuilder._get_dataframe(market_data, "1h")
        if df_h1 is not None and not df_h1.empty:
            df_h1 = TrendEngine.calculate(df_h1, "1h")
            last = df_h1.iloc[-1]
            snapshot["h1"] = {
                "last_candle_close": round(float(last["close"]), 4),
                "supertrend": str(last.get("supertrend_trend", "Neutral")),
                "adx": round(float(last.get("adx", 0)), 2)
                if "adx" in df_h1.columns
                else None,
                "trend_regime": str(last.get("trend_regime", "Neutral")),
            }

        return snapshot

    @staticmethod
    def _get_dataframe(market_data: Dict, tf: str) -> pd.DataFrame:
        """Helper untuk mengambil DataFrame dari timeframe tertentu"""
        try:
            return market_data.get(tf, {}).get("aggregated", pd.DataFrame())
        except:
            return pd.DataFrame()

    @staticmethod
    def _summarize_candles(df: pd.DataFrame, n: int = 5) -> str:
        """Ringkasan sederhana 5-6 candle terakhir"""
        if len(df) < n:
            return "Insufficient data"

        recent = df.tail(n)
        bullish = sum(
            1
            for i in range(len(recent))
            if recent.iloc[i]["close"] > recent.iloc[i]["open"]
        )
        bearish = n - bullish

        volume_trend = (
            "increasing"
            if recent["volume"].iloc[-1] > recent["volume"].mean()
            else "decreasing"
        )

        return f"{bullish} bullish, {bearish} bearish, volume {volume_trend}"


# Helper function untuk dipanggil dari context_builder
def build_market_snapshot(market_data_for_pair: Dict) -> Dict:
    """Fungsi utama"""
    return MarketSnapshotBuilder.build(market_data_for_pair)
