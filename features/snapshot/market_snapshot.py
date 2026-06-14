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
    def build(market_data: Dict, mode: str = "scalping") -> Dict[str, Any]:
        """
        market_data: dict dari MarketService untuk satu pair
        Contoh: market_data[pair] = {"5m": {...}, "15m": {...}, ...}
        """
        if mode == "swing":
            tf_prec = "15m"
            tf_conf = "1h"
            tf_mom = "4h"
            tf_trend = "1d"
        else:
            tf_prec = "3m"
            tf_conf = "5m"
            tf_mom = "15m"
            tf_trend = "1h"

        snapshot = {
            "current_price": None,
            "timestamp_utc": datetime.utcnow().isoformat(),
            tf_prec: {},
            tf_conf: {},
            tf_mom: {},
            tf_trend: {},
        }

        # ==================== Precision Entry ====================
        df_prec = MarketSnapshotBuilder._get_dataframe(market_data, tf_prec)
        if df_prec is not None and not df_prec.empty:
            df_prec = MomentumEngine.calculate(df_prec, tf_prec)
            last = df_prec.iloc[-1]
            snapshot["current_price"] = round(float(last["close"]), 4)
            snapshot[tf_prec] = {
                "last_candle": {
                    "open": round(float(last["open"]), 4),
                    "high": round(float(last["high"]), 4),
                    "low": round(float(last["low"]), 4),
                    "close": round(float(last["close"]), 4),
                },
                "last_6_candles_summary": MarketSnapshotBuilder._summarize_candles(
                    df_prec, 6
                ),
                "rsi": round(float(last.get("rsi", 50)), 2)
                if "rsi" in df_prec.columns
                else None,
            }

        # ==================== Confirmation Timeframe ====================
        df_conf = MarketSnapshotBuilder._get_dataframe(market_data, tf_conf)
        if df_conf is not None and not df_conf.empty:
            df_conf = MomentumEngine.calculate(df_conf, tf_conf)
            df_conf = VolatilityEngine.calculate(df_conf, tf_conf)
            last = df_conf.iloc[-1]
            snapshot[tf_conf] = {
                "last_candle": {
                    "open": round(float(last["open"]), 4),
                    "high": round(float(last["high"]), 4),
                    "low": round(float(last["low"]), 4),
                    "close": round(float(last["close"]), 4),
                },
                "last_5_candles_summary": MarketSnapshotBuilder._summarize_candles(
                    df_conf, 5
                ),
                "rsi": round(float(last.get("rsi", 50)), 2)
                if "rsi" in df_conf.columns
                else None,
                "atr": round(float(last.get("atr", 0)), 4)
                if "atr" in df_conf.columns
                else None,
            }

        # ==================== Momentum Timeframe ====================
        df_mom = MarketSnapshotBuilder._get_dataframe(market_data, tf_mom)
        if df_mom is not None and not df_mom.empty:
            df_mom = MomentumEngine.calculate(df_mom, tf_mom)
            last = df_mom.iloc[-1]
            snapshot[tf_mom] = {
                "last_candle_close": round(float(last["close"]), 4),
                "rsi": round(float(last.get("rsi", 50)), 2)
                if "rsi" in df_mom.columns
                else None,
                "macd_histogram": round(float(last.get("macd_histogram", 0)), 4)
                if "macd_histogram" in df_mom.columns
                else None,
                "trend": "Bullish" if last.get("macd_histogram", 0) > 0 else "Bearish",
            }

        # ==================== Trend & Bias Timeframe ====================
        df_trend_data = MarketSnapshotBuilder._get_dataframe(market_data, tf_trend)
        if df_trend_data is not None and not df_trend_data.empty:
            df_trend_data = TrendEngine.calculate(df_trend_data, tf_trend)
            last = df_trend_data.iloc[-1]
            snapshot[tf_trend] = {
                "last_candle_close": round(float(last["close"]), 4),
                "supertrend": str(last.get("supertrend_trend", "Neutral")),
                "adx": round(float(last.get("adx", 0)), 2)
                if "adx" in df_trend_data.columns
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
def build_market_snapshot(market_data_for_pair: Dict, mode: str = "scalping") -> Dict:
    """Fungsi utama"""
    return MarketSnapshotBuilder.build(market_data_for_pair, mode)
