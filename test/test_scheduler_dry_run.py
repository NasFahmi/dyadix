import os
import sys
import time
import json
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

def main():
    print("=" * 60)
    print("  DYADIX - Scheduler Microstructure Dry-Run Test")
    print("=" * 60)
    
    # 1. Initialize LoopScheduler components
    from pipelines.loop_scheduler import LoopScheduler
    from features.context_builder import build_full_context
    
    scheduler = LoopScheduler()
    
    # Start the microstructure collector
    print("\n[STEP 1] Starting microstructure collector...")
    scheduler.microstructure_collector.start()
    
    # Refresh data manager once to get technical/sentiment/derivatives caches ready
    print("\n[STEP 2] Pre-fetching and caching other market data layers...")
    scheduler.data_manager.refresh_stale_data()
    
    print("\nWaiting 5 seconds to collect real-time trade and orderbook stream updates...")
    time.sleep(5)
    
    # 2. Re-create the cycle context building logic
    print("\n[STEP 3] Fetching data and building full context...")
    market_data = scheduler.data_manager.get_market_data()
    if not market_data:
        print("[ERR] No market data available. Make sure internet connection is active.")
        scheduler.microstructure_collector.stop()
        sys.exit(1)
        
    sentiment_result = scheduler.data_manager.get_sentiment_result()
    correlation_data = scheduler.data_manager.get_correlation_data()
    derivatives_data = scheduler.data_manager.get_derivatives_data()
    
    # Fetch microstructure data
    microstructure_data = {}
    for pair in scheduler.data_manager.pairs:
        microstructure_data[pair] = scheduler.microstructure_collector.get_metrics(pair)
        
    # Build context
    try:
        full_contexts = build_full_context(
            market_data=market_data,
            sentiment_result=sentiment_result,
            derivatives_data=derivatives_data,
            correlation_data=correlation_data,
            target_pairs=scheduler.data_manager.pairs,
            microstructure_data=microstructure_data,
        )
    except Exception as e:
        print(f"[ERR] Failed to build full context: {e}")
        scheduler.microstructure_collector.stop()
        sys.exit(1)
        
    # Print the built context for the first target pair
    target_pair = scheduler.data_manager.pairs[0]
    ctx = full_contexts.get(target_pair, {})
    
    # Inject extra context (last candles & market snapshot) as LoopScheduler does
    ctx = scheduler._inject_extra_context(ctx, market_data.get(target_pair, {}))
    
    print(f"\n--- Aggregated Context for {target_pair} (Truncated view of Microstructure part) ---")
    print(json.dumps(ctx.get("microstructure"), indent=2))
    
    # 3. Call the Decision LLM
    print("\n[STEP 4] Calling Decision LLM with full context...")
    
    # Add temporary placeholder fields normally injected by the loop scheduler right before LLM call
    realtime_price = scheduler._fetch_realtime_price(target_pair)
    ctx["realtime_price"] = realtime_price
    ctx["signal_detector_result"] = {
        "suggested_bias": "Moderate Bullish", # Mock signal details
        "signal_type": "DIVERGENCE",
        "confidence": 0.75,
        "reasons": ["RSI Oversold", "Orderbook Bid Imbalance"],
    }
    
    decision = scheduler._call_decision_llm(ctx)
    
    print("\n" + "=" * 60)
    print("  DECISION LLM OUTPUT")
    print("=" * 60)
    print(json.dumps(decision, indent=2))
    print("=" * 60)
    
    print("\nStopping collector...")
    scheduler.microstructure_collector.stop()
    print("Test finished successfully.")

if __name__ == "__main__":
    main()
