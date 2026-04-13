"""
features/technical/volatility.py

Modul untuk menghitung indikator Volatility.
Fokus utama: M5 (short-term volatility & explosion detection)
"""

import pandas as pd
import pandas_ta as ta
from typing import Dict, Tuple
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class VolatilityEngine:
    @staticmethod
    def calculate(df: pd.DataFrame, timeframe: str = "5m") -> pd.DataFrame:
        """
        Hitung semua volatility indicators.
        """
        if df.empty or len(df) < 30:
            logger.warning(
                f"Data tidak cukup untuk volatility calculation di {timeframe}"
            )
            return df

        df = df.copy()

        # ==================== ATR ====================
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)

        # ==================== Bollinger Bands ====================
        bb = ta.bbands(df["close"], length=20, std=2.0)
        
        # Rename pandas_ta confusing columns dynamically to fixed names
        rename_dict = {}
        for c in bb.columns:
            if c.startswith("BBU"): rename_dict[c] = "BBU_20_2.0"
            elif c.startswith("BBM"): rename_dict[c] = "BBM_20_2.0"
            elif c.startswith("BBL"): rename_dict[c] = "BBL_20_2.0"
        bb = bb.rename(columns=rename_dict)
        
        df = pd.concat([df, bb], axis=1)

        bb_upper = "BBU_20_2.0"
        bb_middle = "BBM_20_2.0"
        bb_lower = "BBL_20_2.0"

        # Tambahkan posisi harga relatif terhadap Bollinger Bands
        df["bb_position"] = 0
        if bb_upper in df.columns and bb_lower in df.columns:
            df.loc[df["close"] > df[bb_upper], "bb_position"] = 1
            df.loc[df["close"] < df[bb_lower], "bb_position"] = -1

        # BB Width (squeeze & expansion)
        if all(col in df.columns for col in [bb_upper, bb_lower, bb_middle]):
            df["bb_width"] = (df[bb_upper] - df[bb_lower]) / df[bb_middle] * 100
        else:
            df["bb_width"] = float("nan")

        # ==================== Historical Volatility ====================
        returns = df["close"].pct_change()
        df["hist_vol_20"] = returns.rolling(window=20).std() * (100**0.5)

        # ==================== VOLATILITY REGIME ====================
        if "bb_width" in df.columns and not df["bb_width"].isna().all():
            avg_bb_width = df["bb_width"].rolling(window=50).mean()

            df["volatility_regime"] = "Normal Volatility"
            df.loc[df["bb_width"] < avg_bb_width * 0.7, "volatility_regime"] = (
                "Low Volatility (Squeeze)"
            )
            df.loc[df["bb_width"] > avg_bb_width * 1.5, "volatility_regime"] = (
                "High Volatility (Expansion)"
            )
        else:
            df["volatility_regime"] = "Normal Volatility"

        latest_atr = df['atr'].iloc[-1] if not df['atr'].empty else 0
        latest_bb_width = df['bb_width'].iloc[-1] if 'bb_width' in df and not df['bb_width'].empty else 0

        logger.debug(
            f"Volatility indicators calculated for {timeframe} | "
            f"Latest ATR: {latest_atr:.2f} | "
            f"BB Width: {latest_bb_width:.2f}%"
        )

        return df

    @staticmethod
    def get_latest_summary(df: pd.DataFrame, timeframe: str = "5m") -> Dict:
        if df.empty:
            return {"error": "No data"}

        latest = df.iloc[-1]
        recent_avg_atr = (
            df["atr"].rolling(window=20).mean().iloc[-1]
            if len(df) > 20
            else latest.get("atr", 0)
        )

        summary = {
            "timeframe": timeframe,
            "atr": round(float(latest.get("atr", 0)), 4),
            "atr_vs_average": round(float(latest.get("atr", 0) / recent_avg_atr), 2)
            if recent_avg_atr > 0
            else 1.0,
            # Bollinger Bands
            "bb_upper": round(float(latest.get("BBU_20_2.0", 0)), 4),
            "bb_middle": round(float(latest.get("BBM_20_2.0", 0)), 4),
            "bb_lower": round(float(latest.get("BBL_20_2.0", 0)), 4),
            "bb_width_pct": round(float(latest.get("bb_width", 0)), 2),
            "bb_position": "Upper Band"
            if latest.get("bb_position") == 1
            else "Lower Band"
            if latest.get("bb_position") == -1
            else "Middle Band",
            "volatility_regime": str(
                latest.get("volatility_regime", "Normal Volatility")
            ),
            "volatility_status": "Increasing"
            if latest.get("atr", 0) > recent_avg_atr * 1.1
            else "Decreasing"
            if latest.get("atr", 0) < recent_avg_atr * 0.9
            else "Stable",
            "calculated_at": datetime.utcnow().isoformat(),
        }

        return summary


# Helper function
def calculate_volatility_features(
    df: pd.DataFrame, timeframe: str = "5m"
) -> Tuple[pd.DataFrame, Dict]:
    df_result = VolatilityEngine.calculate(df, timeframe)
    summary = VolatilityEngine.get_latest_summary(df_result, timeframe)
    return df_result, summary
