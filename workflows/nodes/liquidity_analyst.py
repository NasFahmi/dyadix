import logging
from workflows.state import DyadixState

logger = logging.getLogger(__name__)

def liquidity_analyst_node(state: DyadixState) -> dict:
    """
    Analyst Agent untuk mengevaluasi data likuiditas secara rule-based.
    Mengekstrak status liquidity sweeps, support/resistance pools, dan status likuiditas lainnya.
    """
    symbol = state.get("symbol", "UNKNOWN")
    # ── Pre-entry Logging ──────────────────────────────────────────
    liq_pre = state.get("liquidity_data", {})
    micro_pre = state.get("microstructure_data", {})
    _micro_info = (
        f"{len(micro_pre)} keys: {list(micro_pre.keys())[:4]}"
        if micro_pre
        else "empty (websocket-only, not active in --once/test mode)"
    )
    _pools = liq_pre.get("liquidity_pools", {})
    _sweeps = liq_pre.get("recent_sweeps", [])
    print(f"[PRE-NODE]  [Liquidity Analyst] {symbol} | "
          f"sentiment='{liq_pre.get('liquidity_sentiment','?')}' | "
          f"sweep_type='{liq_pre.get('sweep_type','None')}' | "
          f"high_pools={len(_pools.get('highs', []))} | low_pools={len(_pools.get('lows', []))} | "
          f"recent_sweeps={len(_sweeps)} | "
          f"microstructure={_micro_info}")
    logger.info(f"[Liquidity Analyst] [PRE-NODE] {symbol} | "
                f"sentiment={liq_pre.get('liquidity_sentiment')} | "
                f"sweep_type={liq_pre.get('sweep_type')} | "
                f"pools={len(_pools.get('highs',[]))}H/{len(_pools.get('lows',[]))}L | "
                f"sweeps={len(_sweeps)} | "
                f"microstructure={'active' if micro_pre else 'empty (websocket-only)'}")
    print(f"[MONITORING] [Liquidity Analyst] Analyzing {symbol}...")
    logger.info(f"[Liquidity Analyst] Analyzing {symbol}...")
    
    liquidity_data = state.get("liquidity_data", {})
    microstructure_data = state.get("microstructure_data", {})
    
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
        
    # ── Microstructure Evaluation ──
    micro_bull_score = 0.0
    micro_bear_score = 0.0
    
    if microstructure_data:
        # 1. CVD
        cvd_5m = microstructure_data.get("cvd_5m_usd", 0.0)
        cvd_15m = microstructure_data.get("cvd_15m_usd", 0.0)
        if cvd_5m > 0 and cvd_15m > 0:
            micro_bull_score += 0.05
            reasons.append(f"CVD bullish alignment (5m: ${cvd_5m:,.0f}, 15m: ${cvd_15m:,.0f})")
        elif cvd_5m < 0 and cvd_15m < 0:
            micro_bear_score += 0.05
            reasons.append(f"CVD bearish alignment (5m: ${cvd_5m:,.0f}, 15m: ${cvd_15m:,.0f})")
            
        # 2. Orderbook Imbalance
        imbalance = microstructure_data.get("orderbook_imbalance_top5", 0.0)
        if imbalance > 0.15:
            micro_bull_score += 0.04
            reasons.append(f"Orderbook bid imbalance top-5: {imbalance:.2%}")
        elif imbalance < -0.15:
            micro_bear_score += 0.04
            reasons.append(f"Orderbook ask imbalance top-5: {imbalance:.2%}")
            
        # 3. Whale Execution
        whale_buys = microstructure_data.get("whale_buy_count_15m", 0)
        whale_sells = microstructure_data.get("whale_sell_count_15m", 0)
        if whale_buys > whale_sells:
            micro_bull_score += 0.03
            reasons.append(f"Whale buys active (Buys: {whale_buys} vs Sells: {whale_sells})")
        elif whale_sells > whale_buys:
            micro_bear_score += 0.03
            reasons.append(f"Whale sells active (Sells: {whale_sells} vs Buys: {whale_buys})")
            
        # 4. Liquidations
        long_liq = microstructure_data.get("long_liquidations_usd_15m", 0.0)
        short_liq = microstructure_data.get("short_liquidations_usd_15m", 0.0)
        if short_liq > 0 and short_liq > long_liq:
            micro_bull_score += 0.03
            reasons.append(f"Short liquidation squeeze (${short_liq:,.0f} USD)")
        elif long_liq > 0 and long_liq > short_liq:
            micro_bear_score += 0.03
            reasons.append(f"Long liquidation squeeze (${long_liq:,.0f} USD)")
            
    # Integrasi Microstructure ke Bias & Confidence
    if micro_bull_score > 0 or micro_bear_score > 0:
        if bias == "Bullish":
            confidence += (micro_bull_score - micro_bear_score)
        elif bias == "Bearish":
            confidence += (micro_bear_score - micro_bull_score)
        elif bias == "Neutral":
            if micro_bull_score >= 0.08:
                bias = "Bullish"
                confidence = 0.65
            elif micro_bear_score >= 0.08:
                bias = "Bearish"
                confidence = 0.65
                
        confidence = min(0.95, max(0.5, confidence))
        
    verdict = {
        "bias": bias,
        "confidence": round(confidence, 2),
        "reasons": reasons,
        "sentiment_raw": sentiment_raw,
        "key_levels": liquidity_data.get("key_levels", {})
    }
    
    print(f"[MONITORING] [Liquidity Analyst] Verdict for {symbol}: bias={bias}, confidence={confidence}")
    logger.info(f"[Liquidity Analyst] Verdict for {symbol}: bias={bias}, confidence={confidence}")
    # ── Post-exit Logging ────────────────────────────────────────────
    print(f"[POST-NODE] [Liquidity Analyst] {symbol} | bias={bias} | conf={round(confidence,2)} | "
          f"sentiment='{sentiment_raw}' | micro_bull={micro_bull_score:.2f} micro_bear={micro_bear_score:.2f} | "
          f"reasons_count={len(reasons)}")
    logger.info(f"[Liquidity Analyst] [POST-NODE] {symbol} | bias={bias} conf={round(confidence,2)} "
                f"micro_bull={micro_bull_score:.2f} micro_bear={micro_bear_score:.2f}")
    return {"liquidity_verdict": verdict}
