import logging
from workflows.state import DyadixState

logger = logging.getLogger(__name__)

def sentiment_analyst_node(state: DyadixState) -> dict:
    """
    Analyst Agent untuk mengevaluasi data sentimen pasar secara global (news, social, F&G).
    Mengekstrak overall_sentiment, sentiment_score, fear_greed index, dsb.
    """
    symbol = state.get("symbol", "UNKNOWN")
    print(f"[MONITORING] [Sentiment Analyst] Analyzing {symbol}...")
    logger.info(f"[Sentiment Analyst] Analyzing {symbol}...")
    
    from config.settings import get_config
    config = get_config()
    features = config.get("features", {})
    
    sentiment_enabled = (
        features.get("enable_reddit_scraper", False) or
        features.get("enable_news", False) or
        features.get("enable_fear_greed", False) or
        features.get("enable_twitter_influencer", False)
    )
    
    if not sentiment_enabled:
        print(f"[MONITORING] [Sentiment Analyst] Disabled in settings. Skipping analysis for {symbol}.")
        logger.info(f"[Sentiment Analyst] Sentiment analysis is disabled in settings. Skipping analysis for {symbol}.")
        verdict = {
            "bias": "Neutral",
            "confidence": 0.5,
            "reasons": ["Sentiment analysis features are disabled in config settings."],
            "sentiment_score": 50,
            "fear_greed_value": None,
            "sentiment_raw": "Disabled"
        }
        return {"sentiment_verdict": verdict}
        
    sentiment_data = state.get("sentiment_data", {})
    
    sentiment_raw = sentiment_data.get("overall_sentiment", "Neutral")
    sentiment_score = sentiment_data.get("sentiment_score", 50)
    
    sentiment_lower = sentiment_raw.lower()
    if "bullish" in sentiment_lower:
        bias = "Bullish"
    elif "bearish" in sentiment_lower:
        bias = "Bearish"
    else:
        bias = "Neutral"
        
    reasons = [f"Overall macro sentiment: {sentiment_raw} (score {sentiment_score})"]
    
    # Fear and Greed Index
    fg_data = sentiment_data.get("components", {}).get("fear_greed", {})
    fg_val = fg_data.get("value")
    fg_class = fg_data.get("sentiment_class")
    if fg_val is not None:
        reasons.append(f"Fear & Greed Index: {fg_val} ({fg_class})")
        
    # Economic calendar events
    eco_calendar = sentiment_data.get("components", {}).get("economic_calendar", [])
    if eco_calendar:
        high_impact = [e for e in eco_calendar if e.get("impact", "").lower() == "high"]
        if high_impact:
            reasons.append(f"Detected {len(high_impact)} high-impact macroeconomic events")
            
    # Hitung confidence berdasarkan simpangan dari skor 50
    confidence = min(0.90, max(0.5, 0.5 + abs(sentiment_score - 50) / 100))
    
    verdict = {
        "bias": bias,
        "confidence": round(confidence, 2),
        "reasons": reasons,
        "sentiment_score": sentiment_score,
        "fear_greed_value": fg_val,
        "sentiment_raw": sentiment_raw
    }
    
    print(f"[MONITORING] [Sentiment Analyst] Verdict for {symbol}: bias={bias}, confidence={confidence}")
    logger.info(f"[Sentiment Analyst] Verdict for {symbol}: bias={bias}, confidence={confidence}")
    return {"sentiment_verdict": verdict}
