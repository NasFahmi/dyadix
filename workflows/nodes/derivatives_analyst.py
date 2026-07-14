import logging
from workflows.state import DyadixState

logger = logging.getLogger(__name__)

def derivatives_analyst_node(state: DyadixState) -> dict:
    """
    Analyst Agent untuk mengevaluasi data pasar derivatif secara rule-based.
    Mengekstrak derivatives_sentiment, trend funding rate, open interest (OI) change, dll.
    """
    symbol = state.get("symbol", "UNKNOWN")
    # ── Pre-entry Logging ──────────────────────────────────────────
    derivatives_data_pre = state.get("derivatives_data", {})
    _oi_pre = derivatives_data_pre.get("open_interest", {})
    _fr_pre = derivatives_data_pre.get("funding_rate", {})
    print(f"[PRE-NODE]  [Derivatives Analyst] {symbol} | "
          f"sentiment='{derivatives_data_pre.get('derivatives_sentiment', '?')}' | "
          f"funding_latest={_fr_pre.get('latest', '?')} | funding_trend={_fr_pre.get('trend', '?')} | "
          f"oi_regime='{_oi_pre.get('regime', '?')}' | "
          f"oi_chg_1h={_oi_pre.get('change_1h_pct', '?')}% | oi_chg_4h={_oi_pre.get('change_4h_pct', '?')}%")
    logger.info(f"[Derivatives Analyst] [PRE-NODE] {symbol} | "
                f"sentiment={derivatives_data_pre.get('derivatives_sentiment')} | "
                f"funding={_fr_pre.get('latest')} trend={_fr_pre.get('trend')} | "
                f"oi_regime={_oi_pre.get('regime')} chg_1h={_oi_pre.get('change_1h_pct')}% chg_4h={_oi_pre.get('change_4h_pct')}%")
    print(f"[MONITORING] [Derivatives Analyst] Analyzing {symbol}...")
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
        
    # Ambil Open Interest change - DerivativesEngine mengembalikan 'change_1h_pct' dan 'change_4h_pct'
    oi_info = derivatives_data.get("open_interest", {})
    latest_oi_change = oi_info.get("change_1h_pct")  # key yang benar dari DerivativesEngine
    oi_change_4h = oi_info.get("change_4h_pct")
    oi_regime = oi_info.get("regime", "")
    if latest_oi_change is not None:
        reasons.append(f"OI Change 1h: {latest_oi_change:.2f}%")
    if oi_change_4h is not None:
        reasons.append(f"OI Change 4h: {oi_change_4h:.2f}%")
    if oi_regime:
        reasons.append(f"OI Regime: {oi_regime}")
        
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
        "oi_change_1h": latest_oi_change,
        "oi_change_4h": oi_change_4h,
        "oi_regime": oi_regime,
        "sentiment_raw": sentiment_raw
    }
    
    print(f"[MONITORING] [Derivatives Analyst] Verdict for {symbol}: bias={bias}, confidence={confidence}")
    logger.info(f"[Derivatives Analyst] Verdict for {symbol}: bias={bias}, confidence={confidence}")
    # ── Post-exit Logging ────────────────────────────────────────────
    print(f"[POST-NODE] [Derivatives Analyst] {symbol} | bias={bias} | conf={confidence} | "
          f"funding={verdict.get('funding_rate')} | "
          f"oi_chg_1h={verdict.get('oi_change_1h')}% | oi_chg_4h={verdict.get('oi_change_4h')}% | "
          f"oi_regime='{verdict.get('oi_regime')}' | sentiment_raw='{verdict.get('sentiment_raw')}' | reasons={len(reasons)}")
    logger.info(f"[Derivatives Analyst] [POST-NODE] {symbol} | bias={bias} conf={confidence} "
                f"funding={verdict.get('funding_rate')} oi_chg_1h={verdict.get('oi_change_1h')}% "
                f"oi_regime={verdict.get('oi_regime')}")
    return {"derivatives_verdict": verdict}
