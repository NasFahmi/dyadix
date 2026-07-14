import logging
from workflows.state import DyadixState

logger = logging.getLogger(__name__)

def technical_analyst_node(state: DyadixState) -> dict:
    """
    Analyst Agent untuk mengevaluasi data teknikal secara rule-based.
    Mengekstrak bias, confidence, dan alasan pendukung dari market_data.
    """
    symbol = state.get("symbol", "UNKNOWN")
    # ── Pre-entry Logging ──────────────────────────────────────────
    market_data_pre = state.get("market_data", {})
    realtime_price = state.get("realtime_price")
    print(f"[PRE-NODE]  [Technical Analyst] {symbol} | "
          f"realtime_price={realtime_price} | "
          f"overall_bias='{market_data_pre.get('overall_technical_bias','?')}' | "
          f"daily_bias='{market_data_pre.get('daily_bias', {}).get('bias','?')}'")
    logger.info(f"[Technical Analyst] [PRE-NODE] {symbol} | "
                f"realtime_price={realtime_price} | "
                f"overall_bias={market_data_pre.get('overall_technical_bias')} | "
                f"daily_bias={market_data_pre.get('daily_bias', {}).get('bias')}")
    print(f"\n[MONITORING] [Technical Analyst] Analyzing {symbol}...")
    logger.info(f"[Technical Analyst] Analyzing {symbol}...")
    
    market_data = state.get("market_data", {})
    
    # Ambil data teknikal yang sudah dihitung
    overall_bias = market_data.get("overall_technical_bias", "Neutral")
    daily_bias = market_data.get("daily_bias", {}).get("bias", "Neutral")
    
    # Cari trend
    trend_info = {}
    for key in market_data:
        if key.startswith("trend_"):
            trend_info = market_data[key]
            break
    trend_regime = trend_info.get("trend_regime", "Neutral")
    
    # Cari momentum
    momentum_info = {}
    for key in market_data:
        if key.startswith("momentum_"):
            momentum_info = market_data[key]
            break
    rsi = momentum_info.get("rsi", 50)
    
    # Cari price action
    pa_info = {}
    for key in market_data:
        if key.startswith("price_action_"):
            pa_info = market_data[key]
            break
    pa_bias = pa_info.get("pa_bias", "Neutral")
    
    # Buat summary technical indicators
    reasons = []
    
    # Cari order block
    ob_info = {}
    for key in market_data:
        if key.startswith("order_block_"):
            ob_info = market_data[key]
            break
            
    # Evaluation of Order Blocks
    threshold_pct = 0.002
    current_price = state.get("realtime_price") or market_data.get("current_price")
    ob_confluence_score = 0.0
    
    if current_price and ob_info:
        bull_ob = ob_info.get("nearest_bullish_ob")
        bear_ob = ob_info.get("nearest_bearish_ob")
        
        if bull_ob:
            top = bull_ob["top"]
            bottom = bull_ob["bottom"]
            if (current_price >= bottom) and (current_price <= top * (1 + threshold_pct)):
                ob_confluence_score += 0.20
                reasons.append(f"Price in Bullish Order Block ({bottom}-{top})")
                if overall_bias == "Neutral":
                    overall_bias = "Bullish"
                elif "Bearish" in overall_bias:
                    overall_bias = "Neutral"
                    
        if bear_ob:
            top = bear_ob["top"]
            bottom = bear_ob["bottom"]
            if (current_price <= top) and (current_price >= bottom * (1 - threshold_pct)):
                ob_confluence_score += 0.20
                reasons.append(f"Price in Bearish Order Block ({bottom}-{top})")
                if overall_bias == "Neutral":
                    overall_bias = "Bearish"
                elif "Bullish" in overall_bias:
                    overall_bias = "Neutral"
    if overall_bias != "Neutral":
        reasons.append(f"Overall technical bias is {overall_bias}")
    if daily_bias != "Neutral":
        reasons.append(f"Daily bias: {daily_bias}")
    if trend_regime:
        reasons.append(f"Trend regime: {trend_regime}")
    if rsi:
        reasons.append(f"RSI Momentum: {rsi:.0f}")
    if pa_bias != "Neutral":
        reasons.append(f"Price Action bias: {pa_bias}")
        
    # Periksa candlestick pattern
    if pa_info.get("is_bullish_engulfing"):
        reasons.append("Bullish Engulfing pattern detected")
    elif pa_info.get("is_bearish_engulfing"):
        reasons.append("Bearish Engulfing pattern detected")
        
    if pa_info.get("is_hammer"):
        reasons.append("Hammer candlestick pattern detected")
    elif pa_info.get("is_shooting_star"):
        reasons.append("Shooting Star candlestick pattern detected")
        
    # Hitung confidence berdasarkan confluence
    # Kita bisa set confidence dasar sesuai keselarasan bias harian, trend, dan momentum
    confluence_score = 0
    confluence_score += ob_confluence_score
    
    if daily_bias == "Bullish" and "uptrend" in trend_regime.lower():
        confluence_score += 0.3
    elif daily_bias == "Bearish" and "downtrend" in trend_regime.lower():
        confluence_score += 0.3
        
    if "bullish" in pa_bias.lower():
        confluence_score += 0.2
    elif "bearish" in pa_bias.lower():
        confluence_score += 0.2
        
    if "strong" in trend_regime.lower():
        confluence_score += 0.2
        
    # Score minimal confidence = 0.5, maks = 0.95
    confidence = min(0.95, max(0.5, 0.5 + confluence_score))
    
    verdict = {
        "bias": overall_bias,
        "confidence": round(confidence, 2),
        "reasons": reasons,
        "rsi": rsi,
        "trend": trend_regime,
        "daily_bias": daily_bias
    }
    
    print(f"[MONITORING] [Technical Analyst] Verdict for {symbol}: bias={overall_bias}, confidence={confidence}")
    logger.info(f"[Technical Analyst] Verdict for {symbol}: bias={overall_bias}, confidence={confidence}")
    # ── Post-exit Logging ────────────────────────────────────────────
    print(f"[POST-NODE] [Technical Analyst] {symbol} | bias={overall_bias} | conf={round(confidence,2)} | "
          f"trend='{trend_regime}' | rsi={rsi:.0f} | daily_bias='{daily_bias}' | ob_score={ob_confluence_score:.2f}")
    logger.info(f"[Technical Analyst] [POST-NODE] {symbol} | bias={overall_bias} conf={round(confidence,2)} "
                f"trend={trend_regime} rsi={rsi:.0f} daily_bias={daily_bias}")
    return {"technical_verdict": verdict}
