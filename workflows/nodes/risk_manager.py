import logging
from workflows.state import DyadixState
from config.settings import get_config

logger = logging.getLogger(__name__)

# Safety valve: SL tidak boleh lebih lebar dari ini (dalam satuan ATR)
MAX_SL_ATR_SAFETY = 3.0
MIN_RR_REQUIRED = 1.5

def risk_manager_node(state: DyadixState) -> dict:
    """
    Risk Manager Agent — Validasi parameter risiko dan clearance trade.

    Path 1 (Structure-based, ideal):
        Jika Structure Mapper menghasilkan structure_map yang valid (should_wait=False),
        Risk Manager hanya memvalidasi: RR >= 1.5 dan SL distance <= 3x ATR.

    Path 2 (ATR-based fallback):
        Jika structure_map tidak tersedia atau should_wait=True,
        gunakan kalkulasi ATR-based sebagai fallback (legacy behavior).
    """
    symbol = state.get("symbol", "UNKNOWN")

    # ── Pre-entry Logging ──────────────────────────────────────────
    consensus_pre = state.get("aggregated_verdict", {})
    structure_map_pre = state.get("structure_map", {})
    price_pre = state.get("realtime_price", 0.0)
    has_structure = bool(structure_map_pre) and not structure_map_pre.get("should_wait", True)
    print(f"[PRE-NODE]  [Risk Manager] {symbol} | "
          f"consensus_bias='{consensus_pre.get('consensus_bias','?')}' | "
          f"structure_map={'VALID' if has_structure else 'FALLBACK/WAIT'} | "
          f"realtime_price={price_pre}")
    logger.info(f"[Risk Manager] [PRE-NODE] {symbol} | "
                f"consensus_bias={consensus_pre.get('consensus_bias')} | "
                f"structure_map={'valid' if has_structure else 'fallback'} | "
                f"realtime_price={price_pre}")
    print(f"[MONITORING] [Risk Manager] Evaluating risk for {symbol}...")
    logger.info(f"[Risk Manager] Evaluating risk for {symbol}...")

    config = get_config()
    rm_config = config.get("risk_management", {})
    risk_pct = rm_config.get("risk_per_trade_pct", 1.0)
    leverage = rm_config.get("leverage", 10)

    market_data = state.get("market_data", {})
    current_price = state.get("realtime_price", 0.0)
    if current_price <= 0:
        current_price = market_data.get("current_price", 0.0)

    if current_price <= 0:
        print(f"[MONITORING] [Risk Manager] Error: price is 0 for {symbol}")
        logger.error(f"[Risk Manager] Error: price is 0 for {symbol}")
        return {
            "risk_verdict": {
                "cleared": False,
                "reason": "Current price not found",
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "risk_reward": "N/A",
                "source": "error",
            }
        }

    # Ambil ATR (dibutuhkan untuk validasi safety valve di kedua path)
    atr = 0.0
    for key, val in market_data.items():
        if key.startswith("volatility_") and isinstance(val, dict):
            atr = val.get("atr", 0.0)
            if atr > 0:
                break
    if atr <= 0.0:
        atr = current_price * 0.005
        logger.warning(f"[Risk Manager] ATR not found for {symbol}, fallback 0.5% = {atr:.2f}")

    # ══════════════════════════════════════════════════════════════════
    #  PATH 1: Structure-based (dari Structure Mapper)
    # ══════════════════════════════════════════════════════════════════
    structure_map = state.get("structure_map", {})

    if structure_map and not structure_map.get("should_wait", True):
        sl_price = structure_map.get("recommended_sl", 0.0)
        tp_price = structure_map.get("recommended_tp", 0.0)
        natural_rr = structure_map.get("natural_rr", 0.0)
        sl_distance = structure_map.get("sl_distance", 0.0)
        sl_type = structure_map.get("sl_type", "unknown")
        tp_type = structure_map.get("tp_type", "unknown")

        cleared = False
        reasons = []

        # Validasi 1: RR harus >= minimum
        if natural_rr < MIN_RR_REQUIRED:
            reasons.append(
                f"Structure RR {natural_rr:.2f} below minimum {MIN_RR_REQUIRED}. "
                f"(This should not happen — Structure Mapper bug?)"
            )
        else:
            reasons.append(f"Structure RR {natural_rr:.2f} >= {MIN_RR_REQUIRED} ✓")

        # Validasi 2: SL distance safety valve (tidak boleh terlalu lebar)
        sl_atr_ratio = sl_distance / atr if atr > 0 else 999.0
        if sl_atr_ratio > MAX_SL_ATR_SAFETY:
            reasons.append(
                f"SL distance {sl_distance:.2f} = {sl_atr_ratio:.1f}x ATR, exceeds safety limit {MAX_SL_ATR_SAFETY}x ATR. "
                f"Setup too wide — WAIT."
            )
        else:
            reasons.append(f"SL distance {sl_distance:.2f} = {sl_atr_ratio:.1f}x ATR ≤ {MAX_SL_ATR_SAFETY}x ✓")
            cleared = True

        # Gabung validasi
        if natural_rr < MIN_RR_REQUIRED:
            cleared = False

        risk_verdict = {
            "cleared": cleared,
            "reasons": reasons,
            "entry_midpoint": round(current_price, 5),
            "stop_loss": round(sl_price, 5),
            "take_profit": round(tp_price, 5),
            "risk_reward": f"1:{natural_rr:.2f}",
            "atr_value": round(atr, 5),
            "risk_per_trade_pct": risk_pct,
            "leverage": leverage,
            "max_running_trades": rm_config.get("max_running_trades", 1),
            "source": "structure_mapper",
            "sl_type": sl_type,
            "tp_type": tp_type,
        }

        print(f"[MONITORING] [Risk Manager] [STRUCTURE PATH] {symbol}: cleared={cleared}, "
              f"SL={sl_price} ({sl_type}), TP={tp_price} ({tp_type}), RR=1:{natural_rr}")
        logger.info(f"[Risk Manager] [STRUCTURE PATH] {symbol} | cleared={cleared} | "
                    f"SL={sl_price} ({sl_type}) | TP={tp_price} ({tp_type}) | RR=1:{natural_rr}")
        print(f"[POST-NODE] [Risk Manager] {symbol} | path=STRUCTURE | cleared={cleared} | "
              f"entry={current_price} | SL={round(sl_price,4)} ({sl_type}) | "
              f"TP={round(tp_price,4)} ({tp_type}) | RR=1:{natural_rr:.2f} | ATR={round(atr,4)}")
        logger.info(f"[Risk Manager] [POST-NODE] {symbol} | path=structure | cleared={cleared} "
                    f"entry={current_price} sl={round(sl_price,4)} tp={round(tp_price,4)} rr=1:{natural_rr:.2f}")
        return {"risk_verdict": risk_verdict}

    # ══════════════════════════════════════════════════════════════════
    #  PATH 2: ATR-based fallback (legacy — jika Structure Mapper wait/gagal)
    # ══════════════════════════════════════════════════════════════════
    wait_reason = structure_map.get("wait_reason", "Structure Mapper returned no valid setup")
    logger.info(f"[Risk Manager] Fallback to ATR-based for {symbol}. Reason: {wait_reason}")

    consensus = state.get("aggregated_verdict", {})
    bias = consensus.get("consensus_bias", "Neutral").lower()

    cleared = False
    reasons = [f"[FALLBACK: ATR-based] Structure Mapper: {wait_reason}"]
    sl_price = 0.0
    tp_price = 0.0
    rr_ratio = 3.0  # legacy fixed RR

    if "bullish" in bias:
        sl_price = current_price - (2.0 * atr)
        risk_dist = current_price - sl_price
        tp_price = current_price + (rr_ratio * risk_dist)
        if sl_price > 0 and tp_price > current_price:
            cleared = True
            reasons.append("ATR fallback: Long parameters generated.")
    elif "bearish" in bias:
        sl_price = current_price + (2.0 * atr)
        risk_dist = sl_price - current_price
        tp_price = current_price - (rr_ratio * risk_dist)
        if sl_price > current_price and tp_price > 0:
            cleared = True
            reasons.append("ATR fallback: Short parameters generated.")
    else:
        reasons.append("Consensus bias Neutral — no trade clearance.")

    # Selalu cleared=False pada fallback path (tidak ada struktur = tidak trade)
    # Kecuali override dari config
    force_atr_fallback = rm_config.get("force_atr_fallback_clearance", False)
    if not force_atr_fallback:
        cleared = False
        reasons.append("ATR fallback clearance disabled — prefer WAIT over unstructured trade.")

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
        "max_running_trades": rm_config.get("max_running_trades", 1),
        "source": "atr_fallback",
    }

    print(f"[MONITORING] [Risk Manager] [ATR FALLBACK] {symbol}: cleared={cleared}, "
          f"entry={current_price}, SL={sl_price}, TP={tp_price}")
    logger.info(f"[Risk Manager] [ATR FALLBACK] {symbol} | cleared={cleared} | "
                f"SL={sl_price} | TP={tp_price} | RR=1:{rr_ratio}")
    print(f"[POST-NODE] [Risk Manager] {symbol} | path=ATR_FALLBACK | cleared={cleared} | "
          f"entry={current_price} | SL={round(sl_price,5)} | TP={round(tp_price,5)} | "
          f"ATR={round(atr,5)} | RR=1:{rr_ratio}")
    logger.info(f"[Risk Manager] [POST-NODE] {symbol} | path=atr_fallback | cleared={cleared} "
                f"entry={current_price} sl={round(sl_price,5)} tp={round(tp_price,5)} "
                f"atr={round(atr,5)} rr=1:{rr_ratio}")
    return {"risk_verdict": risk_verdict}
