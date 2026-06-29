import os
import sys
import json
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pipelines.main_pipeline import MainPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    print("=" * 70)
    print("  DYADIX END-TO-END SIMULATION: SCREENING -> SIGNAL DETECTOR -> FINAL DECISION")
    print("=" * 70)

    print("\n[STEP 1] Inisialisasi MainPipeline (Loading Dynamic Screening Pairs)...")
    pipeline = MainPipeline()
    print(f"[OK] Active Scan Candidates ({len(pipeline.market_service.pairs)} pairs): {pipeline.market_service.pairs}")

    print("\n[STEP 2 & 3] Running Pipeline Data Fetching, Context Building & Signal Pre-Scoring...")
    results = pipeline.run(ignore_session=True)

    print("\n" + "=" * 70)
    print("  SUMMARY KEPUTUSAN FINAL (END-TO-END PIPELINE)")
    print("=" * 70)

    evaluated_count = 0
    decision_count = 0

    for pair, data in results.items():
        evaluated_count += 1
        if "signal_skipped" in data and data["signal_skipped"]:
            print(f"\n[SKIP] {pair:<10} : SKIPPED — Signal Detector (Confidence below threshold / No setup)")
            continue

        if "error" in data and "decision" not in data:
            print(f"\n[ERROR] {pair:<10} : ERROR — {data.get('error', 'unknown')}")
            continue

        decision_count += 1
        decision = data.get("decision", {})
        ctx = data.get("full_context", {})
        sig = ctx.get("signal_detector_result", {})

        print(f"\n{'─' * 60}")
        print(f"  [TARGET] PAIR PASSED TO FINAL DECISION : {pair}")
        print(f"  {'─' * 60}")
        print(f"  Signal Detector Assessment : {sig.get('suggested_bias')} (Type: {sig.get('signal_type')}, Confidence: {sig.get('confidence')})")
        print(f"  Signal Reasons             : {' | '.join(sig.get('reasons', []))}")
        print(f"  LLM Final Decision         : {decision.get('decision', 'N/A')}")
        print(f"  LLM Bias / Confidence      : {decision.get('bias', 'N/A')} ({decision.get('confidence', 'N/A')})")
        print(f"  Recommended Timeframe     : {decision.get('recommended_timeframe', 'N/A')}")
        print(f"  Entry Zone                 : {decision.get('entry_zone', 'N/A')}")
        print(f"  Target (TP) / Stop Loss (SL): {decision.get('target', 'N/A')} / {decision.get('stop_loss', 'N/A')}")
        print(f"  Risk-Reward Ratio          : {decision.get('risk_reward', 'N/A')}")
        print(f"  Analysis Reason            : {decision.get('reason', 'N/A')}")
        key_risks = decision.get("key_risks", [])
        if key_risks:
            print(f"  Key Risks                  : {' | '.join(key_risks)}")

    print("\n" + "=" * 70)
    print(f"  Simulasi Selesai: {evaluated_count} candidate pairs dievaluasi | {decision_count} pair diteruskan ke Final Decision LLM")
    print("=" * 70)

if __name__ == "__main__":
    main()
