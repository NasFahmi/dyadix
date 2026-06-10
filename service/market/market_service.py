"""
services/market/market_service.py

Orchestrator utama untuk mengambil OHLCV dari Hyperliquid DEX.
"""

import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
import logging

from config.settings import get_config
from service.market.hyperliquid.hyperliquid_service import HyperliquidService
from utils.ohlcv_aggregator import OHLCVAggregator

logger = logging.getLogger(__name__)


class MarketService:
    """
    Service utama untuk mengelola data market (OHLCV) dari Hyperliquid DEX.
    """

    def __init__(self):
        self.config = get_config()
        self.hyperliquid = HyperliquidService()

        # Ambil konfigurasi dari settings.yaml
        self.pairs: List[str] = self.config.get("trading", {}).get("pairs") or ["BTCUSDT"]
        self.correlation_pairs: List[str] = self.config.get("trading", {}).get("correlation_pairs", [])
        
        self.timeframes: List[str] = self.config.get("trading", {}).get(
            "timeframes", ["5m", "15m", "1h"]
        ) or ["5m", "15m", "1h"]
        self.agg_method: str = "volume_weighted"

        logger.info(
            f"MarketService initialized with {len(self.pairs)} pairs "
            f"and timeframes: {self.timeframes} using Hyperliquid DEX"
        )

    def fetch_ohlcv_all(
        self, limit: int = 500, agg_method: Optional[str] = None
    ) -> Dict:
        """
        Fetch OHLCV untuk semua pair dan semua timeframe yang ada di config.
        """
        if agg_method is None:
            agg_method = self.agg_method

        all_data = {}
        fetch_list = list(set(self.pairs + self.correlation_pairs))

        for pair in fetch_list:
            logger.info(f"Fetching OHLCV for {pair} from Hyperliquid...")
            pair_data = {}

            for tf in self.timeframes:
                try:
                    # Fetch dari Hyperliquid
                    df_hl = self.hyperliquid.fetch_ohlcv(
                        symbol=pair, timeframe=tf, limit=limit
                    )

                    # Ganti Bybit dengan empty DataFrame untuk memicu fallback di aggregator
                    df_aggregated = OHLCVAggregator.aggregate(
                        df_binance=df_hl, df_bybit=pd.DataFrame(), method=agg_method
                    )

                    pair_data[tf] = {
                        "binance": df_hl,
                        "bybit": pd.DataFrame(),
                        "aggregated": df_aggregated,
                        "last_updated": datetime.utcnow(),
                    }

                    logger.debug(
                        f"✓ {pair} {tf} fetched successfully | "
                        f"Rows: {len(df_aggregated)}"
                    )

                except Exception as e:
                    logger.error(f"❌ Failed to fetch {pair} {tf}: {e}")
                    pair_data[tf] = {
                        "binance": pd.DataFrame(),
                        "bybit": pd.DataFrame(),
                        "aggregated": pd.DataFrame(),
                        "last_updated": datetime.utcnow(),
                        "error": str(e),
                    }

            all_data[pair] = pair_data

        logger.info(f"Market data fetch completed for {len(all_data)} pairs")
        return all_data

    def fetch_single_pair(
        self, pair: str, timeframes: Optional[List[str]] = None, limit: int = 500
    ) -> Dict:
        """
        Fetch data hanya untuk satu pair tertentu.
        """
        if timeframes is None:
            timeframes = self.timeframes

        logger.info(f"Fetching single pair: {pair} from Hyperliquid")

        pair_data = {}
        for tf in timeframes:
            try:
                df_hl = self.hyperliquid.fetch_ohlcv(pair, tf, limit)
                df_aggregated = OHLCVAggregator.aggregate(
                    df_hl, pd.DataFrame(), method=self.agg_method
                )

                pair_data[tf] = {
                    "binance": df_hl,
                    "bybit": pd.DataFrame(),
                    "aggregated": df_aggregated,
                }
            except Exception as e:
                logger.error(f"Error fetching {pair} {tf}: {e}")
                pair_data[tf] = {"error": str(e)}

        return pair_data

    def get_latest_candles(self, pair: str, timeframe: str = "15m", n: int = 1) -> Dict:
        """
        Ambil candle terbaru.
        """
        data = self.fetch_single_pair(pair, [timeframe], limit=200)
        if timeframe in data and not data[timeframe]["aggregated"].empty:
            df = data[timeframe]["aggregated"]
            return {
                "latest": df.iloc[-n:].to_dict(orient="records"),
                "pair": pair,
                "timeframe": timeframe,
            }
        return {}

    def save_raw_data(self, all_data: Dict, base_path: str = "data/raw/market"):
        """
        Simpan raw data ke folder sesuai struktur project.
        """
        import os
        from datetime import datetime

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        for pair, tf_data in all_data.items():
            for tf, exchange_data in tf_data.items():
                path = f"{base_path}/{pair}/{tf}"
                os.makedirs(path, exist_ok=True)

                try:
                    if not exchange_data["aggregated"].empty:
                        exchange_data["aggregated"].reset_index().to_json(
                            f"{path}/aggregated_{timestamp}.json",
                            orient="records",
                            date_format="iso",
                            indent=4,
                        )
                except Exception as e:
                    logger.warning(f"Failed to save {pair} {tf}: {e}")

        logger.info(f"Raw market data saved to {base_path}")

    def get_available_pairs(self) -> List[str]:
        """Return list pair yang sedang aktif di config"""
        return self.pairs
