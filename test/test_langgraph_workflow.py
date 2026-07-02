import pytest
from workflows.trading_workflow import create_trading_workflow
from workflows.state import DyadixState

def test_langgraph_workflow_compiles():
    """Memastikan LangGraph compiled successfully."""
    app = create_trading_workflow()
    assert app is not None

def test_rule_based_analysts_confluence():
    """Memastikan logical rule-based analyst nodes mengembalikan output yang benar."""
    from workflows.nodes.technical_analyst import technical_analyst_node
    from workflows.nodes.liquidity_analyst import liquidity_analyst_node
    from workflows.nodes.derivatives_analyst import derivatives_analyst_node
    from workflows.nodes.sentiment_analyst import sentiment_analyst_node
    
    mock_state = {
        "symbol": "BTCUSDC",
        "realtime_price": 95000.0,
        "current_market_session": "London",
        "market_data": {
            "overall_technical_bias": "Strong Bullish",
            "daily_bias": {"bias": "Bullish"},
            "volatility_5m": {"atr": 450.0},
            "trend_1h": {"trend_regime": "Strong Uptrend"},
            "momentum_15m": {"rsi": 62.0},
            "price_action_5m": {"pa_bias": "Bullish", "is_bullish_engulfing": True}
        },
        "sentiment_data": {
            "overall_sentiment": "Bullish",
            "sentiment_score": 68,
            "components": {
                "fear_greed": {"value": 72, "sentiment_class": "Greed"}
            }
        },
        "derivatives_data": {
            "derivatives_sentiment": "Bullish",
            "funding_rate": {"latest": 0.0001},
            "open_interest": {"latest_oi_change": 2.5}
        },
        "liquidity_data": {
            "liquidity_sentiment": "Bullish (PDL Sweep)",
            "key_levels": {"pdl": 94500.0, "pdh": 96200.0}
        },
        "correlation_data": {},
        "microstructure_data": {},
        "signal_detector_result": {
            "confidence": 0.78,
            "suggested_bias": "Bullish"
        },
        "errors": []
    }
    
    # Run individual analyst nodes
    tech_out = technical_analyst_node(mock_state)
    assert "technical_verdict" in tech_out
    assert tech_out["technical_verdict"]["bias"] == "Strong Bullish"
    assert tech_out["technical_verdict"]["confidence"] >= 0.70
    
    liq_out = liquidity_analyst_node(mock_state)
    assert "liquidity_verdict" in liq_out
    assert liq_out["liquidity_verdict"]["bias"] == "Bullish"
    
    deriv_out = derivatives_analyst_node(mock_state)
    assert "derivatives_verdict" in deriv_out
    assert deriv_out["derivatives_verdict"]["bias"] == "Bullish"
    
    from config.settings import get_config
    config = get_config()
    features = config.get("features", {})
    sent_enabled = any(features.get(k, False) for k in ["enable_reddit_scraper", "enable_news", "enable_fear_greed", "enable_twitter_influencer"])
    
    sent_out = sentiment_analyst_node(mock_state)
    assert "sentiment_verdict" in sent_out
    if sent_enabled:
        assert sent_out["sentiment_verdict"]["bias"] == "Bullish"
    else:
        assert sent_out["sentiment_verdict"]["bias"] == "Neutral"

def test_risk_manager_calculations():
    """Memastikan risk manager menghitung SL, TP, dan status cleared dengan benar."""
    from workflows.nodes.risk_manager import risk_manager_node
    
    mock_state = {
        "symbol": "BTCUSDC",
        "realtime_price": 95000.0,
        "market_data": {
            "volatility_5m": {"atr": 500.0}
        },
        "aggregated_verdict": {
            "consensus_bias": "Strong Bullish",
            "consensus_confidence": 0.8
        }
    }
    
    out = risk_manager_node(mock_state)
    assert "risk_verdict" in out
    verdict = out["risk_verdict"]
    assert verdict["cleared"] is True
    # Long: SL = 95000 - 2 * 500 = 94000
    assert verdict["stop_loss"] == 94000.0
    # TP = 95000 + 3.0 * (95000 - 94000) = 98000
    assert verdict["take_profit"] == 98000.0
    assert verdict["risk_reward"] == "1:3.0"
