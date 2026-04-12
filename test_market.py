import pandas as pd
from utils.ohlcv_aggregator import OHLCVAggregator
from service.market.binance.binance_service import BinanceService
from service.market.bybit.bybit_service import BybitService
from typing import List, Dict

class MarketService:
    def __init__(self, pairs: List[str] = None, timeframes: List[str] = None):
        self.binance_service = BinanceService()
        self.bybit_service = BybitService()
        self.pairs = pairs or ["BTC/USDT"]
        self.timeframes = timeframes or ["1h"]

    def fetch_and_aggregate_data(self) -> Dict:
        aggregated_data = {}

        for pair in self.pairs:
            aggregated_data[pair] = {}

            for tf in self.timeframes:
                binance_df = self.binance_service.get_ohlcv(pair, tf)
                bybit_df = self.bybit_service.get_ohlcv(pair, tf)

                # Convert to DataFrame since get_ohlcv returns list of lists
                if binance_df:
                    binance_df = pd.DataFrame(binance_df, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    binance_df['timestamp'] = pd.to_datetime(binance_df['timestamp'], unit='ms')
                    binance_df.set_index('timestamp', inplace=True)
                else:
                    binance_df = pd.DataFrame()
                    
                if bybit_df:
                    bybit_df = pd.DataFrame(bybit_df, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    bybit_df['timestamp'] = pd.to_datetime(bybit_df['timestamp'], unit='ms')
                    bybit_df.set_index('timestamp', inplace=True)
                else:
                    bybit_df = pd.DataFrame()

                agg_df = OHLCVAggregator.aggregate(
                    df_binance=binance_df,
                    df_bybit=bybit_df,
                    method="volume_weighted",  # ← rekomendasi untuk MVP
                )

                aggregated_data[pair][tf] = {
                    "binance": binance_df,
                    "bybit": bybit_df,
                    "aggregated": agg_df,
                }
                
        return aggregated_data

if __name__ == "__main__":
    service = MarketService(pairs=["BTC/USDT"], timeframes=["1m"])
    data = service.fetch_and_aggregate_data()
    print(data["BTC/USDT"]["1m"]["aggregated"].head())
