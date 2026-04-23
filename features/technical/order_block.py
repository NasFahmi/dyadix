"""
features/technical/order_block.py

Modul untuk mendeteksi Order Block institusional berdasarkan Smart Money Concepts (SMC).
Fokus utama: Deteksi zona support/resistance probabilitas tinggi di H1 atau M15.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Tuple, List
from datetime import datetime

logger = logging.getLogger(__name__)

class OrderBlockEngine:
    """
    Engine untuk mendeteksi Order Block yang belum tersentuh (Unmitigated).
    """

    @staticmethod
    def get_active_obs(df: pd.DataFrame, atr_multiplier: float = 1.5, lookback: int = 150) -> Tuple[List[Dict], List[Dict]]:
        """
        Mendeteksi Bullish dan Bearish Order Blocks yang belum termitigasi.
        """
        if df.empty or len(df) < 20:
            return [], []
            
        df = df.copy()
        
        # Calculate ATR if not present
        atr_col = [c for c in df.columns if "ATR" in c]
        if not atr_col:
            import pandas_ta as ta
            df.ta.atr(length=14, append=True)
            atr_col = [c for c in df.columns if "ATR" in c][0]
        else:
            atr_col = atr_col[0]
            
        df["body"] = df["close"] - df["open"]
        df["body_abs"] = abs(df["body"])
        
        bullish_obs = []
        bearish_obs = []
        
        start_idx = max(14, len(df) - lookback)
        
        # 1. Identifikasi Impulse dan pembentukan OB
        for i in range(start_idx, len(df)):
            row = df.iloc[i]
            body_abs = row["body_abs"]
            atr = row[atr_col]
            
            if pd.isna(atr):
                continue
                
            is_bullish_impulse = (row["body"] > 0) and (body_abs > atr_multiplier * atr)
            is_bearish_impulse = (row["body"] < 0) and (body_abs > atr_multiplier * atr)
            
            if is_bullish_impulse:
                # Cari candle Bearish terakhir sebelum impulse
                for j in range(i-1, max(-1, i-10), -1):
                    if df.iloc[j]["body"] < 0:
                        ob = {
                            "top": df.iloc[j]["high"],
                            "bottom": df.iloc[j]["low"],
                            "index": j,
                            "impulse_index": i
                        }
                        bullish_obs.append(ob)
                        break
                        
            if is_bearish_impulse:
                # Cari candle Bullish terakhir sebelum impulse
                for j in range(i-1, max(-1, i-10), -1):
                    if df.iloc[j]["body"] > 0:
                        ob = {
                            "top": df.iloc[j]["high"],
                            "bottom": df.iloc[j]["low"],
                            "index": j,
                            "impulse_index": i
                        }
                        bearish_obs.append(ob)
                        break
        
        # 2. Filter Mitigation
        active_bullish = []
        for ob in bullish_obs:
            mitigated = False
            # Cek candle setelah impulse, apakah menyentuh OB top
            for k in range(ob["impulse_index"] + 1, len(df)):
                if df.iloc[k]["low"] <= ob["top"]:
                    mitigated = True
                    break
            if not mitigated:
                active_bullish.append(ob)
                
        active_bearish = []
        for ob in bearish_obs:
            mitigated = False
            # Cek candle setelah impulse, apakah menyentuh OB bottom
            for k in range(ob["impulse_index"] + 1, len(df)):
                if df.iloc[k]["high"] >= ob["bottom"]:
                    mitigated = True
                    break
            if not mitigated:
                active_bearish.append(ob)
                
        return active_bullish, active_bearish

    @staticmethod
    def get_latest_summary(df: pd.DataFrame, timeframe: str = "1h", atr_multiplier: float = 1.5) -> Dict:
        """
        Mengambil OB terdekat dari harga saat ini.
        """
        if df.empty:
            return {"error": "No data"}

        active_bullish, active_bearish = OrderBlockEngine.get_active_obs(df, atr_multiplier)
        current_price = df.iloc[-1]["close"]
        
        nearest_bullish = None
        min_dist_bull = float('inf')
        for ob in active_bullish:
            if ob["top"] < current_price: # OB harus berada di bawah harga saat ini
                dist = current_price - ob["top"]
                if dist < min_dist_bull:
                    min_dist_bull = dist
                    nearest_bullish = ob
                    
        nearest_bearish = None
        min_dist_bear = float('inf')
        for ob in active_bearish:
            if ob["bottom"] > current_price: # OB harus berada di atas harga saat ini
                dist = ob["bottom"] - current_price
                if dist < min_dist_bear:
                    min_dist_bear = dist
                    nearest_bearish = ob
                    
        return {
            "timeframe": timeframe,
            "nearest_bullish_ob": {
                "top": round(float(nearest_bullish["top"]), 4), 
                "bottom": round(float(nearest_bullish["bottom"]), 4)
            } if nearest_bullish else None,
            "nearest_bearish_ob": {
                "top": round(float(nearest_bearish["top"]), 4), 
                "bottom": round(float(nearest_bearish["bottom"]), 4)
            } if nearest_bearish else None,
            "active_bullish_count": len(active_bullish),
            "active_bearish_count": len(active_bearish),
            "calculated_at": datetime.utcnow().isoformat()
        }

def calculate_order_block_features(df: pd.DataFrame, timeframe: str = "1h", atr_multiplier: float = 1.5) -> Tuple[pd.DataFrame, Dict]:
    summary = OrderBlockEngine.get_latest_summary(df, timeframe, atr_multiplier)
    return df, summary
