
import pandas as pd
from service.market.binance.binance_service import BinanceService
from service.market.bybit.bybit_service import BybitService
import logging

logging.basicConfig(level=logging.INFO)

def test_sol_5m():
    binance = BinanceService()
    bybit = BybitService()
    
    symbol = "SOLUSDT"
    tf = "5m"
    limit = 100
    
    print(f"Fetching {symbol} {tf} from Binance...")
    df_binance = binance.fetch_ohlcv(symbol, tf, limit=limit)
    
    print(f"Fetching {symbol} {tf} from Bybit...")
    df_bybit = bybit.fetch_ohlcv(symbol, tf, limit=limit)
    
    if df_binance.empty:
        print("Binance data is empty")
    else:
        print(f"Binance timestamps: {df_binance.index[0]} to {df_binance.index[-1]} (Count: {len(df_binance)})")
        print(df_binance.index[:5])
        
    if df_bybit.empty:
        print("Bybit data is empty")
    else:
        print(f"Bybit timestamps: {df_bybit.index[0]} to {df_bybit.index[-1]} (Count: {len(df_bybit)})")
        print(df_bybit.index[:5])

    common = df_binance.index.intersection(df_bybit.index)
    print(f"Common timestamps count: {len(common)}")
    if len(common) > 0:
        print(f"Common timestamps: {common[0]} to {common[-1]}")
    else:
        # Check if there is any overlap at all
        b_min, b_max = df_binance.index.min(), df_binance.index.max()
        y_min, y_max = df_bybit.index.min(), df_bybit.index.max()
        print(f"Binance range: {b_min} - {b_max}")
        print(f"Bybit range:   {y_min} - {y_max}")
        
        # Check for slight offsets
        if len(df_binance) > 0 and len(df_bybit) > 0:
            diff = df_binance.index[0] - df_bybit.index[0]
            print(f"Difference in first timestamp: {diff}")

if __name__ == "__main__":
    test_sol_5m()
