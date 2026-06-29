import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from service.market.screening.screening_service import ScreeningService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    print("=" * 60)
    print("  Testing Dyadix Market Screening Module (Fase 2)")
    print("=" * 60)

    service = ScreeningService()
    
    print("\n[1] Fetching Ranked Markets & Scores Breakdown...")
    ranked_markets = service.get_ranked_markets(force_refresh=False)
    
    print(f"\n[OK] Total Ranked Markets: {len(ranked_markets)}")
    if ranked_markets:
        print("\nTop 10 Ranked Candidate Markets:")
        print(f"  {'Rank':<5} | {'Symbol':<8} | {'Score':<6} | {'Price':<10} | {'24h Vol (USD)':<16} | {'OI (USD)':<16} | Breakdown (Vol/ATR/OI/Fund)")
        print("  " + "-" * 105)
        for m in ranked_markets[:10]:
            bd = m['scores_breakdown']
            bd_str = f"{bd['volume_score']:.1f}/{bd['volatility_score']:.1f}/{bd['oi_score']:.1f}/{bd['funding_score']:.1f}"
            print(f"  #{m['rank']:<4} | {m['symbol']:<8} | {m['score']:<6.2f} | ${m['price']:<9.2f} | ${m['volume_24h']:>14,.2f} | ${m['open_interest_usd']:>14,.2f} | {bd_str}")

    print("\n[2] Testing Formatted Candidate Symbols for Dyadix Integration...")
    candidate_symbols = service.get_candidate_symbols(force_refresh=False)
    print(f"[OK] Dynamic Top Candidates Count: {len(candidate_symbols)}")
    print("Top Candidate Symbols:", candidate_symbols)

    print("\n" + "=" * 60)
    print("  Fase 2 Market Screening Test Completed Successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()
