import os
import sys
import json
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pipelines.main_pipeline import MainPipeline
from workflows.trading_workflow import create_trading_workflow

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def test_live_integration():
    print("=" * 70)
    print("  LIVE INTEGRATION TEST: LANGGRAPH MULTI-AGENT WITH REAL MARKET DATA")
    print("=" * 70)
    
    pipeline = MainPipeline()
    pairs = pipeline.market_service.pairs
    
    print(f"\n[STEP 1] Fetching live market data for candidates: {pairs}...")
    market_data = pipeline.market_service.fetch_ohlcv_all(limit=100)
    
    print("\n[STEP 2] Building sentiment, correlation, and derivatives data...")
    sentiment_result = pipeline._build_sentiment(market_data)
    correlation_data = pipeline._build_correlation(market_data)
    derivatives_data = pipeline._build_mock_derivatives(market_data)
    
    print("\n[STEP 3] Aggregating full context...")
    from features.context_builder import build_full_context
    full_contexts = build_full_context(
        market_data=market_data,
        sentiment_result=sentiment_result,
        derivatives_data=derivatives_data,
        correlation_data=correlation_data,
        target_pairs=pairs,
    )
    
    all_decisions = []
    
    print("\n[STEP 4] Running LangGraph Trading Workflow for each candidate...")
    for pair in pairs:
        ctx = full_contexts.get(pair)
        if not ctx or "error" in ctx:
            print(f"❌ Failed to build context for {pair}: {ctx.get('error') if ctx else 'No context'}")
            continue
            
        # Inject candle summaries and market snapshots
        ctx = pipeline._inject_candle_summary(ctx, market_data.get(pair, {}))
        ctx = pipeline._inject_market_snapshot(ctx, market_data.get(pair, {}))
        
        # Mock signal detector results to force the flow to LLM Decision Node
        # We vary the confidence to test the portfolio ranking
        import random
        confidence_val = round(random.uniform(0.75, 0.95), 2)
        signal_result = {
            "has_potential_signal": True,
            "confidence": confidence_val,
            "suggested_bias": "Bullish",
            "signal_type": "LONG",
            "reasons": ["Manual override: Testing LangGraph execution flow"]
        }
        
        ctx["signal_detector_result"] = signal_result
        
        initial_state = {
            "symbol": pair,
            "realtime_price": ctx.get("current_price", 0.0),
            "current_market_session": ctx.get("current_market_session", "Unknown"),
            "market_data": ctx.get("technical", {}),
            "sentiment_data": ctx.get("sentiment", {}),
            "derivatives_data": ctx.get("derivatives", {}),
            "liquidity_data": ctx.get("liquidity", {}),
            "correlation_data": ctx.get("correlation", {}),
            "microstructure_data": ctx.get("microstructure", {}),
            "signal_detector_result": signal_result,
            "errors": []
        }
        if "current_price" not in initial_state["market_data"] and "current_price" in ctx:
            initial_state["market_data"]["current_price"] = ctx["current_price"]
            
        print(f"\n📢 Invoking LangGraph for {pair}...")
        workflow = create_trading_workflow()
        workflow_result = workflow.invoke(initial_state)
        
        decision = workflow_result.get("trade_verdict", {})
        all_decisions.append((pair, ctx, signal_result, decision))
        
        print("\n" + "=" * 60)
        print(f"  LANGGRAPH LIVE EXECUTION RESULT FOR {pair}")
        print("=" * 60)
        print(f"Symbol           : {workflow_result.get('symbol')}")
        print(f"Consensus Bias   : {workflow_result.get('aggregated_verdict', {}).get('consensus_bias')}")
        print(f"Risk Cleared     : {workflow_result.get('risk_verdict', {}).get('cleared')}")
        print(f"SL Target        : SL {workflow_result.get('risk_verdict', {}).get('stop_loss')} / TP {workflow_result.get('risk_verdict', {}).get('take_profit')}")
        print(f"Final Action     : {decision.get('decision')}")
        print(f"LLM Reasoning    : {decision.get('reason')}")
        print(f"Execution Type   : {decision.get('execution_type')}")
        print(f"Target Price     : {decision.get('target')}")
        print(f"Stop Loss Price  : {decision.get('stop_loss')}")
        print("=" * 60 + "\n")

    # === STEP 5: PORTFOLIO & CORRELATION FILTER ===
    print("\n" + "=" * 70)
    print("  STEP 5: PORTFOLIO SELECTOR & CORRELATION FILTER ANALYSIS")
    print("=" * 70)
    
    # Portfolio Selector: Filter active decisions (BUY/SELL)
    active_candidates = [item for item in all_decisions if item[3].get("decision") in ["BUY", "SELL"]]
    # Rank by signal confidence (descending)
    active_candidates.sort(key=lambda x: x[2]["confidence"], reverse=True)
    
    print(f"\n💼 Portfolio Selector: Found {len(active_candidates)} active trade signals (BUY/SELL) out of {len(all_decisions)} pairs.")
    for c in active_candidates:
        print(f"   - Candidate: {c[0]} | Action: {c[3].get('decision')} | Signal Confidence: {c[2]['confidence']}")
        
    final_trade_candidates = []
    correlation_limit = 0.7
    
    print(f"\n⚡ Running Correlation Filter (limit: {correlation_limit})...")
    for candidate in active_candidates:
        pair, ctx, signal_result, decision = candidate
        is_correlated = False
        
        for selected in final_trade_candidates:
            sel_pair = selected[0]
            # Look up correlation in correlation_data
            matrix = correlation_data.get("matrix", {})
            corr_val = matrix.get(pair, {}).get(sel_pair, 0.0)
            
            if abs(corr_val) > correlation_limit:
                print(f"   ❌ Skip {pair}: Highly correlated with selected {sel_pair} (corr: {corr_val:.2f})")
                is_correlated = True
                break
                
        if not is_correlated:
            final_trade_candidates.append(candidate)
            print(f"   📥 Accept {pair}: Low correlation with selected portfolio.")
            
    print("\n" + "=" * 70)
    print("  🏆 FINAL TRADE CANDIDATES (PORTFOLIO SELECTOR OUTPUT)")
    print("=" * 70)
    if final_trade_candidates:
        for idx, item in enumerate(final_trade_candidates, 1):
            print(f"  {idx}. {item[0]} -> {item[3].get('decision')} (Signal Confidence: {item[2]['confidence']})")
    else:
        print("  No active trade candidates selected.")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    test_live_integration()
