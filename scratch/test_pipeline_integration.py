import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from service.market.market_service import MarketService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    print("=" * 60)
    print("  Testing Dyadix MarketService & Screening Integration")
    print("=" * 60)

    print("\n[1] Initializing MarketService...")
    ms = MarketService()
    
    active_pairs = ms.get_available_pairs()
    print(f"\n[OK] Active Pairs in MarketService ({len(active_pairs)}):")
    for i, p in enumerate(active_pairs, 1):
        print(f"  {i:>2}. {p}")

    print("\n" + "=" * 60)
    print("  Integration Test Completed Successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()
