import logging
from workflows.state import DyadixState
from config.settings import get_config

logger = logging.getLogger(__name__)

def risk_manager_node(state: DyadixState) -> dict:
    """
    Risk Manager Agent untuk mengevaluasi parameter risiko secara rule-based.
    Menghitung entry midpoint, ATR-based Stop Loss, Take Profit (min RR 1:3.0),
    dan position sizing.
    """
    symbol = state.get("symbol", "UNKNOWN")
    logger.info(f"[Risk Manager] Evaluating risk for {symbol}...")
    
    config = get_config()
    rm_config = config.get("risk_management", {})
    
    consensus = state.get("aggregated_verdict", {})
    bias = consensus.get("consensus_bias", "Neutral")
    
    market_data = state.get("market_data", {})
    current_price = state.get("realtime_price", 0.0)
    if current_price <= 0:
        current_price = market_data.get("current_price", 0.0)
        
    if current_price <= 0:
        # Fallback jika harga tidak terdeteksi
        logger.error(f"[Risk Manager] Error: price is 0 for {symbol}")
        return {
            "risk_verdict": {
                "cleared": False,
                "reason": "Current price not found",
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "position_size_pct": 0.0
            }
        }
        
    # Ambil ATR
    atr = 0.0
    for key, val in market_data.items():
        if key.startswith("volatility_") and isinstance(val, dict):
            atr = val.get("atr", 0.0)
            break
            
    # Fallback ATR jika 0 (gunakan 0.5% dari harga sekarang)
    if atr <= 0.0:
        atr = current_price * 0.005
        logger.warning(f"[Risk Manager] Volatility ATR not found, using fallback 0.5% price ATR: {atr}")
        
    bias_lower = bias.lower()
    cleared = False
    reasons = []
    
    sl_price = 0.0
    tp_price = 0.0
    rr_ratio = 3.0 # target minimum 1:3.0 Risk-Reward
    
    if "bullish" in bias_lower:
        # Long setup
        # Stop Loss = entry - 2 * ATR
        sl_price = current_price - (2.0 * atr)
        # Take Profit = entry + 3.0 * (entry - SL)
        risk_dist = current_price - sl_price
        tp_price = current_price + (rr_ratio * risk_dist)
        
        # Validasi sederhana
        if sl_price > 0 and tp_price > current_price:
            cleared = True
            reasons.append("Long setup parameters generated successfully.")
            
    elif "bearish" in bias_lower:
        # Short setup
        # Stop Loss = entry + 2 * ATR
        sl_price = current_price + (2.0 * atr)
        # Take Profit = entry - 3.0 * (SL - entry)
        risk_dist = sl_price - current_price
        tp_price = current_price - (rr_ratio * risk_dist)
        
        # Validasi sederhana
        if sl_price > current_price and tp_price > 0:
            cleared = True
            reasons.append("Short setup parameters generated successfully.")
    else:
        # Neutral setup
        reasons.append("Consensus bias is Neutral. Risk Manager holds trade clearance.")
        
    # Hitung position sizing pct berdasarkan risk settings
    risk_pct = rm_config.get("risk_per_trade_pct", 1.0)
    leverage = rm_config.get("leverage", 10)
    
    risk_verdict = {
        "cleared": cleared,
        "reasons": reasons,
        "entry_midpoint": round(current_price, 5),
        "stop_loss": round(sl_price, 5),
        "take_profit": round(tp_price, 5),
        "risk_reward": f"1:{rr_ratio:.1f}",
        "atr_value": round(atr, 5),
        "risk_per_trade_pct": risk_pct,
        "leverage": leverage,
        "max_running_trades": rm_config.get("max_running_trades", 1)
    }
    
    logger.info(f"[Risk Manager] Verdict for {symbol}: cleared={cleared}, entry={current_price}, SL={sl_price}, TP={tp_price}")
    return {"risk_verdict": risk_verdict}
