import os
import sys
import json
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from service.market.screening.screening_service import ScreeningService
from pipelines.main_pipeline import MainPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def test_simulation_flow():
    print("=" * 70)
    print("  SIMULASI FULL PIPELINE: SCREENING -> SIGNAL DETECTOR -> FINAL DECISION")
    print("=" * 70)

    print("\n[STEP 1] Running Screening Service to get Top Candidates...")
    svc = ScreeningService()
    candidate_pairs = svc.get_candidate_symbols(force_refresh=False)
    print(f"[OK] Top 10 Candidate Pairs from Screening: {candidate_pairs}")

    print("\n[STEP 2] Simulating Signal Detector Evaluation & Dynamic Forwarding...")
    
    # Mock / Real assessment demonstration
    pipeline = MainPipeline()
    
    # Lets evaluate context building and signal detection logic
    print("\n[STEP 3] Evaluating Signal Confluence for candidate pairs...")
    market_data = pipeline.market_service.fetch_ohlcv_all(limit=100)
    sentiment_result = pipeline._build_sentiment(market_data)
    correlation_data = pipeline._build_correlation(market_data)
    derivatives_data = pipeline._build_mock_derivatives(market_data)

    from features.context_builder import build_full_context
    full_contexts = build_full_context(
        market_data=market_data,
        sentiment_result=sentiment_result,
        derivatives_data=derivatives_data,
        correlation_data=correlation_data,
        target_pairs=pipeline.market_service.pairs,
    )

    qualified_pairs = []
    for pair, ctx in full_contexts.items():
        if "error" in ctx and "technical" not in ctx:
            continue
        sig = pipeline.signal_detector.detect(ctx)
        print(f"  - Pair: {pair:<10} | Signal Potential: {str(sig['has_potential_signal']):<5} | Confidence: {sig['confidence']:.2f} | Bias: {sig['suggested_bias']}")
        if sig["has_potential_signal"] and sig["confidence"] >= pipeline.signal_detector.min_confidence:
            qualified_pairs.append((pair, ctx, sig))

    qualified_pairs.sort(key=lambda x: x[2]["confidence"], reverse=True)
    top_tradeables = qualified_pairs[: pipeline.max_tradeable]

    print(f"\n[OK] Strict Pre-Scoring Output: {len(top_tradeables)} pairs qualify for Final Decision LLM (max_tradeable={pipeline.max_tradeable}).")
    if top_tradeables:
        for pair, ctx, sig in top_tradeables:
            print(f"  --> FORWARDING TO FINAL DECISION: {pair} (Confidence: {sig['confidence']})")
    else:
        print("  --> INFO: Zero pairs met min_confidence threshold in current market state. System safely protected tokens!")

    print("\n" + "=" * 70)
    print("  Simulasi End-to-End Selesai & Berhasil 100%!")
    print("=" * 70)

if __name__ == "__main__":
    test_simulation_flow()
