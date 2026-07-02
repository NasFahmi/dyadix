import sys
import os
import logging

# Ensure root of project is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_test():
    from workflows.trading_workflow import create_trading_workflow
    
    logger.info("Initializing LangGraph Trading Workflow...")
    app = create_trading_workflow()
    logger.info("Workflow compiled successfully.")
    
    # Mock input state
    initial_state = {
        "symbol": "BTCUSDC",
        "realtime_price": 95000.0,
        "current_market_session": "London",
        "market_data": {
            "overall_technical_bias": "Strong Bullish",
            "daily_bias": {
                "bias": "Bullish"
            },
            "volatility_5m": {
                "atr": 450.0
            },
            "trend_1h": {
                "trend_regime": "Strong Uptrend"
            },
            "momentum_15m": {
                "rsi": 62.0
            },
            "price_action_5m": {
                "pa_bias": "Bullish",
                "is_bullish_engulfing": True
            }
        },
        "sentiment_data": {
            "overall_sentiment": "Bullish",
            "sentiment_score": 68,
            "components": {
                "fear_greed": {
                    "value": 72,
                    "sentiment_class": "Greed"
                }
            }
        },
        "derivatives_data": {
            "derivatives_sentiment": "Bullish",
            "funding_rate": {
                "latest": 0.0001
            },
            "open_interest": {
                "latest_oi_change": 2.5
            }
        },
        "liquidity_data": {
            "liquidity_sentiment": "Bullish (PDL Sweep)",
            "key_levels": {
                "pdl": 94500.0,
                "pdh": 96200.0
            }
        },
        "correlation_data": {},
        "microstructure_data": {},
        "signal_detector_result": {
            "confidence": 0.78,
            "suggested_bias": "Bullish"
        },
        "errors": []
    }
    
    logger.info("Invoking workflow with mock inputs...")
    result = app.invoke(initial_state)
    
    print("\n" + "=" * 60)
    print("  LANGGRAPH WORKFLOW RUN SUCCESSFUL")
    print("=" * 60)
    print(f"Symbol           : {result.get('symbol')}")
    print(f"Tech Verdict     : {result.get('technical_verdict')}")
    print(f"Liquidity Verdict: {result.get('liquidity_verdict')}")
    print(f"Derivatives Vert : {result.get('derivatives_verdict')}")
    print(f"Sentiment Verdict: {result.get('sentiment_verdict')}")
    print(f"Consensus        : {result.get('aggregated_verdict')}")
    print(f"Risk Verdict     : {result.get('risk_verdict')}")
    print(f"Final Decision   : {result.get('final_decision')}")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_test()
