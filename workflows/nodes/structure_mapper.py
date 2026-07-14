"""
workflows/nodes/structure_mapper.py

Structure Mapper Node — Pemilihan SL/TP berbasis level struktural market.

Menggantikan kalkulasi SL/TP ATR-based di Risk Manager dengan pendekatan level-first:
  - SL ditempatkan di level struktural valid (OB, Pool, PDH/PDL) + buffer 0.12%
  - TP dipilih via cascade dari terdekat ke terjauh, stop saat RR >= min_rr (default 1.5)
  - Level yang di-sweep recently membutuhkan RR lebih tinggi (2.0)
  - Level Moderate pool (< 3 touches) di-skip sebagai TP candidate
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from workflows.state import DyadixState

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Konstanta
# ─────────────────────────────────────────────────────────────────────────────

SL_BUFFER_PCT = 0.0012          # 0.12% buffer di atas/bawah level SL
MIN_RR_NORMAL = 1.5             # RR minimum untuk level biasa
MIN_RR_SWEPT = 2.0              # RR minimum untuk level yang sudah di-sweep recently
MAX_SL_ATR_RATIO = 1.5          # SL dipilih jika jarak <= 1.5x ATR; jika tidak ada, paksa OB
MIN_POOL_TOUCHES = 3            # Minimum touches untuk pool dianggap "Strong" sebagai TP


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: Klasifikasi weight TP candidate
# ─────────────────────────────────────────────────────────────────────────────

def _tp_weight(level_type: str, touches: int, is_swept: bool) -> str:
    """
    Menentukan weight (eligibilitas) sebuah level sebagai TP candidate.

    Returns:
        "HIGH"           → eligible, RR threshold = MIN_RR_NORMAL (1.5)
        "ALWAYS_VALID"   → PDH/PDL selalu eligible, RR threshold = MIN_RR_NORMAL (1.5)
        "REQUIRES_HIGH_RR" → eligible tapi butuh RR >= MIN_RR_SWEPT (2.0) karena baru di-sweep
        "SKIP"           → tidak eligible (Moderate pool atau tidak memenuhi syarat)
    """
    if level_type in ("pdh", "pdl"):
        if is_swept:
            return "REQUIRES_HIGH_RR"
        return "ALWAYS_VALID"

    if level_type in ("bullish_ob_bottom", "bearish_ob_top"):
        if is_swept:
            return "REQUIRES_HIGH_RR"
        return "HIGH"

    if level_type in ("high_pool", "low_pool"):
        if touches < MIN_POOL_TOUCHES:
            return "SKIP"   # Moderate pool — tidak cukup kuat
        if is_swept:
            return "REQUIRES_HIGH_RR"
        return "HIGH"

    return "SKIP"


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: Cek apakah sebuah level ada di recent_sweeps
# ─────────────────────────────────────────────────────────────────────────────

def _is_recently_swept(level_price: float, recent_sweeps: List[Dict], tolerance_pct: float = 0.003) -> bool:
    """
    Cek apakah level_price cocok dengan salah satu level di recent_sweeps
    dalam toleransi ±0.3%.
    """
    for sweep in recent_sweeps:
        swept_price = sweep.get("level_price", 0.0)
        if swept_price <= 0:
            continue
        diff_pct = abs(level_price - swept_price) / swept_price
        if diff_pct <= tolerance_pct:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: Extract ATR dari market_data
# ─────────────────────────────────────────────────────────────────────────────

def _extract_atr(market_data: Dict) -> float:
    """Ambil ATR dari volatility_* key di market_data."""
    for key, val in market_data.items():
        if key.startswith("volatility_") and isinstance(val, dict):
            atr = val.get("atr", 0.0)
            if atr and atr > 0:
                return float(atr)
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: Extract OB data dari market_data
# ─────────────────────────────────────────────────────────────────────────────

def _extract_ob(market_data: Dict) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Ambil nearest_bullish_ob dan nearest_bearish_ob dari market_data.
    Prioritas: order_block_1h (scalping) atau order_block_4h (swing).
    Returns: (bullish_ob, bearish_ob) — masing-masing dict dengan 'top', 'bottom' atau None.
    """
    # Cari key order_block_* dengan prioritas primary timeframe
    primary_key = None
    secondary_key = None
    for key in market_data:
        if key.startswith("order_block_"):
            if "1h" in key or "4h" in key:
                primary_key = key
            elif "15m" in key or "30m" in key:
                secondary_key = key

    ob_key = primary_key or secondary_key
    if not ob_key:
        return None, None

    ob_data = market_data.get(ob_key, {})
    return ob_data.get("nearest_bullish_ob"), ob_data.get("nearest_bearish_ob")


