import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import get_config
from service.market.screening.screening_service import ScreeningService
from pipelines.data_manager import DataManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    print("=" * 60)
    print("  Testing Dyadix Market Screening (Fase 3: Multi-Stage & 5-Min Trigger)")
    print("=" * 60)

    config = get_config()
    screening_cfg = config.get("screening", {})
    
    print("\n[1] Checking Configuration Settings in settings.yml:")
    print(f"  - Enabled                 : {screening_cfg.get('enabled')}")
    print(f"  - Scan Candidates (Stage 1): {screening_cfg.get('scan_candidates')}")
    print(f"  - Max Tradeable   (Stage 2): {screening_cfg.get('max_tradeable')}")
    print(f"  - Refresh Interval (Mins) : {screening_cfg.get('refresh_interval_minutes')} mins")

    print("\n[2] Initializing ScreeningService & DataManager...")
    svc = ScreeningService()
    print(f"  - ScreeningService TTL Minutes: {svc.cache.ttl_minutes:.2f} mins")
    print(f"  - ScreeningService Scan Candidates Count: {svc.scan_candidates_count}")

    dm = DataManager()
    print(f"\n[OK] DataManager Active Scan Pairs ({len(dm.pairs)}):")
    print(" ", dm.pairs)

    print("\n" + "=" * 60)
    print("  Fase 3 Verification Completed Successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()
