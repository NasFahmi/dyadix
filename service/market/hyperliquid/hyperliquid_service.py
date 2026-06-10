import os
import pandas as pd
import time
import logging
from typing import Optional
from hyperliquid.info import Info
from hyperliquid.utils import constants

logger = logging.getLogger(__name__)

class HyperliquidService:
    def __init__(self):
        """
        Inisialisasi HyperliquidService.
        Menghubungkan ke endpoint public Info dari Hyperliquid.
        """
        testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"
        base_url = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL
        self.info = Info(base_url, skip_ws=True)
        mode = "TESTNET" if testnet else "PRODUCTION"
        logger.info(f"HyperliquidService initialized [{mode}]")

    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 100) -> pd.DataFrame:
        """
        Ambil data OHLCV untuk coin tertentu dari Hyperliquid.
        
        Args:
            symbol   : Kode pair, e.g. "BTCUSDT" atau "BTC"
            timeframe: Interval candle, e.g. "3m", "5m", "15m", "1h", "1d"
            limit    : Jumlah candle yang diminta
            
        Returns:
            pd.DataFrame: DataFrame berisi data candlestick dengan index timestamp.
        """
        # Konversi symbol dari format Binance (e.g. BTCUSDT) ke Hyperliquid coin (e.g. BTC)
        coin = symbol.replace("USDT", "").replace("USDC", "").replace("/", "").replace(":", "")

        interval = timeframe
        interval_mapping_seconds = {
            "1m": 60,
            "3m": 180,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "2h": 7200,
            "4h": 14400,
            "8h": 28800,
            "1d": 86400,
        }
        
        seconds_per_candle = interval_mapping_seconds.get(interval, 60)
        end_time = int(time.time() * 1000)
        # Tambahkan buffer 50 candle untuk memastikan limit terpenuhi setelah filter
        start_time = end_time - (limit + 50) * seconds_per_candle * 1000

        try:
            logger.debug(f"Fetching candles for {coin} on {interval} timeframe from Hyperliquid...")
            candles = self.info.candles_snapshot(coin, interval, start_time, end_time)
            
            if not candles:
                logger.warning(f"No candles returned for {coin} on {interval}")
                return pd.DataFrame()

            rows = []
            for c in candles:
                rows.append({
                    "timestamp": pd.to_datetime(c["T"], unit="ms"),
                    "open": float(c["o"]),
                    "high": float(c["h"]),
                    "low": float(c["l"]),
                    "close": float(c["c"]),
                    "volume": float(c["v"])
                })
                
            df = pd.DataFrame(rows)
            if not df.empty:
                df.set_index("timestamp", inplace=True)
                df.sort_index(inplace=True)
                df = df.tail(limit)
                
            logger.debug(f"Fetched {len(df)} candles for {coin} ({interval})")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol} ({timeframe}) from Hyperliquid: {e}")
            return pd.DataFrame()
