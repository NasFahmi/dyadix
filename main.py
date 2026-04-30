"""
main.py — Entry point Dyadix Trading DSS

Dua mode operasi:
  1. Loop mode (default): Berjalan terus-menerus dengan signal detection
     → python main.py
  2. One-shot mode: Jalankan pipeline sekali lalu exit
     → python main.py --once

Konfigurasi pair aktif: config/settings.yml
Konfigurasi model LLM : .env  (DECISION_LLM_MODEL, NEWS_SOCIAL_ANALYSIS_MODEL)
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def run_once():
    """Mode one-shot: jalankan pipeline lengkap sekali lalu exit."""
    from pipelines.main_pipeline import MainPipeline

    pipeline = MainPipeline()
    results = pipeline.run(ignore_session=True)

    # ── Print ringkasan keputusan per pair ────────────────────────────
    print("\n" + "=" * 60)
    print("  DYADIX — Trading Decision Summary")
    print("=" * 60)

    for pair, data in results.items():
        if "error" in data and "decision" not in data:
            print(f"\n❌ {pair}: ERROR — {data.get('error', 'unknown')}")
            continue

        decision = data.get("decision", {})
        ctx = data.get("full_context", {})

        print(f"\n{'─' * 50}")
        print(f"  Pair    : {pair}")
        print(f"  Decision: {decision.get('decision', 'N/A')}")
        print(f"  Bias    : {decision.get('bias', 'N/A')}")
        print(f"  Confidence : {decision.get('confidence', 'N/A')}")
        print(f"  Final Bias (engine): {ctx.get('final_bias', 'N/A')}")
        print(f"  Timeframe  : {decision.get('recommended_timeframe', 'N/A')}")
        print(f"  Entry Zone : {decision.get('entry_zone', 'N/A')}")
        print(f"  Target     : {decision.get('target', 'N/A')}")
        print(f"  Stop Loss  : {decision.get('stop_loss', 'N/A')}")
        print(f"  RR Ratio   : {decision.get('risk_reward', 'N/A')}")
        print(f"  Expected   : {decision.get('expected_move', 'N/A')}")
        print(f"  Reason     : {decision.get('reason', 'N/A')}")
        key_risks = decision.get("key_risks", [])
        if key_risks:
            print(f"  Key Risks  : {' | '.join(key_risks)}")
        print(f"  Invalid if : {decision.get('invalidated_if', 'N/A')}")
        print(f"  Summary    : {ctx.get('overall_context_summary', 'N/A')}")

    print("\n" + "=" * 60)
    print("  Pipeline completed.")
    print("=" * 60)


def run_loop():
    """Mode loop: jalankan DSS secara continuous dengan signal detection."""
    from pipelines.loop_scheduler import LoopScheduler

    scheduler = LoopScheduler()
    scheduler.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Dyadix Trading DSS — Decision Support System"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run pipeline once then exit (one-shot mode)",
    )
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        run_loop()
