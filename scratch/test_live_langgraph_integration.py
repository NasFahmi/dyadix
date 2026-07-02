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
    pair = "BTCUSDC"
    
    print(f"\n[STEP 1] Fetching live market data for {pair}...")
    # Fetch data only for BTCUSDC to speed up
    pipeline.market_service.pairs = [pair]
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
        target_pairs=[pair],
    )
    
    ctx = full_contexts.get(pair)
    if not ctx or "error" in ctx:
        print(f"Failed to build context: {ctx}")
        return
        
    # Inject candle summaries and market snapshots
    ctx = pipeline._inject_candle_summary(ctx, market_data.get(pair, {}))
    ctx = pipeline._inject_market_snapshot(ctx, market_data.get(pair, {}))
    
    # Mock signal detector results to force the flow to LLM Decision Node
    signal_result = {
        "has_potential_signal": True,
        "confidence": 0.82,
        "suggested_bias": "Bullish",
        "signal_type": "LONG",
        "reasons": ["Manual override: Testing LangGraph execution flow"]
    }
    
    ctx["signal_detector_result"] = signal_result
    
    print("\n[STEP 4] Compiling initial state for LangGraph...")
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
        
    print("\n[STEP 5] Invoking LangGraph Trading Workflow...")
    workflow = create_trading_workflow()
    workflow_result = workflow.invoke(initial_state)
    
    decision = workflow_result.get("final_decision", {})
    
    print("\n" + "=" * 60)
    print("  LANGGRAPH LIVE EXECUTION RESULT")
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

if __name__ == "__main__":
    test_live_integration()
