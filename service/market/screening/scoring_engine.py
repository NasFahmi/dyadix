"""
service/market/screening/scoring_engine.py

Engine perhitungan skor dan perankingan pasar untuk Dyadix Market Screening.
Menggunakan Min-Max Normalization (0-100) dan bobot komposit.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class ScoringEngine:
    """
    Menghitung skor peluang (0 - 100) untuk setiap pair berdasarkan 4 metrik utama:
    - Volume 24h (30%)
    - Volatilitas / ATR proxy (30%)
    - Open Interest USD (25%)
    - Funding Rate Absolut (15%)
    """

    def __init__(
        self,
        volume_weight: float = 0.30,
        atr_weight: float = 0.30,
        oi_weight: float = 0.25,
        funding_weight: float = 0.15,
    ):
        self.volume_weight = volume_weight
        self.atr_weight = atr_weight
        self.oi_weight = oi_weight
        self.funding_weight = funding_weight

    @staticmethod
    def _normalize(val: float, min_val: float, max_val: float) -> float:
        """Helper untuk Min-Max Normalization ke skala 0 - 100."""
        if max_val <= min_val:
            return 50.0  # Jika semua data bernilai sama
        normalized = ((val - min_val) / (max_val - min_val)) * 100.0
        return max(0.0, min(100.0, normalized))

    def calculate_scores(self, markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Menghitung skor untuk setiap market dan mengurutkannya dari yang tertinggi.
        """
        if not markets:
            return []

        # Extract values for normalization
        volumes = [m.get("volume_24h", 0.0) for m in markets]
        volatilities = [m.get("volatility_24h_pct", 0.0) for m in markets]
        ois = [m.get("open_interest_usd", 0.0) for m in markets]
        fundings = [abs(m.get("funding_rate", 0.0)) for m in markets]

        min_vol, max_vol = min(volumes), max(volumes)
        min_atr, max_atr = min(volatilities), max(volatilities)
        min_oi, max_oi = min(ois), max(ois)
        min_fund, max_fund = min(fundings), max(fundings)

        scored_markets = []
        for m in markets:
            # Copy to avoid mutating original dictionary directly
            item = dict(m)

            vol_val = item.get("volume_24h", 0.0)
            atr_val = item.get("volatility_24h_pct", 0.0)
            oi_val = item.get("open_interest_usd", 0.0)
            fund_val = abs(item.get("funding_rate", 0.0))

            vol_score = self._normalize(vol_val, min_vol, max_vol)
            atr_score = self._normalize(atr_val, min_atr, max_atr)
            oi_score = self._normalize(oi_val, min_oi, max_oi)
            fund_score = self._normalize(fund_val, min_fund, max_fund)

            total_score = (
                (vol_score * self.volume_weight)
                + (atr_score * self.atr_weight)
                + (oi_score * self.oi_weight)
                + (fund_score * self.funding_weight)
            )

            item["scores_breakdown"] = {
                "volume_score": round(vol_score, 2),
                "volatility_score": round(atr_score, 2),
                "oi_score": round(oi_score, 2),
                "funding_score": round(fund_score, 2),
            }
            item["score"] = round(total_score, 2)
            scored_markets.append(item)

        # Urutkan berdasarkan skor tertinggi (descending)
        scored_markets.sort(key=lambda x: x["score"], reverse=True)

        # Tambahkan informasi rank (peringkat)
        for rank, m in enumerate(scored_markets, start=1):
            m["rank"] = rank

        logger.info(f"Scoring complete for {len(scored_markets)} markets.")
        return scored_markets
