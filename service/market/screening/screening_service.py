"""
service/market/screening/screening_service.py

Orchestrator utama modul Market Screening.
Menggabungkan MarketCollector, ScreeningCache, dan ScoringEngine untuk menyajikan data universe,
perankingan pasar, serta daftar top candidate pairs yang siap dipakai pipeline Dyadix.
"""

import logging
from typing import List, Dict, Any, Optional

from config.settings import get_config
from service.market.screening.market_collector import MarketCollector
from service.market.screening.screening_cache import ScreeningCache
from service.market.screening.scoring_engine import ScoringEngine

logger = logging.getLogger(__name__)


class ScreeningService:
    """
    Service utama untuk mengelola screening market Hyperliquid.
    """

    def __init__(
        self,
        collector: Optional[MarketCollector] = None,
        cache: Optional[ScreeningCache] = None,
        scoring_engine: Optional[ScoringEngine] = None,
    ):
        self.config = get_config()
        screening_cfg = self.config.get("screening", {})

        self.enabled: bool = screening_cfg.get("enabled", True)
        self.min_volume_24h: float = float(screening_cfg.get("min_volume_24h", 1_000_000))
        self.refresh_interval_minutes: float = float(
            screening_cfg.get("refresh_interval_minutes", screening_cfg.get("refresh_interval_hours", 0.0833) * 60.0)
        )
        self.scan_candidates_count: int = int(
            screening_cfg.get("scan_candidates", screening_cfg.get("top_candidates", 10))
        )
        self.max_tradeable_count: int = int(screening_cfg.get("max_tradeable", 3))

        self.collector = collector or MarketCollector()
        self.cache = cache or ScreeningCache(ttl_minutes=self.refresh_interval_minutes)
        
        # Initialize Scoring Engine with weights from config or defaults
        self.scoring_engine = scoring_engine or ScoringEngine(
            volume_weight=float(screening_cfg.get("volume_weight", 0.30)),
            atr_weight=float(screening_cfg.get("atr_weight", 0.30)),
            oi_weight=float(screening_cfg.get("oi_weight", 0.25)),
            funding_weight=float(screening_cfg.get("funding_weight", 0.15)),
        )

    def get_all_universe_metrics(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Mengambil data metrik seluruh market (dari cache jika ada & valid, atau live fetch).
        """
        if not force_refresh:
            cached_data = self.cache.load()
            if cached_data is not None:
                return cached_data

        logger.info("Fetching fresh universe market metrics from Hyperliquid...")
        fresh_data = self.collector.collect_all_market_metrics()

        if fresh_data:
            self.cache.save(fresh_data)
            return fresh_data

        # Fallback jika fetch gagal, coba baca cache lama (sekalipun kadaluarsa)
        fallback_data = self.cache.load()
        if fallback_data:
            logger.warning("Using expired cache data as fallback due to live collection failure.")
            return fallback_data

        return []

    def get_filtered_markets(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Mengambil metrik pasar yang sudah lolos Universe Filter (misal volume_24h >= 1,000,000 USD).
        """
        all_metrics = self.get_all_universe_metrics(force_refresh=force_refresh)
        filtered = [m for m in all_metrics if m.get("volume_24h", 0) >= self.min_volume_24h]
        
        logger.info(
            f"Screening Filter: {len(filtered)} out of {len(all_metrics)} markets "
            f"passed min_volume_24h >= ${self.min_volume_24h:,.0f} USD"
        )
        return filtered

    def get_ranked_markets(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Mengambil daftar pasar yang lolos filter dan telah dihitung skor serta peringkatnya.
        """
        filtered = self.get_filtered_markets(force_refresh=force_refresh)
        ranked = self.scoring_engine.calculate_scores(filtered)
        return ranked

    def get_candidate_symbols(
        self, force_refresh: bool = False, quote_asset: Optional[str] = None
    ) -> List[str]:
        """
        Mengembalikan daftar Top N kandidat simbol pair terbaik hasil screening.
        Setiap simbol ditempelkan quote asset (misal "BTC" -> "BTCUSDC") agar 100% kompatibel
        dengan MarketService Dyadix.
        """
        if not quote_asset:
            # Cari quote asset default dari config trading pairs atau "USDC"
            trading_pairs = self.config.get("trading", {}).get("pairs", ["BTCUSDC"])
            if trading_pairs and trading_pairs[0].endswith("USDT"):
                quote_asset = "USDT"
            else:
                quote_asset = "USDC"

        ranked_markets = self.get_ranked_markets(force_refresh=force_refresh)
        top_markets = ranked_markets[: self.scan_candidates_count]

        candidate_symbols = []
        for m in top_markets:
            raw_symbol = m.get("symbol", "")
            if not raw_symbol:
                continue
            
            # Format dengan quote asset jika belum ada
            if raw_symbol.endswith("USDC") or raw_symbol.endswith("USDT"):
                formatted_symbol = raw_symbol
            else:
                formatted_symbol = f"{raw_symbol}{quote_asset}"
                
            candidate_symbols.append(formatted_symbol)

        logger.info(f"Screening Top Candidates ({len(candidate_symbols)}): {candidate_symbols}")
        return candidate_symbols