# ─────────────────────────────────────────────────────────────────────────────
#  Core: Build SL candidates
# ─────────────────────────────────────────────────────────────────────────────

def _build_sl_candidates(
    direction: str,
    entry: float,
    atr: float,
    bullish_ob: Optional[Dict],
    bearish_ob: Optional[Dict],
    high_pools: List[Dict],
    low_pools: List[Dict],
    pdh: Optional[float],
    pdl: Optional[float],
) -> List[Dict]:
    """
    Bangun list kandidat SL, diurutkan dari terdekat ke terjauh dari entry.
    Masing-masing item: {"level": float, "type": str, "distance": float, "atr_ratio": float}
    """
    candidates = []

    if direction == "bearish":
        # SL harus DI ATAS entry untuk SELL trade
        if bearish_ob and bearish_ob.get("top"):
            lvl = float(bearish_ob["top"])
            if lvl > entry:
                candidates.append({"level": lvl, "type": "bearish_ob_top", "distance": lvl - entry})

        # High pools yang Strong (sebagai SL candidate harus di atas entry)
        for pool in high_pools:
            if pool.get("strength") == "Strong" and pool.get("touches", 0) >= MIN_POOL_TOUCHES:
                lvl = float(pool["price"])
                if lvl > entry:
                    candidates.append({"level": lvl, "type": "high_pool", "distance": lvl - entry})

        if pdh and float(pdh) > entry:
            candidates.append({"level": float(pdh), "type": "pdh", "distance": float(pdh) - entry})

    elif direction == "bullish":
        # SL harus DI BAWAH entry untuk BUY trade
        if bullish_ob and bullish_ob.get("bottom"):
            lvl = float(bullish_ob["bottom"])
            if lvl < entry:
                candidates.append({"level": lvl, "type": "bullish_ob_bottom", "distance": entry - lvl})

        # Low pools yang Strong
        for pool in low_pools:
            if pool.get("strength") == "Strong" and pool.get("touches", 0) >= MIN_POOL_TOUCHES:
                lvl = float(pool["price"])
                if lvl < entry:
                    candidates.append({"level": lvl, "type": "low_pool", "distance": entry - lvl})

        if pdl and float(pdl) < entry:
            candidates.append({"level": float(pdl), "type": "pdl", "distance": entry - float(pdl)})

    # Tambahkan atr_ratio ke masing-masing candidate
    for c in candidates:
        c["atr_ratio"] = round(c["distance"] / atr, 2) if atr > 0 else 999.0

    # Urutkan dari terdekat ke terjauh
    candidates.sort(key=lambda x: x["distance"])
    return candidates


# ─────────────────────────────────────────────────────────────────────────────
#  Core: Select SL dari candidates
# ─────────────────────────────────────────────────────────────────────────────

