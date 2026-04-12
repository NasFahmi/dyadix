"""
features/daily_bias.py

Modul untuk menghitung Daily Bias berdasarkan candle Daily Previous Day.
Dijalankan sekali per hari pukul 00:00 UTC.
"""

import pandas as pd
from datetime import datetime
import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class DailyBiasCalculator:
    """
    Menghitung Daily Bias dan key levels dari Previous Day Candle.
    """

    def __init__(self, data_dir: str = "data/processed/daily_bias"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    def calculate_daily_bias(self, df_daily: pd.DataFrame, pair: str) -> Dict:
        """
        Hitung Daily Bias dari DataFrame Daily OHLC (aggregated).

        Parameters:
            df_daily: DataFrame dengan timeframe '1d' atau 'D',
                      harus sudah diurutkan berdasarkan waktu (terbaru di bawah)
            pair: Pair yang dihitung (contoh: BTCUSDT)

        Returns:
            Dictionary berisi daily bias dan key levels
        """
        if df_daily.empty or len(df_daily) < 2:
            logger.error(f"Data daily tidak cukup untuk {pair}")
            return self._empty_bias(pair)

        # Ambil candle Previous Day (hari kemarin)
        # Karena index terurut ascending, ambil baris kedua terakhir
        previous_day = df_daily.iloc[
            -2
        ]  # -1 = current day (masih berjalan), -2 = previous day

        # Ambil current day (yang sedang berjalan) untuk reference
        current_day = df_daily.iloc[-1]

        # Hitung Daily Bias
        open_price = previous_day["open"]
        close_price = previous_day["close"]
        high_price = previous_day["high"]
        low_price = previous_day["low"]

        if close_price > open_price:
            bias = "Bullish"
            strength = (
                "Strong"
                if (close_price - open_price) / (high_price - low_price) > 0.7
                else "Moderate"
            )
        elif close_price < open_price:
            bias = "Bearish"
            strength = (
                "Strong"
                if (open_price - close_price) / (high_price - low_price) > 0.7
                else "Moderate"
            )
        else:
            bias = "Neutral"
            strength = "Neutral"

        # Candle Pattern sederhana
        body_size = abs(close_price - open_price)
        range_size = high_price - low_price
        upper_shadow = high_price - max(open_price, close_price)
        lower_shadow = min(open_price, close_price) - low_price

        if body_size < 0.1 * range_size:
            candle_pattern = "Doji"
        elif upper_shadow > 2 * body_size and lower_shadow < 0.3 * body_size:
            candle_pattern = "Shooting Star" if bias == "Bearish" else "Inverted Hammer"
        elif lower_shadow > 2 * body_size and upper_shadow < 0.3 * body_size:
            candle_pattern = "Hammer" if bias == "Bullish" else "Hanging Man"
        elif close_price > open_price and close_price > previous_day.get(
            "close", 0
        ):  # simplistic
            candle_pattern = "Bullish Engulfing"
        elif close_price < open_price and close_price < previous_day.get("close", 0):
            candle_pattern = "Bearish Engulfing"
        else:
            candle_pattern = "Normal"

        daily_bias = {
            "pair": pair,
            "date": previous_day.name.strftime("%Y-%m-%d")
            if isinstance(previous_day.name, pd.Timestamp)
            else str(previous_day.name),
            "bias": bias,
            "strength": strength,
            "candle_pattern": candle_pattern,
            # Key Levels (sangat penting untuk trading)
            "previous_day_high": float(high_price),
            "previous_day_low": float(low_price),
            "previous_day_close": float(close_price),
            "previous_day_open": float(open_price),
            "previous_day_range": float(range_size),
            # Current Day Info
            "current_day_open": float(current_day["open"]),
            "current_price": float(current_day["close"]),  # harga terakhir
            # Additional Info
            "body_size_pct": float((body_size / range_size) * 100)
            if range_size > 0
            else 0.0,
            "calculated_at": datetime.utcnow().isoformat(),
            "source": "aggregated_volume_weighted",
        }

        logger.info(
            f"Daily Bias calculated for {pair}: {bias} ({strength}) | "
            f"PDH: {high_price:.2f} | PDL: {low_price:.2f}"
        )

        # Simpan ke file (parquet + json untuk mudah dibaca)
        self._save_daily_bias(daily_bias, pair)

        return daily_bias

    def _empty_bias(self, pair: str) -> Dict:
        """Return bias kosong jika data tidak cukup"""
        return {
            "pair": pair,
            "bias": "Neutral",
            "strength": "Unknown",
            "candle_pattern": "Unknown",
            "previous_day_high": None,
            "previous_day_low": None,
            "previous_day_close": None,
            "error": "Insufficient data",
            "calculated_at": datetime.utcnow().isoformat(),
        }

    def _save_daily_bias(self, bias_data: Dict, pair: str):
        """Simpan hasil daily bias"""
        try:
            # Simpan sebagai JSON (mudah dibaca)
            import json

            filename = f"{pair}_daily_bias_{datetime.utcnow().strftime('%Y%m%d')}.json"
            filepath = os.path.join(self.data_dir, filename)

            with open(filepath, "w") as f:
                json.dump(bias_data, f, indent=2, default=str)

            logger.debug(f"Daily bias saved: {filepath}")
        except Exception as e:
            logger.warning(f"Failed to save daily bias for {pair}: {e}")

    def load_latest_bias(self, pair: str) -> Optional[Dict]:
        """Load daily bias terbaru untuk suatu pair"""
        try:
            files = [
                f
                for f in os.listdir(self.data_dir)
                if f.startswith(pair) and f.endswith(".json")
            ]
            if not files:
                return None
            latest_file = max(files)
            with open(os.path.join(self.data_dir, latest_file), "r") as f:
                return json.load(f)
        except Exception:
            return None


# Helper function untuk dipanggil dari pipeline
def get_daily_bias(df_daily_aggregated: pd.DataFrame, pair: str) -> Dict:
    """Helper function sederhana"""
    calculator = DailyBiasCalculator()
    return calculator.calculate_daily_bias(df_daily_aggregated, pair)
