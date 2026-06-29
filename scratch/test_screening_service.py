import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from service.market.screening.screening_service import ScreeningService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    print("=" * 60)
    print("  Testing Dyadix Market Screening Module (Fase 1)")
    print("=" * 60)

    service = ScreeningService()
    
    print("\n[1] Testing Live Market Collection & Universe Filtering...")
    filtered_markets = service.get_filtered_markets(force_refresh=True)
    
    print(f"\n[OK] Total markets passing filter (Volume >= $1M): {len(filtered_markets)}")
    if filtered_markets:
        print("\nTop 5 Sample Filtered Markets:")
        for m in filtered_markets[:5]:
            print(f"  - {m['symbol']:<8} | Price: ${m['price']:<10.2f} | 24h Vol: ${m['volume_24h']:>14,.2f} | OI (USD): ${m['open_interest_usd']:>14,.2f} | Funding: {m['funding_rate']}")

    print("\n[2] Testing Caching Mechanism (Second fetch should hit cache)...")
    cached_markets = service.get_filtered_markets(force_refresh=False)
    print(f"[OK] Retrieved {len(cached_markets)} markets from cache.")

    candidate_symbols = service.get_candidate_symbols()
    print(f"\n[OK] Candidate Symbols Count: {len(candidate_symbols)}")
    print("Sample Candidate Symbols:", candidate_symbols[:10])

    print("\n" + "=" * 60)
    print("  Fase 1 Market Screening Test Completed Successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()