def _select_sl(
    candidates: List[Dict],
    direction: str,
    entry: float,
    atr: float,
    buffer_pct: float = SL_BUFFER_PCT,
) -> Optional[Dict]:
    """
    Pilih SL terbaik:
    - Prioritas: yang pertama dengan atr_ratio <= MAX_SL_ATR_RATIO
    - Fallback: jika tidak ada yang <= threshold, pakai yang terdekat (OB atau first candidate)
    - Tambahkan buffer 0.12% di luar level
    """
    if not candidates:
        return None

    # Coba pilih dalam threshold ATR
    selected = None
    for c in candidates:
        if c["atr_ratio"] <= MAX_SL_ATR_RATIO:
            selected = c
            break

    # Fallback ke candidate terdekat jika tidak ada dalam threshold
    if not selected:
        # Preferensikan OB jika ada, kalau tidak ambil yang pertama
        for c in candidates:
            if "ob" in c["type"]:
                selected = c
                break
        if not selected:
            selected = candidates[0]

    # Hitung SL final dengan buffer
    raw_level = selected["level"]
    if direction == "bearish":
        sl_with_buffer = raw_level * (1 + buffer_pct)  # Geser ke atas dari OB top
    else:
        sl_with_buffer = raw_level * (1 - buffer_pct)  # Geser ke bawah dari OB bottom

    sl_distance = abs(sl_with_buffer - entry)

    return {
        "level": round(sl_with_buffer, 4),
        "raw_level": round(raw_level, 4),
        "type": selected["type"],
        "distance": round(sl_distance, 4),
        "atr_ratio": round(sl_distance / atr, 2) if atr > 0 else 999.0,
        "buffer_pct_applied": buffer_pct * 100,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Core: Build TP candidates
# ─────────────────────────────────────────────────────────────────────────────

def _build_tp_candidates(
    direction: str,
    entry: float,
    bullish_ob: Optional[Dict],
    bearish_ob: Optional[Dict],
    high_pools: List[Dict],
    low_pools: List[Dict],
    pdh: Optional[float],
    pdl: Optional[float],
    recent_sweeps: List[Dict],
) -> List[Dict]:
    """
    Bangun list kandidat TP, lengkap dengan weight dan is_swept flag.
    TP harus di arah yang berlawanan dari SL.
    """
    candidates = []

    if direction == "bearish":
        # TP harus DI BAWAH entry untuk SELL trade
        # 1. Low Pools
        for pool in low_pools:
            lvl = float(pool.get("price", 0))
            if lvl <= 0 or lvl >= entry:
                continue
            touches = pool.get("touches", 0)
            is_swept = _is_recently_swept(lvl, recent_sweeps)
            weight = _tp_weight("low_pool", touches, is_swept)
            if weight != "SKIP":
                candidates.append({
                    "level": lvl,
                    "type": f"low_pool_{pool.get('strength', 'unknown').lower()}",
                    "weight": weight,
                    "is_swept": is_swept,
                    "touches": touches,
                    "distance": entry - lvl,
                })

        # 2. PDL
        if pdl and float(pdl) < entry:
            lvl = float(pdl)
            is_swept = _is_recently_swept(lvl, recent_sweeps)
            weight = _tp_weight("pdl", 999, is_swept)
            candidates.append({
                "level": lvl,
                "type": "pdl",
                "weight": weight,
                "is_swept": is_swept,
                "touches": 999,
                "distance": entry - lvl,
            })

        # 3. Bullish OB bottom (sebagai TP dari SELL — harga turun ke area demand)
        if bullish_ob and bullish_ob.get("bottom"):
            lvl = float(bullish_ob["bottom"])
            if lvl < entry:
                is_swept = _is_recently_swept(lvl, recent_sweeps)
                weight = _tp_weight("bullish_ob_bottom", 999, is_swept)
                candidates.append({
                    "level": lvl,
                    "type": "bullish_ob_bottom",
                    "weight": weight,
                    "is_swept": is_swept,
                    "touches": 999,
                    "distance": entry - lvl,
                })

    elif direction == "bullish":
        # TP harus DI ATAS entry untuk BUY trade
        # 1. High Pools
        for pool in high_pools:
            lvl = float(pool.get("price", 0))
            if lvl <= 0 or lvl <= entry:
                continue
            touches = pool.get("touches", 0)
            is_swept = _is_recently_swept(lvl, recent_sweeps)
            weight = _tp_weight("high_pool", touches, is_swept)
            if weight != "SKIP":
                candidates.append({
                    "level": lvl,
                    "type": f"high_pool_{pool.get('strength', 'unknown').lower()}",
                    "weight": weight,
                    "is_swept": is_swept,
                    "touches": touches,
                    "distance": lvl - entry,
                })

        # 2. PDH
        if pdh and float(pdh) > entry:
            lvl = float(pdh)
            is_swept = _is_recently_swept(lvl, recent_sweeps)
            weight = _tp_weight("pdh", 999, is_swept)
            candidates.append({
                "level": lvl,
                "type": "pdh",
                "weight": weight,
                "is_swept": is_swept,
                "touches": 999,
                "distance": lvl - entry,
            })

        # 3. Bearish OB top (sebagai TP dari BUY — harga naik ke area supply)
        if bearish_ob and bearish_ob.get("top"):
            lvl = float(bearish_ob["top"])
            if lvl > entry:
                is_swept = _is_recently_swept(lvl, recent_sweeps)
                weight = _tp_weight("bearish_ob_top", 999, is_swept)
                candidates.append({
                    "level": lvl,
                    "type": "bearish_ob_top",
                    "weight": weight,
                    "is_swept": is_swept,
                    "touches": 999,
                    "distance": lvl - entry,
                })

    # Urutkan dari terdekat ke terjauh
    candidates.sort(key=lambda x: x["distance"])
    return candidates


# ─────────────────────────────────────────────────────────────────────────────
#  Core: Cascade TP selection
# ─────────────────────────────────────────────────────────────────────────────

def _cascade_tp(
    tp_candidates: List[Dict],
    sl_distance: float,
    min_rr_normal: float = MIN_RR_NORMAL,
    min_rr_swept: float = MIN_RR_SWEPT,
) -> Tuple[Optional[Dict], List[Dict]]:
    """
    Cascade melalui TP candidates dari terdekat ke terjauh.
    Hentikan saat menemukan level yang memenuhi RR threshold sesuai weight-nya.

    Returns:
        (selected_tp: dict | None, cascade_log: list)
    """
    cascade_log = []

    for candidate in tp_candidates:
        tp_distance = candidate["distance"]
        if sl_distance <= 0:
            cascade_log.append({**candidate, "rr": 0.0, "result": "INVALID_SL_DISTANCE"})
            continue

        rr = round(tp_distance / sl_distance, 2)
        weight = candidate["weight"]

        # Tentukan RR threshold berdasarkan weight
        if weight == "REQUIRES_HIGH_RR":
            threshold = min_rr_swept
        else:
            threshold = min_rr_normal  # HIGH atau ALWAYS_VALID

        if rr >= threshold:
            cascade_log.append({
                "level": candidate["level"],
                "type": candidate["type"],
                "weight": weight,
                "is_swept": candidate["is_swept"],
                "rr": rr,
                "threshold": threshold,
                "result": "ACCEPTED",
            })
            return candidate, cascade_log
        else:
            cascade_log.append({
                "level": candidate["level"],
                "type": candidate["type"],
                "weight": weight,
                "is_swept": candidate["is_swept"],
                "rr": rr,
                "threshold": threshold,
                "result": "RR_TOO_LOW",
            })

    return None, cascade_log


# ─────────────────────────────────────────────────────────────────────────────
#  Main Node Function
# ─────────────────────────────────────────────────────────────────────────────

def structure_mapper_node(state: DyadixState) -> dict:
    """
    Structure Mapper Node — Mapping level struktural untuk penentuan SL/TP.

    Membaca market_data dan liquidity_data dari state secara langsung (bukan verdicts),
    lalu menghasilkan structure_map berisi SL/TP yang bermakna secara teknikal.
    """
    symbol = state.get("symbol", "UNKNOWN")
    entry = state.get("realtime_price", 0.0)
    market_data = state.get("market_data", {})
    liquidity_data = state.get("liquidity_data", {})
    aggregated = state.get("aggregated_verdict", {})

    print(f"[MONITORING] [Structure Mapper] Mapping structural levels for {symbol} @ {entry}...")
    logger.info(f"[Structure Mapper] Start for {symbol} @ entry={entry}")

    # ── Guard: entry price harus valid ─────────────────────────────────────
    if entry <= 0:
        logger.warning(f"[Structure Mapper] Invalid entry price for {symbol}. Returning wait.")
        return {"structure_map": {"should_wait": True, "wait_reason": "Invalid entry price"}}

    # ── Extract consensus direction ─────────────────────────────────────────
    consensus_bias = aggregated.get("consensus_bias", "Neutral").lower()
    if "bullish" in consensus_bias:
        direction = "bullish"
    elif "bearish" in consensus_bias:
        direction = "bearish"
    else:
        logger.info(f"[Structure Mapper] Neutral consensus for {symbol}. No structural mapping needed.")
        return {
            "structure_map": {
                "should_wait": True,
                "wait_reason": "Consensus bias is Neutral — no directional setup to map",
                "direction": "neutral",
            }
        }

    # ── Extract ATR ─────────────────────────────────────────────────────────
    atr = _extract_atr(market_data)
    if atr <= 0:
        atr = entry * 0.005  # Fallback 0.5%
        logger.warning(f"[Structure Mapper] ATR not found for {symbol}, using fallback 0.5% = {atr:.2f}")

    # ── Extract Order Blocks ────────────────────────────────────────────────
    bullish_ob, bearish_ob = _extract_ob(market_data)

    # ── Extract Liquidity Pools ─────────────────────────────────────────────
    pools = liquidity_data.get("liquidity_pools", {})
    high_pools = pools.get("highs", [])
    low_pools = pools.get("lows", [])

    # ── Extract Key Levels ─────────────────────────────────────────────────
    key_levels = liquidity_data.get("key_levels", {})
    pdh = key_levels.get("pdh")
    pdl = key_levels.get("pdl")

    # ── Extract Recent Sweeps ──────────────────────────────────────────────
    recent_sweeps = liquidity_data.get("recent_sweeps", [])

    logger.info(
        f"[Structure Mapper] {symbol} | direction={direction} | atr={atr:.2f} | "
        f"bull_ob={'yes' if bullish_ob else 'no'} | bear_ob={'yes' if bearish_ob else 'no'} | "
        f"high_pools={len(high_pools)} | low_pools={len(low_pools)} | "
        f"pdh={pdh} | pdl={pdl} | recent_sweeps={len(recent_sweeps)}"
    )

    # ── Build SL Candidates ────────────────────────────────────────────────
    sl_candidates = _build_sl_candidates(
        direction=direction,
        entry=entry,
        atr=atr,
        bullish_ob=bullish_ob,
        bearish_ob=bearish_ob,
        high_pools=high_pools,
        low_pools=low_pools,
        pdh=pdh,
        pdl=pdl,
    )

    if not sl_candidates:
        logger.warning(f"[Structure Mapper] No SL candidates found for {symbol} ({direction}). Returning wait.")
        return {
            "structure_map": {
                "should_wait": True,
                "wait_reason": f"No structural SL level found above/below entry for {direction} setup",
                "direction": direction,
                "entry_reference": entry,
                "atr_reference": round(atr, 4),
            }
        }

    # ── Select SL ──────────────────────────────────────────────────────────
    sl_result = _select_sl(
        candidates=sl_candidates,
        direction=direction,
        entry=entry,
        atr=atr,
        buffer_pct=SL_BUFFER_PCT,
    )

    if not sl_result:
        return {
            "structure_map": {
                "should_wait": True,
                "wait_reason": "Failed to select SL from structural candidates",
                "direction": direction,
                "entry_reference": entry,
            }
        }

    sl_distance = sl_result["distance"]

    # ── Build TP Candidates ────────────────────────────────────────────────
    tp_candidates = _build_tp_candidates(
        direction=direction,
        entry=entry,
        bullish_ob=bullish_ob,
        bearish_ob=bearish_ob,
        high_pools=high_pools,
        low_pools=low_pools,
        pdh=pdh,
        pdl=pdl,
        recent_sweeps=recent_sweeps,
    )

    if not tp_candidates:
        logger.warning(f"[Structure Mapper] No TP candidates found for {symbol} ({direction}).")
        return {
            "structure_map": {
                "should_wait": True,
                "wait_reason": "No eligible TP structural level found (all pools Moderate or no levels on this side)",
                "direction": direction,
                "entry_reference": entry,
                "recommended_sl": sl_result["level"],
                "sl_type": sl_result["type"],
                "sl_distance": sl_distance,
                "atr_reference": round(atr, 4),
            }
        }

    # ── Cascade TP Selection ───────────────────────────────────────────────
    selected_tp, cascade_log = _cascade_tp(
        tp_candidates=tp_candidates,
        sl_distance=sl_distance,
    )

    if not selected_tp:
        logger.info(
            f"[Structure Mapper] {symbol}: All {len(tp_candidates)} TP candidates exhausted — no valid RR. "
            f"Cascade log: {cascade_log}"
        )
        return {
            "structure_map": {
                "should_wait": True,
                "wait_reason": (
                    f"No TP level achieved minimum RR {MIN_RR_NORMAL}. "
                    f"Best was {cascade_log[-1]['rr'] if cascade_log else 'N/A'} "
                    f"({len(tp_candidates)} levels tried)"
                ),
                "direction": direction,
                "entry_reference": entry,
                "recommended_sl": sl_result["level"],
                "sl_type": sl_result["type"],
                "sl_raw_level": sl_result["raw_level"],
                "sl_distance": sl_distance,
                "sl_distance_atr_ratio": sl_result["atr_ratio"],
                "atr_reference": round(atr, 4),
                "cascade_log": cascade_log,
            }
        }

    # ── Build Final structure_map ───────────────────────────────────────────
    tp_distance = selected_tp["distance"]
    natural_rr = round(tp_distance / sl_distance, 2) if sl_distance > 0 else 0.0

    structure_map = {
        "should_wait": False,
        "wait_reason": "",
        "direction": direction,
        "entry_reference": round(entry, 4),

        # SL
        "recommended_sl": sl_result["level"],
        "sl_type": sl_result["type"],
        "sl_raw_level": sl_result["raw_level"],
        "sl_distance": round(sl_distance, 4),
        "sl_distance_atr_ratio": sl_result["atr_ratio"],
        "sl_buffer_pct": sl_result["buffer_pct_applied"],

        # TP
        "recommended_tp": round(selected_tp["level"], 4),
        "tp_type": selected_tp["type"],
        "tp_distance": round(tp_distance, 4),
        "tp_was_swept": selected_tp["is_swept"],

        # RR
        "natural_rr": natural_rr,

        # Debug / Audit
        "cascade_attempts": len(cascade_log),
        "cascade_log": cascade_log,
        "atr_reference": round(atr, 4),
        "sl_buffer_pct_applied": SL_BUFFER_PCT * 100,
    }

    print(
        f"[POST-NODE] [Structure Mapper] {symbol} | direction={direction} | "
        f"SL={sl_result['level']} ({sl_result['type']}) | "
        f"TP={selected_tp['level']} ({selected_tp['type']}) | "
        f"RR=1:{natural_rr} | cascade_attempts={len(cascade_log)}"
    )
    logger.info(
        f"[Structure Mapper] {symbol} | SL={sl_result['level']} ({sl_result['type']}) | "
        f"TP={selected_tp['level']} ({selected_tp['type']}) | RR=1:{natural_rr}"
    )

    return {"structure_map": structure_map}
