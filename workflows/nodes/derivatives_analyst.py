import logging
from workflows.state import DyadixState

logger = logging.getLogger(__name__)

def derivatives_analyst_node(state: DyadixState) -> dict:
    """
    Analyst Agent untuk mengevaluasi data pasar derivatif secara rule-based.
    Mengekstrak derivatives_sentiment, trend funding rate, open interest (OI) change, dll.
    """
    symbol = state.get("symbol", "UNKNOWN")
    logger.info(f"[Derivatives Analyst] Analyzing {symbol}...")
    
    derivatives_data = state.get("derivatives_data", {})
    
    sentiment_raw = derivatives_data.get("derivatives_sentiment", "Neutral")
    sentiment_lower = sentiment_raw.lower()
    
    if "strong bullish" in sentiment_lower or "moderate bullish" in sentiment_lower or "bullish" in sentiment_lower:
        bias = "Bullish"
    elif "strong bearish" in sentiment_lower or "moderate bearish" in sentiment_lower or "bearish" in sentiment_lower:
        bias = "Bearish"
    else:
        bias = "Neutral"
        
    reasons = [f"Derivatives sentiment: {sentiment_raw}"]
    
    # Ambil funding rate
    funding_info = derivatives_data.get("funding_rate", {})
    latest_funding = funding_info.get("latest")
    if latest_funding is not None:
        reasons.append(f"Latest Funding Rate: {latest_funding:.5%}")
        
    # Ambil Open Interest change
    oi_info = derivatives_data.get("open_interest", {})
    latest_oi_change = oi_info.get("latest_oi_change")
    if latest_oi_change is not None:
        reasons.append(f"Latest OI Change: {latest_oi_change:.2f}%")
        
    # Hitung confidence berdasarkan kekuatan sentiment
    confidence = 0.5
    if "strong" in sentiment_lower:
        confidence = 0.80
        reasons.append("High confidence due to strong positioning alignment")
    elif "moderate" in sentiment_lower or "bullish" in sentiment_lower or "bearish" in sentiment_lower:
        confidence = 0.65
        reasons.append("Moderate confidence in positioning trend")
        
    verdict = {
        "bias": bias,
        "confidence": confidence,
        "reasons": reasons,
        "funding_rate": latest_funding,
        "oi_change": latest_oi_change,
        "sentiment_raw": sentiment_raw
    }
    
    logger.info(f"[Derivatives Analyst] Verdict for {symbol}: bias={bias}, confidence={confidence}")
    return {"derivatives_verdict": verdict}
