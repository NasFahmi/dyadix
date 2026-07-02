import logging
from workflows.state import DyadixState

logger = logging.getLogger(__name__)

def liquidity_analyst_node(state: DyadixState) -> dict:
    """
    Analyst Agent untuk mengevaluasi data likuiditas secara rule-based.
    Mengekstrak status liquidity sweeps, support/resistance pools, dan status likuiditas lainnya.
    """
    symbol = state.get("symbol", "UNKNOWN")
    logger.info(f"[Liquidity Analyst] Analyzing {symbol}...")
    
    liquidity_data = state.get("liquidity_data", {})
    
    sentiment_raw = liquidity_data.get("liquidity_sentiment", "Neutral")
    # Tentukan bias dari sentiment
    sentiment_lower = sentiment_raw.lower()
    if "pdl sweep" in sentiment_lower or "near low pool" in sentiment_lower or "bullish" in sentiment_lower:
        bias = "Bullish"
    elif "pdh sweep" in sentiment_lower or "near high pool" in sentiment_lower or "bearish" in sentiment_lower:
        bias = "Bearish"
    else:
        bias = "Neutral"
        
    reasons = [f"Liquidity sentiment: {sentiment_raw}"]
    
    # Check if there is active sweep information
    sweep_type = liquidity_data.get("sweep_type")
    if sweep_type:
        reasons.append(f"Confirmed liquidity sweep: {sweep_type}")
        
    # Pool proximity
    highs_proximity = liquidity_data.get("highs_pool_proximity")
    lows_proximity = liquidity_data.get("lows_pool_proximity")
    
    if highs_proximity:
        reasons.append(f"Proximity to high pool: {highs_proximity}")
    if lows_proximity:
        reasons.append(f"Proximity to low pool: {lows_proximity}")
        
    # Hitung confidence berdasarkan status sweeps
    confidence = 0.5
    if "sweep" in sentiment_lower:
        confidence = 0.85
        reasons.append("High confidence due to recent sweep event")
    elif "near" in sentiment_lower:
        confidence = 0.70
        reasons.append("Moderate confidence near liquidity pools")
        
    verdict = {
        "bias": bias,
        "confidence": confidence,
        "reasons": reasons,
        "sentiment_raw": sentiment_raw,
        "key_levels": liquidity_data.get("key_levels", {})
    }
    
    logger.info(f"[Liquidity Analyst] Verdict for {symbol}: bias={bias}, confidence={confidence}")
    return {"liquidity_verdict": verdict}
