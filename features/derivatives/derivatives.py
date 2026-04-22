"""
features/derivatives.py

Modul untuk menghitung dan menganalisis data Derivatives:
- Funding Rate
- Open Interest
- OI Change
- Basis (optional)
"""

import pandas as pd
from typing import Dict, List, Tuple
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DerivativesEngine:
    """
    Engine untuk mengolah data Funding Rate dan Open Interest dari Binance & Bybit.
    """

    @staticmethod
    def calculate(derivatives_data: Dict, pair: str) -> Dict:
        """
        Hitung analisis derivatives untuk satu pair.

        Parameters:
            derivatives_data: Dict berisi data funding rate & open interest
                Contoh struktur:
                {
                    "funding_rate": df_funding,      # kolom: timestamp, funding_rate
                    "open_interest": df_oi,          # kolom: timestamp, open_interest, oi_change
                    "basis": df_basis                # optional
                }
            pair: Pair yang dianalisis (contoh: BTCUSDT)
        """
        if not derivatives_data:
            return {"error": "No derivatives data"}

        result = {
            "pair": pair,
            "timestamp": datetime.utcnow().isoformat(),
            "funding_rate": {},
            "open_interest": {},
            "derivatives_sentiment": "Neutral",
        }

        # ==================== FUNDING RATE ANALYSIS ====================
        if (
            "funding_rate" in derivatives_data
            and not derivatives_data["funding_rate"].empty
        ):
            df_funding = derivatives_data["funding_rate"].tail(
                8
            )  # 8 data terakhir (~8 jam terakhir)

            latest_funding = df_funding["funding_rate"].iloc[-1]
            avg_funding = df_funding["funding_rate"].mean()
            funding_trend = df_funding["funding_rate"].diff().mean()

            result["funding_rate"] = {
                "latest": round(float(latest_funding), 6),
                "average_8h": round(float(avg_funding), 6),
                "trend": "Rising"
                if funding_trend > 0
                else "Falling"
                if funding_trend < 0
                else "Stable",
                "sentiment": "Bullish"
                if latest_funding > 0.0001
                else "Bearish"
                if latest_funding < -0.0001
                else "Neutral",
            }

        # ==================== OPEN INTEREST ANALYSIS ====================
        if (
            "open_interest" in derivatives_data
            and not derivatives_data["open_interest"].empty
        ):
            df_oi = derivatives_data["open_interest"].tail(20)
            n_oi = len(df_oi)

            latest_oi = df_oi["open_interest"].iloc[-1]
            oi_change_1h = (
                (latest_oi - df_oi["open_interest"].iloc[-2])
                / df_oi["open_interest"].iloc[-2]
                * 100
                if n_oi >= 2
                else 0
            )
            oi_change_4h = (
                (latest_oi - df_oi["open_interest"].iloc[-5])
                / df_oi["open_interest"].iloc[-5]
                * 100
                if n_oi >= 5
                else 0
            )

            # Price vs OI Divergence (need at least 5 data points)
            price_up = (
                df_oi["close"].iloc[-1] > df_oi["close"].iloc[-5]
                if "close" in df_oi.columns and n_oi >= 5
                else False
            )
            oi_up = oi_change_4h > 0

            if price_up and oi_up:
                oi_regime = "Healthy Uptrend (Longs Increasing)"
            elif price_up and not oi_up:
                oi_regime = "Suspicious Uptrend (Longs Decreasing)"
            elif not price_up and oi_up:
                oi_regime = "Potential Reversal (Shorts Increasing)"
            else:
                oi_regime = "Healthy Downtrend" if not price_up else "Neutral"

            result["open_interest"] = {
                "latest": int(latest_oi),
                "change_1h_pct": round(float(oi_change_1h), 2),
                "change_4h_pct": round(float(oi_change_4h), 2),
                "regime": oi_regime,
            }

        # ==================== OVERALL DERIVATIVES SENTIMENT ====================
        funding_sentiment = result.get("funding_rate", {}).get("sentiment", "Neutral")
        oi_regime = result.get("open_interest", {}).get("regime", "Neutral")

        if funding_sentiment == "Bullish" and "Healthy Uptrend" in oi_regime:
            result["derivatives_sentiment"] = "Strong Bullish"
        elif funding_sentiment == "Bearish" and "Healthy Downtrend" in oi_regime:
            result["derivatives_sentiment"] = "Strong Bearish"
        elif funding_sentiment == "Bullish":
            result["derivatives_sentiment"] = "Moderate Bullish"
        elif funding_sentiment == "Bearish":
            result["derivatives_sentiment"] = "Moderate Bearish"
        else:
            result["derivatives_sentiment"] = "Neutral"

        logger.info(
            f"Derivatives analysis completed for {pair} | "
            f"Funding: {funding_sentiment} | OI Regime: {oi_regime}"
        )

        return result


# Helper function
def calculate_derivatives_features(derivatives_data: Dict, pair: str) -> Dict:
    """
    Fungsi utama untuk dipanggil dari pipeline.
    """
    engine = DerivativesEngine()
    return engine.calculate(derivatives_data, pair)
