"""
services/market/market_service.py

Orchestrator utama untuk mengambil OHLCV dari Binance Futures dan Bybit Futures.
Menggunakan OHLCVAggregator yang sudah kamu buat.
"""

import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
import logging

from config.settings import get_config  # Sesuaikan dengan cara config kamu
from service.market.binance.binance_service import BinanceService
from service.market.bybit.bybit_service import BybitService
from utils.ohlcv_aggregator import OHLCVAggregator

logger = logging.getLogger(__name__)


class MarketService:
    """
    Service utama untuk mengelola data market (OHLCV) dari multiple exchange.
    """

    def __init__(self):
        self.config = get_config()
        self.binance = BinanceService()
        self.bybit = BybitService()

        # Ambil konfigurasi dari settings.yaml
        self.pairs: List[str] = self.config.get("trading", {}).get("pairs", ["BTCUSDT"])
        self.timeframes: List[str] = self.config.get("trading", {}).get(
            "timeframes", ["5m", "15m", "1h"]
        )
        self.agg_method: str = "volume_weighted"  # default sesuai pilihan kamu

        logger.info(
            f"MarketService initialized with {len(self.pairs)} pairs "
            f"and timeframes: {self.timeframes}"
        )

    def fetch_ohlcv_all(
        self, limit: int = 500, agg_method: Optional[str] = None
    ) -> Dict:
        """
        Fetch OHLCV untuk semua pair dan semua timeframe yang ada di config.

        Return structure:
        {
            "BTCUSDT": {
                "5m": {
                    "binance": df,
                    "bybit": df,
                    "aggregated": df
                },
                "15m": { ... },
                "1h": { ... }
            },
            "ETHUSDT": { ... }
        }
        """
        if agg_method is None:
            agg_method = self.agg_method

        all_data = {}

        for pair in self.pairs:
            logger.info(f"Fetching OHLCV for {pair}...")
            pair_data = {}

            for tf in self.timeframes:
                try:
                    # Fetch dari Binance Futures
                    df_binance = self.binance.fetch_ohlcv(
                        symbol=pair, timeframe=tf, limit=limit
                    )

                    # Fetch dari Bybit Futures
                    df_bybit = self.bybit.fetch_ohlcv(
                        symbol=pair, timeframe=tf, limit=limit
                    )

                    # Aggregate menggunakan volume_weighted
                    df_aggregated = OHLCVAggregator.aggregate(
                        df_binance=df_binance, df_bybit=df_bybit, method=agg_method
                    )

                    pair_data[tf] = {
                        "binance": df_binance,
                        "bybit": df_bybit,
                        "aggregated": df_aggregated,
                        "last_updated": datetime.utcnow(),
                    }

                    logger.debug(
                        f"✓ {pair} {tf} aggregated successfully | "
                        f"Rows: {len(df_aggregated)}"
                    )

                except Exception as e:
                    logger.error(f"❌ Failed to fetch/aggregate {pair} {tf}: {e}")
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
        Fetch data hanya untuk satu pair tertentu (berguna untuk testing atau mode single pair).
        """
        if timeframes is None:
            timeframes = self.timeframes

        logger.info(f"Fetching single pair: {pair}")

        pair_data = {}
        for tf in timeframes:
            try:
                df_binance = self.binance.fetch_ohlcv(pair, tf, limit)
                df_bybit = self.bybit.fetch_ohlcv(pair, tf, limit)

                df_aggregated = OHLCVAggregator.aggregate(
                    df_binance, df_bybit, method=self.agg_method
                )

                pair_data[tf] = {
                    "binance": df_binance,
                    "bybit": df_bybit,
                    "aggregated": df_aggregated,
                }
            except Exception as e:
                logger.error(f"Error fetching {pair} {tf}: {e}")
                pair_data[tf] = {"error": str(e)}

        return pair_data

    def get_latest_candles(self, pair: str, timeframe: str = "15m", n: int = 1) -> Dict:
        """
        Ambil candle terbaru (berguna untuk quick check di detection nanti).
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
        Simpan raw data (binance, bybit, aggregated) ke folder sesuai struktur project.
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
                        exchange_data["aggregated"].to_parquet(
                            f"{path}/aggregated_{timestamp}.parquet"
                        )
                        # exchange_data["aggregated"].reset_index().to_json(
                        #     f"{path}/aggregated_{timestamp}.json",
                        #     orient="records",
                        #     date_format="iso",
                        #     indent=4,
                        # )
                    # Kamu bisa juga simpan binance & bybit kalau perlu untuk debugging
                except Exception as e:
                    logger.warning(f"Failed to save {pair} {tf}: {e}")

        logger.info(f"Raw market data saved to {base_path}")

    def get_available_pairs(self) -> List[str]:
        """Return list pair yang sedang aktif di config"""
        return self.pairs
