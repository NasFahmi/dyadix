import os
import pandas as pd
import time
import logging
from datetime import datetime
from hyperliquid.info import Info
from hyperliquid.utils import constants

logger = logging.getLogger(__name__)

class HyperliquidDerivativesService:
    def __init__(self):
        """
        Inisialisasi HyperliquidDerivativesService.
        Menghubungkan ke endpoint public Info dari Hyperliquid.
        """
        testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"
        base_url = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL
        self.info = Info(base_url, skip_ws=True)

    def fetch_funding_rate(self, symbol: str, limit: int = 24) -> pd.DataFrame:
        """
        Fetch data riwayat funding rate untuk satu coin perpetual.
        
        Args:
            symbol: e.g. "BTCUSDT"
            limit : Jumlah record yang diambil (di Hyperliquid, funding dibayar per 1 jam)
            
        Returns:
            pd.DataFrame: DataFrame berisi kolom timestamp dan funding_rate.
        """
        coin = symbol.replace("USDT", "").replace("USDC", "").replace("/", "").replace(":", "")
        try:
            # Karena funding rate di Hyperliquid diperbarui setiap jam,
            # kita ambil data historis 1 jam * limit.
            end_time = int(time.time() * 1000)
            start_time = end_time - (limit * 3600 * 1000)
            
            logger.debug(f"Fetching funding rate history for {coin} from Hyperliquid...")
            funding_data = self.info.funding_history(coin, start_time, end_time)
            
            if not funding_data:
                logger.warning(f"No funding rate history found for {coin}")
                return pd.DataFrame()

            rows = []
            for entry in funding_data:
                rows.append({
                    "timestamp": pd.to_datetime(entry["time"], unit="ms"),
                    "funding_rate": float(entry["fundingRate"])
                })
                
            df = pd.DataFrame(rows)
            if not df.empty:
                df.set_index("timestamp", inplace=True)
                df.sort_index(inplace=True)
                df = df.tail(limit)
                
            logger.debug(f"Fetched {len(df)} funding entries for {coin}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching funding rate for {symbol} from Hyperliquid: {e}")
            return pd.DataFrame()

    def fetch_open_interest(self, symbol: str) -> pd.DataFrame:
        """
        Fetch data Open Interest saat ini untuk satu coin perpetual.
        
        Args:
            symbol: e.g. "BTCUSDT"
            
        Returns:
            pd.DataFrame: DataFrame dengan baris tunggal berisi timestamp dan open_interest.
        """
        coin = symbol.replace("USDT", "").replace("USDC", "").replace("/", "").replace(":", "")
        try:
            logger.debug(f"Fetching asset contexts (for Open Interest) from Hyperliquid...")
            meta, asset_ctxs = self.info.meta_and_asset_ctxs()
            
            oi_value = 0.0
            found = False
            for coin_meta, ctx in zip(meta.get("universe", []), asset_ctxs):
                if coin_meta["name"] == coin:
                    oi_value = float(ctx.get("openInterest", 0.0))
                    found = True
                    break
                    
            if not found:
                logger.warning(f"Coin {coin} not found in Hyperliquid universe meta")
                
            df = pd.DataFrame([
                {
                    "timestamp": pd.to_datetime(int(time.time() * 1000), unit="ms"),
                    "open_interest": oi_value
                }
            ])
            logger.debug(f"Fetched current OI for {coin}: {oi_value:,.0f}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching open interest for {symbol} from Hyperliquid: {e}")
            return pd.DataFrame()
