import logging
from workflows.state import DyadixState

logger = logging.getLogger(__name__)

def _bias_to_numeric(bias: str) -> float:
    """Helper untuk memetakan bias ke nilai numerik (0-8)."""
    mapping = {
        "strong bullish": 8.0,
        "bullish": 7.0,
        "moderate bullish": 6.0,
        "neutral": 4.0,
        "moderate bearish": 2.0,
        "bearish": 1.0,
        "strong bearish": 0.0
    }
    return mapping.get(bias.lower(), 4.0)

def _numeric_to_bias(score: float) -> str:
    """Helper untuk memetakan nilai numerik (0-8) kembali ke bias label."""
    if score >= 7.0:
        return "Strong Bullish"
    elif score >= 5.5:
        return "Moderate Bullish"
    elif score >= 4.5:
        return "Neutral"
    elif score >= 3.0:
        return "Moderate Bearish"
    else:
        return "Strong Bearish"

def aggregator_node(state: DyadixState) -> dict:
    """
    Menggabungkan seluruh verdict dari 4 analyst agent (Technical, Liquidity, Derivatives, Sentiment)
    menggunakan model weighted consensus.
    """
    symbol = state.get("symbol", "UNKNOWN")
    logger.info(f"[Agent Aggregator] Aggregating verdicts for {symbol}...")
    
    tech = state.get("technical_verdict", {})
    liq = state.get("liquidity_verdict", {})
    deriv = state.get("derivatives_verdict", {})
    sent = state.get("sentiment_verdict", {})
    
    # Ambil bias masing-masing agent
    tech_bias = tech.get("bias", "Neutral")
    liq_bias = liq.get("bias", "Neutral")
    deriv_bias = deriv.get("bias", "Neutral")
    sent_bias = sent.get("bias", "Neutral")
    
    # Ambil confidence masing-masing agent
    tech_conf = tech.get("confidence", 0.5)
    liq_conf = liq.get("confidence", 0.5)
    deriv_conf = deriv.get("confidence", 0.5)
    sent_conf = sent.get("confidence", 0.5)
    
    # Konversi bias ke numerik
    tech_num = _bias_to_numeric(tech_bias)
    liq_num = _bias_to_numeric(liq_bias)
    deriv_num = _bias_to_numeric(deriv_bias)
    sent_num = _bias_to_numeric(sent_bias)
    
    from config.settings import get_config
    config = get_config()
    features = config.get("features", {})
    
    sentiment_enabled = (
        features.get("enable_reddit_scraper", False) or
        features.get("enable_news", False) or
        features.get("enable_fear_greed", False) or
        features.get("enable_twitter_influencer", False)
    )
    
    if sentiment_enabled:
        w_tech, w_sent, w_deriv, w_liq = 0.40, 0.30, 0.20, 0.10
    else:
        w_tech, w_sent, w_deriv, w_liq = 0.60, 0.00, 0.30, 0.10
        logger.info(f"[Agent Aggregator] Sentiment is disabled in settings. Redistributing weights (Tech: {w_tech * 100}%, Derivatives: {w_deriv * 100}%, Liquidity: {w_liq * 100}%)")
        
    # Pembobotan consensus
    weighted_score = (
        tech_num * w_tech +
        sent_num * w_sent +
        deriv_num * w_deriv +
        liq_num * w_liq
    )
    
    final_bias = _numeric_to_bias(weighted_score)
    
    # Hitung average confidence weighted by agent importance
    weighted_conf = (
        tech_conf * w_tech +
        sent_conf * w_sent +
        deriv_conf * w_deriv +
        liq_conf * w_liq
    )
    
    # Gabungkan alasan dari seluruh agent
    all_reasons = []
    for agent_name, agent_verdict in [
        ("Technical", tech),
        ("Sentiment", sent),
        ("Derivatives", deriv),
        ("Liquidity", liq)
    ]:
        reasons = agent_verdict.get("reasons", [])
        if reasons:
            # Ambil maksimal 2 alasan terpenting dari tiap agent untuk menghindari clutter
            all_reasons.extend([f"[{agent_name}] {r}" for r in reasons[:2]])
            
    verdict = {
        "consensus_bias": final_bias,
        "consensus_score": round(weighted_score, 2),
        "consensus_confidence": round(weighted_conf, 2),
        "aggregated_reasons": all_reasons,
        "individual_biases": {
            "technical": tech_bias,
            "liquidity": liq_bias,
            "derivatives": deriv_bias,
            "sentiment": sent_bias
        }
    }
    
    logger.info(f"[Agent Aggregator] Aggregated Verdict: bias={final_bias}, confidence={weighted_conf:.2f}")
    return {"aggregated_verdict": verdict}
