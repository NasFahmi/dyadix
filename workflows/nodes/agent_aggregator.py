import logging
from enum import Enum
from datetime import datetime, timezone
from workflows.state import DyadixState

logger = logging.getLogger(__name__)

class MarketRegime(Enum):
    NORMAL = "NORMAL"
    HIGH_IMPACT_EVENT = "HIGH_IMPACT_EVENT"

def parse_utc_timestamp(ts_str: str) -> datetime | None:
    if not ts_str:
        return None
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except Exception as e:
        logger.warning(f"Failed to parse timestamp '{ts_str}': {e}")
        return None

def get_market_regime(state: DyadixState) -> MarketRegime:
    events = state.get("sentiment_data", {}).get("components", {}).get("economic", {}).get("events", [])
    if not events:
        return MarketRegime.NORMAL
        
    now = datetime.now(timezone.utc)
    target_events = ["cpi", "nfp", "fomc", "non-farm", "fed rate", "interest rate"]
    
    for e in events:
        title = e.get("title", "").lower()
        if any(kw in title for kw in target_events):
            ts_str = e.get("timestamp")
            event_dt = parse_utc_timestamp(ts_str)
            if not event_dt:
                date_str = e.get("date")
                time_str = e.get("time", "00:00:00")
                if date_str:
                    try:
                        event_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    except Exception:
                        continue
            if event_dt:
                diff_seconds = abs((event_dt - now).total_seconds())
                if diff_seconds < 24 * 3600:
                    logger.info(f"Upcoming High Impact Event detected: {e.get('title')} at {event_dt.isoformat()}. Switching to HIGH_IMPACT_EVENT regime.")
                    return MarketRegime.HIGH_IMPACT_EVENT
                    
    return MarketRegime.NORMAL

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
    print(f"[MONITORING] [Agent Aggregator] Aggregating verdicts for {symbol}...")
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
    
    regime = get_market_regime(state)
    
    if sentiment_enabled:
        if regime == MarketRegime.HIGH_IMPACT_EVENT:
            w_tech, w_sent, w_deriv, w_liq = 0.20, 0.30, 0.25, 0.25
        else:
            w_tech, w_sent, w_deriv, w_liq = 0.30, 0.10, 0.30, 0.30
    else:
        if regime == MarketRegime.HIGH_IMPACT_EVENT:
            w_tech, w_sent, w_deriv, w_liq = 0.28, 0.00, 0.36, 0.36
        else:
            w_tech, w_sent, w_deriv, w_liq = 0.33, 0.00, 0.33, 0.34
            
        print(f"[MONITORING] [Agent Aggregator] Sentiment is disabled in settings. Redistributing weights (Tech: {w_tech * 100}%, Derivatives: {w_deriv * 100}%, Liquidity: {w_liq * 100}%)")
        logger.info(f"[Agent Aggregator] Sentiment is disabled in settings. Redistributing weights (Tech: {w_tech * 100}%, Derivatives: {w_deriv * 100}%, Liquidity: {w_liq * 100}%)")
        
    # ── Core-Secondary Direction Helpers ──
    def get_simple_direction(bias_str: str) -> str:
        b = bias_str.lower()
        if "bullish" in b:
            return "bullish"
        elif "bearish" in b:
            return "bearish"
        return "neutral"
        
    tech_dir = get_simple_direction(tech_bias)
    liq_dir = get_simple_direction(liq_bias)
    deriv_dir = get_simple_direction(deriv_bias)

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
            all_reasons.extend([f"[{agent_name}] {r}" for r in reasons[:2]])
            
    # ── Rule 2: Core Conflict Detection (Liquidity vs Derivatives) ──
    is_core_conflict = False
    if liq_dir != "neutral" and deriv_dir != "neutral" and liq_dir != deriv_dir:
        if liq_conf > 0.70 and deriv_conf > 0.70:
            is_core_conflict = True
            conflict_msg = f"VETO TRIGGERED: Core Conflict between Liquidity ({liq_bias}) and Derivatives ({deriv_bias})."
            print(f"[MONITORING] [Agent Aggregator] {conflict_msg}")
            logger.info(f"[Agent Aggregator] {conflict_msg}")
            
            final_bias = "Neutral"
            weighted_conf = 0.0
            all_reasons.append(f"[Veto] Core Conflict: Liquidity ({liq_bias}) vs Derivatives ({deriv_bias})")
            
    # ── Rule 1 & 3: Consensus Anchoring (If Core Sepakat) ──
    if not is_core_conflict:
        if liq_dir != "neutral" and deriv_dir != "neutral" and liq_dir == deriv_dir:
            core_bias = liq_dir
            
            if core_bias == "bullish":
                if "bullish" not in final_bias.lower():
                    final_bias = "Bullish"
            elif core_bias == "bearish":
                if "bearish" not in final_bias.lower():
                    final_bias = "Bearish"
                    
            # Technical hanya memodifikasi confidence jika bertentangan
            if tech_dir != "neutral" and tech_dir != core_bias:
                old_conf = weighted_conf
                weighted_conf = max(0.3, weighted_conf - 0.15)
                all_reasons.append(f"[Veto] Tech disagrees with Core Consensus; confidence reduced from {old_conf:.2f} to {weighted_conf:.2f}")
                print(f"[MONITORING] [Agent Aggregator] Technical bias ({tech_bias}) disagrees with core consensus ({core_bias}). Reducing confidence.")
                logger.info(f"[Agent Aggregator] Technical bias ({tech_bias}) disagrees with core consensus ({core_bias}). Reducing confidence.")
            
    verdict = {
        "consensus_bias": final_bias,
        "consensus_score": round(weighted_score, 2),
        "consensus_confidence": round(weighted_conf, 2),
        "aggregated_reasons": all_reasons,
        "market_regime": regime.value,
        "individual_biases": {
            "technical": tech_bias,
            "liquidity": liq_bias,
            "derivatives": deriv_bias,
            "sentiment": sent_bias
        }
    }
    
    print(f"[MONITORING] [Agent Aggregator] Aggregated Verdict: bias={final_bias}, confidence={weighted_conf:.2f}")
    logger.info(f"[Agent Aggregator] Aggregated Verdict: bias={final_bias}, confidence={weighted_conf:.2f}")
    return {"aggregated_verdict": verdict}
