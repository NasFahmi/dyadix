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
            "price_action_5m": {"pa_bias": "Bullish", "is_bullish_engulfing": True},
            "order_block_1h": {
                "nearest_bullish_ob": {"top": 95100.0, "bottom": 94800.0},
                "nearest_bearish_ob": None
            }
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
        "microstructure_data": {
            "cvd_5m_usd": 150000.0,
            "cvd_15m_usd": 450000.0,
            "orderbook_imbalance_top5": 0.25,
            "whale_buy_count_15m": 5,
            "whale_sell_count_15m": 2,
            "long_liquidations_usd_15m": 0.0,
            "short_liquidations_usd_15m": 30000.0
        },
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
    assert any("Order Block" in r for r in tech_out["technical_verdict"]["reasons"])
    
    liq_out = liquidity_analyst_node(mock_state)
    assert "liquidity_verdict" in liq_out
    assert liq_out["liquidity_verdict"]["bias"] == "Bullish"
    assert any("CVD" in r for r in liq_out["liquidity_verdict"]["reasons"])
    assert any("Orderbook" in r for r in liq_out["liquidity_verdict"]["reasons"])
    
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
    from unittest.mock import patch
    
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
    
    with patch("workflows.nodes.risk_manager.get_config") as mock_get_config:
        mock_get_config.return_value = {
            "risk_management": {
                "risk_per_trade_pct": 1.0,
                "leverage": 10,
                "force_atr_fallback_clearance": True
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

def test_aggregator_market_regimes():
    """Memastikan aggregator_node menggunakan bobot yang benar untuk NORMAL dan HIGH_IMPACT_EVENT."""
    from workflows.nodes.agent_aggregator import aggregator_node
    from datetime import datetime, timezone
    
    # 1. NORMAL Regime State
    state_normal = {
        "symbol": "BTCUSDC",
        "technical_verdict": {"bias": "Bullish", "confidence": 0.8, "reasons": []},
        "liquidity_verdict": {"bias": "Bearish", "confidence": 0.7, "reasons": []},
        "derivatives_verdict": {"bias": "Bullish", "confidence": 0.6, "reasons": []},
        "sentiment_verdict": {"bias": "Neutral", "confidence": 0.5, "reasons": []},
        "sentiment_data": {
            "components": {
                "economic": {
                    "events": []
                }
            }
        }
    }
    
    res_normal = aggregator_node(state_normal)
    assert "aggregated_verdict" in res_normal
    assert res_normal["aggregated_verdict"]["market_regime"] == "NORMAL"
    
    # 2. HIGH_IMPACT_EVENT Regime State (CPI within 24h)
    state_high_impact = {
        "symbol": "BTCUSDC",
        "technical_verdict": {"bias": "Bullish", "confidence": 0.8, "reasons": []},
        "liquidity_verdict": {"bias": "Bearish", "confidence": 0.7, "reasons": []},
        "derivatives_verdict": {"bias": "Bullish", "confidence": 0.6, "reasons": []},
        "sentiment_verdict": {"bias": "Neutral", "confidence": 0.5, "reasons": []},
        "sentiment_data": {
            "components": {
                "economic": {
                    "events": [
                        {
                            "title": "Core CPI m/m",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    ]
                }
            }
        }
    }
    
    res_high_impact = aggregator_node(state_high_impact)
    assert "aggregated_verdict" in res_high_impact
    assert res_high_impact["aggregated_verdict"]["market_regime"] == "HIGH_IMPACT_EVENT"

def test_aggregator_veto_logic():
    """Memastikan veto diaktifkan saat terjadi konflik arah (Bullish vs Bearish) di antara analis inti (Liquidity vs Derivatives)."""
    from workflows.nodes.agent_aggregator import aggregator_node
    
    # 1. Core conflict: Liquidity = Bullish (0.8), Derivatives = Bearish (0.75) -> Harus VETO ke Neutral
    state_conflict = {
        "symbol": "BTCUSDC",
        "technical_verdict": {"bias": "Bullish", "confidence": 0.8, "reasons": ["Uptrend strong"]},
        "liquidity_verdict": {"bias": "Bullish", "confidence": 0.8, "reasons": ["Sweep PDL"]},
        "derivatives_verdict": {"bias": "Bearish", "confidence": 0.75, "reasons": ["Funding negative"]},
        "sentiment_verdict": {"bias": "Neutral", "confidence": 0.5, "reasons": []},
        "sentiment_data": {
            "components": {
                "economic": {"events": []}
            }
        }
    }
    
    res = aggregator_node(state_conflict)
    assert "aggregated_verdict" in res
    verdict = res["aggregated_verdict"]
    assert verdict["consensus_bias"] == "Neutral"
    assert verdict["consensus_confidence"] == 0.0
    assert any("[Veto] Core Conflict" in r for r in verdict["aggregated_reasons"])

    # 2. Consensus Anchoring: Liquidity = Bullish (0.8), Derivatives = Bullish (0.8) -> Anchor to Bullish
    # Technical = Bearish (0.7) -> Disagrees, reduces confidence but final bias remains Bullish
    state_anchoring = {
        "symbol": "BTCUSDC",
        "technical_verdict": {"bias": "Bearish", "confidence": 0.7, "reasons": ["Lagging structure"]},
        "liquidity_verdict": {"bias": "Bullish", "confidence": 0.8, "reasons": ["Sweep PDL"]},
        "derivatives_verdict": {"bias": "Bullish", "confidence": 0.8, "reasons": ["Whale buys"]},
        "sentiment_verdict": {"bias": "Neutral", "confidence": 0.5, "reasons": []},
        "sentiment_data": {
            "components": {
                "economic": {"events": []}
            }
        }
    }
    
    res_anchor = aggregator_node(state_anchoring)
    verdict_anchor = res_anchor["aggregated_verdict"]
    assert "Bullish" in verdict_anchor["consensus_bias"]
    assert any("Tech disagrees with Core Consensus" in r for r in verdict_anchor["aggregated_reasons"])

def test_notify_pre_decision_verdict():
    """Memastikan notify_pre_decision_verdict memformat pesan dengan benar dan memanggil requests.post."""
    from bot.telegram import TelegramNotifier
    from unittest.mock import patch, MagicMock

    notifier = TelegramNotifier()
    notifier.enabled = True
    notifier.token = "fake_token"
    notifier.chat_id = "fake_chat_id"

    mock_context = {
        "realtime_price": 95000.0,
        "current_market_session": "New York",
        "consensus_verdict": {
            "consensus_bias": "Strong Bullish",
            "consensus_confidence": 0.85,
            "market_regime": "NORMAL",
            "aggregated_reasons": ["Reason 1", "Reason 2"]
        },
        "technical_analyst_verdict": {"bias": "Bullish", "confidence": 0.8},
        "liquidity_analyst_verdict": {"bias": "Bullish", "confidence": 0.9},
        "derivatives_analyst_verdict": {"bias": "Neutral", "confidence": 0.5},
        "sentiment_analyst_verdict": {"bias": "Bullish", "confidence": 0.7},
        "risk_manager_parameters": {
            "cleared": True,
            "entry_midpoint": 95000.0,
            "stop_loss": 94000.0,
            "take_profit": 98000.0,
            "risk_reward": "1:3.0"
        }
    }

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        success = notifier.notify_pre_decision_verdict("BTCUSDC", mock_context)
        assert success is True
        
        # Verify requests.post was called
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        payload = kwargs.get("json", {})
        
        # Verify essential formatted elements exist in the message text
        text = payload.get("text", "")
        assert "PRE-DECISION STATE — BTCUSDC" in text
        assert "New York" in text
        assert "Strong Bullish" in text
        assert "Technical: Bullish (0.8)" in text
        assert "Liquidity: Bullish (0.9)" in text
        assert "Risk Parameters:" in text
        assert "Cleared: ✅ YES" in text
        assert "$95,000.00" in text
        assert "$94,000.00" in text
        assert "$98,000.00" in text
        assert "Reason 1" in text

