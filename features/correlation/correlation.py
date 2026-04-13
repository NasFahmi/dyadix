"""
features/correlation/correlation.py

Modul untuk menghitung correlation antar pair crypto.
Fokus: Korelasi pergerakan persentase (returns) antar pair dengan alignment waktu.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import logging
from datetime import datetime
from config.settings import get_config

logger = logging.getLogger(__name__)


class CorrelationEngine:
    """
    Engine untuk menghitung correlation matrix dan insight antar pair.
    """

    def __init__(self):
        self.config = get_config()
        self.pairs: List[str] = self.config.get("trading", {}).get("correlation_pairs", [])
        self.benchmark = "BTCUSDT"

    def calculate(
        self,
        market_data: Dict,
        timeframe: str = "1h",
        lookback: int = 120,  # 120 candle ≈ 5 hari di H1
    ) -> Dict:
        """
        Hitung correlation antar semua pair berdasarkan returns.
        """
        if not market_data:
            logger.warning("Market data kosong untuk correlation")
            return {"error": "No market data"}

        closes = {}

        for pair, tf_data in market_data.items():
            # Filter menggunakan self.pairs, tapi pastikan benchmark tetap lulus
            if self.pairs and pair not in self.pairs and pair != self.benchmark:
                continue
                
            if timeframe in tf_data:
                df = tf_data[timeframe].get("aggregated")
                if df is not None and not df.empty and len(df) >= lookback:
                    # Pastikan index diset ke timestamp agar sejajar (time-aligned)
                    # Pada dyadix, umumnya timestamp ada sebagai kolom
                    if 'timestamp' in df.columns:
                        temp_df = df.set_index('timestamp')
                    else:
                        temp_df = df
                        
                    # Ambil tail lookback dan simpan Pandas Series ke dictionary
                    # Menggunakan re-indexing otomais dari Pandas pd.DataFrame(dict) nanti
                    closes[pair] = temp_df['close'].tail(lookback)

        if len(closes) < 2:
            logger.warning("Tidak cukup pair untuk menghitung correlation (butuh min 2)")
            return {"error": "Not enough pairs for correlation"}

        # Buat DataFrame harga close (akan menggunakan outer join untuk menggabungkan index yang selaras)
        price_df = pd.DataFrame(closes)
        
        # Isi gap kosong otomatis (kasus koin disuspend beberapa menit/baris data loss)
        price_df = price_df.ffill().bfill()
        
        # Hitung Returns (Persentase Perubahan) - Cara terbaik di Analisa Kuantitatif Trading
        returns_df = price_df.pct_change().dropna()

        # Hitung correlation matrix (Pearson) menggunakan returns
        corr_matrix = returns_df.corr()

        # Hitung correlation dengan Benchmark
        btc_corr = {}
        if self.benchmark in corr_matrix.columns:
            btc_corr = corr_matrix[self.benchmark].to_dict()

        # Return correlation insight terformat
        correlation_data = {
            "timeframe": timeframe,
            "btc_correlation": {
                k: round(v, 2) for k, v in btc_corr.items() if k != self.benchmark
            },
            "insights": self._generate_insights(corr_matrix, btc_corr),
        }

        logger.info(
            f"Correlation calculated (using returns) for {len(closes)} pairs on {timeframe} timeframe"
        )
        return correlation_data

    def _generate_insights(
        self, corr_matrix: pd.DataFrame, btc_corr: Dict
    ) -> List[Dict]:
        """Generate insight dinamis dari correlation matrix (berbasis Returns)"""
        insights = []

        # 1. Insight Benchmark Dominance (BTC)
        strong_with_btc = [
            pair for pair, corr in btc_corr.items() if corr >= 0.75 and pair != self.benchmark
        ]
        weak_with_btc = [
            pair for pair, corr in btc_corr.items() if corr < 0.75 and pair != self.benchmark
        ]

        if strong_with_btc:
            insights.append(
                {
                    "type": "high_btc_correlation",
                    "description": f"Pair yang sangat mengikuti BTC: {', '.join(strong_with_btc)}",
                    "strength": "Strong",
                }
            )

        if weak_with_btc:
            insights.append(
                {
                    "type": "low_btc_correlation",
                    "description": f"Pair yang relatif independen dari BTC: {', '.join(weak_with_btc)}",
                    "strength": "Weak",
                }
            )

        return insights

# Helper function
def calculate_correlation(
    market_data: Dict, timeframe: str = "1h", lookback: int = 120
) -> Dict:
    """
    Fungsi utama untuk dipanggil dari pipeline.
    """
    engine = CorrelationEngine()
    return engine.calculate(market_data, timeframe, lookback)
