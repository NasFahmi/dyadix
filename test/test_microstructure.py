import os
import sys
import time
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Setup Logging to print websocket activity
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from service.market.hyperliquid.hyperliquid_microstructure import HyperliquidMicrostructureCollector

def main():
    print("=" * 60)
    print("  DYADIX - Hyperliquid Microstructure Test")
    print("=" * 60)
    print("Starting collector and connecting to WebSocket...")
    
    collector = HyperliquidMicrostructureCollector()
    collector.start()
    
    # Let it gather some data for 15 seconds
    try:
        for i in range(8):
            time.sleep(2)
            print(f"\n--- [Tick {i+1}/8] Microstructure Metrics Snapshot ---")
            for pair in collector.pairs:
                metrics = collector.get_metrics(pair)
                print(f"\nPair: {pair}")
                print(f"  CVD (5m)                 : ${metrics['cvd_5m_usd']:,.2f} USD")
                print(f"  CVD (15m)                : ${metrics['cvd_15m_usd']:,.2f} USD")
                print(f"  CVD (1h)                 : ${metrics['cvd_1h_usd']:,.2f} USD")
                print(f"  Orderbook Imbalance (Top5): {metrics['orderbook_imbalance_top5']:.4f} (range: -1 to +1)")
                print(f"  Whale Activity (15m)     : Buys: {metrics['whale_buy_count_15m']} (${metrics['whale_buy_vol_usd_15m']:,.2f} USD) | "
                      f"Sells: {metrics['whale_sell_count_15m']} (${metrics['whale_sell_vol_usd_15m']:,.2f} USD)")
                print(f"  Liquidations (15m)       : Longs: ${metrics['long_liquidations_usd_15m']:,.2f} USD | "
                      f"Shorts: ${metrics['short_liquidations_usd_15m']:,.2f} USD")
                print(f"  Aggressive Flow (5m)     : Avg Size: ${metrics['avg_trade_size_usd_5m']:,.2f} USD | "
                      f"Trades/Min: {metrics['trades_per_minute_5m']}")
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        print("\nStopping collector...")
        collector.stop()
        print("Collector stopped. Test completed.")

if __name__ == "__main__":
    main()
