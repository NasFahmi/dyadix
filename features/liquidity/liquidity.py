"""
features/liquidity.py

Liquidity Engine - Deteksi Swing Pool & Sweep berbasis Kuantitatif.

Kriteria Kualitas:
  1. Jumlah pool masuk akal: 2–4 highs & 2–4 lows
  2. Jarak antar pool minimal 0.4% (BTC)
  3. Strength bervariasi (Strong / Moderate)
  4. Sweep detection tajam (PDH, PDL, dan Pool Sweep)
  5. Sentiment tajam & kontekstual
  6. Hanya pool yang relevan dengan harga saat ini (dalam radius 5%)
  7. Output ringkas untuk LLM
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class LiquidityEngine:

    # === Konfigurasi Konstanta ===
    # Jarak minimum antar pool (0.4% untuk BTC)
    MIN_POOL_DISTANCE_PCT = 0.004
    # Radius relevance dari harga saat ini (5%)
    RELEVANCE_RADIUS_PCT = 0.05
    # Batas minimum swing points agar pool valid
    MIN_SWING_WINDOW = 8
    # Batas maksimal pool yang ditampilkan per sisi
    MAX_POOLS = 4
    # Threshold strong vs moderate
    STRONG_THRESHOLD = 3

    @staticmethod
    def calculate(
        df: pd.DataFrame, daily_bias: Dict = None, timeframe: str = "5m"
    ) -> Dict:
        if df.empty or len(df) < 50:
            logger.warning(f"Data tidak cukup untuk liquidity analysis di {timeframe}")
            return {"error": "Insufficient data (min 50 candles)"}

        df = df.copy().reset_index(drop=True)
        current_price = float(df["close"].iloc[-1])

        result = {
            "timeframe": timeframe,
            "current_price": round(current_price, 2),
            "key_levels": {},
            "liquidity_pools": {"highs": [], "lows": []},
            "recent_sweeps": [],
            "liquidity_sentiment": "Neutral",
            "interpretation": "",
        }

        # ====== 1. PDH / PDL Key Levels & Sweep Detection ======
        if daily_bias:
            pdh = daily_bias.get("previous_day_high")
            pdl = daily_bias.get("previous_day_low")
            if pdh and pdl:
                result["key_levels"] = {
                    "pdh": round(float(pdh), 2),
                    "pdl": round(float(pdl), 2),
                }
                # Sweep PDH: recent candled menyentuh PDH tapi harga sekarang sudah bounce ke bawah
                recent_high = df["high"].tail(10).max()
                recent_low = df["low"].tail(10).min()

                if recent_high >= pdh and current_price < pdh * 0.9985:
                    result["recent_sweeps"].append({
                        "level": "PDH",
                        "level_price": round(float(pdh), 2),
                        "type": "Bearish Sweep",
                    })

                if recent_low <= pdl and current_price > pdl * 1.0015:
                    result["recent_sweeps"].append({
                        "level": "PDL",
                        "level_price": round(float(pdl), 2),
                        "type": "Bullish Sweep",
                    })

        # ====== 2. Swing-based Liquidity Pool Detection ======
        high_pools = LiquidityEngine._find_swing_pools(
            df=df,
            price_series=df["high"],
            close_series=df["close"],
            side="high",
            current_price=current_price,
        )
        low_pools = LiquidityEngine._find_swing_pools(
            df=df,
            price_series=df["low"],
            close_series=df["close"],
            side="low",
            current_price=current_price,
        )

        # ====== 3. Pool Sweep Detection ======
        high_pools, low_pools, pool_sweeps = LiquidityEngine._detect_pool_sweeps(
            df, high_pools, low_pools, current_price
        )
        result["recent_sweeps"].extend(pool_sweeps)

        result["liquidity_pools"]["highs"] = high_pools
        result["liquidity_pools"]["lows"] = low_pools

        # ====== 4. Determine Sentiment ======
        result["liquidity_sentiment"] = LiquidityEngine._determine_sentiment(
            result["recent_sweeps"], result["liquidity_pools"], current_price
        )

        # ====== 5. Interpretation ======
        result["interpretation"] = LiquidityEngine._generate_interpretation(result)

        logger.info(
            f"Liquidity [{timeframe}] | Price: {current_price:.2f} | "
            f"Pools: {len(high_pools)}H/{len(low_pools)}L | "
            f"Sweeps: {len(result['recent_sweeps'])} | "
            f"Sentiment: {result['liquidity_sentiment']}"
        )

        return result

    @staticmethod
    def _find_swing_pools(
        df: pd.DataFrame,
        price_series: pd.Series,
        close_series: pd.Series,
        side: str,
        current_price: float,
    ) -> List[Dict]:
        """
        Temukan Swing High/Low yang valid sebagai Liquidity Pool.
        
        Validasi:
        - Swing berdasarkan window 8 candle (cukup ketat)
        - Hanya dalam radius 5% dari harga sekarang (relevan)
        - Minimal jarak 0.4% antar pool (menghindari cluster noisy)
        - Strength dinilai dari jumlah touches yang UNIK (bukan semua baris)
        """
        w = LiquidityEngine.MIN_SWING_WINDOW
        candidates = []
        n = len(price_series)

        for i in range(w, n - w):
            val = price_series.iloc[i]

            if side == "high":
                is_swing = val == price_series.iloc[i - w: i + w + 1].max()
            else:
                is_swing = val == price_series.iloc[i - w: i + w + 1].min()

            if not is_swing:
                continue

            # Filter: hanya pool dalam radius 5% dari harga sekarang
            distance_pct = abs(val - current_price) / current_price
            if distance_pct > LiquidityEngine.RELEVANCE_RADIUS_PCT:
                continue

            # Hitung touches: berapa banyak candle yang menyentuh area ini
            # Tolerance: 0.2% dari level (cukup ketat untuk mengilangkan noise)
            tol = val * 0.002
            if side == "high":
                touches = int(((df["high"] >= val - tol) & (df["high"] <= val + tol)).sum())
            else:
                touches = int(((df["low"] >= val - tol) & (df["low"] <= val + tol)).sum())

            # Minimal 2 touches agar dianggap valid pool
            if touches < 2:
                continue

            # Recency score: lebih tinggi jika swing-nya lebih baru (0-100)
            recency = int(round((i / n) * 100))

            candidates.append({
                "price": round(float(val), 2),
                "touches": touches,
                "recency": recency,
                "strength": "Strong" if touches >= LiquidityEngine.STRONG_THRESHOLD else "Moderate",
            })

        if not candidates:
            return []

        # Sorting: prioritaskan touches terbanyak, kemudian yang lebih baru
        candidates.sort(key=lambda x: (x["touches"], x["recency"]), reverse=True)

        # Deduplication: buang pool yang terlalu berdekatan (< 0.4%)
        unique_pools = []
        for p in candidates:
            too_close = any(
                abs(p["price"] - ex["price"]) / p["price"] < LiquidityEngine.MIN_POOL_DISTANCE_PCT
                for ex in unique_pools
            )
            if not too_close:
                unique_pools.append(p)
            if len(unique_pools) >= LiquidityEngine.MAX_POOLS:
                break

        # Hapus key 'recency' dari output akhir (hanya untuk internal scoring)
        for pool in unique_pools:
            pool.pop("recency", None)

        return unique_pools

    @staticmethod
    def _detect_pool_sweeps(
        df: pd.DataFrame,
        high_pools: List[Dict],
        low_pools: List[Dict],
        current_price: float,
    ):
        """
        Deteksi apakah pool baru saja di-sweep:
        Harga sempat menembus level pool tapi sudah bounce balik (dengan jarak >0.2%).
        """
        pool_sweeps = []
        recent_high = df["high"].tail(8).max()
        recent_low = df["low"].tail(8).min()

        swept_high_pools = []
        for pool in high_pools:
            if recent_high >= pool["price"] and current_price < pool["price"] * 0.998:
                pool_sweeps.append({
                    "level": "High Pool",
                    "level_price": pool["price"],
                    "type": "Bearish Sweep",
                })
            else:
                swept_high_pools.append(pool)

        swept_low_pools = []
        for pool in low_pools:
            if recent_low <= pool["price"] and current_price > pool["price"] * 1.002:
                pool_sweeps.append({
                    "level": "Low Pool",
                    "level_price": pool["price"],
                    "type": "Bullish Sweep",
                })
            else:
                swept_low_pools.append(pool)

        return swept_high_pools, swept_low_pools, pool_sweeps

    @staticmethod
    def _determine_sentiment(
        sweeps: List, pools: Dict, current_price: float
    ) -> str:
        """Tentukan Liquidity Sentiment berdasarkan sweeps dan proximity ke pool."""
        # Prioritas 1: Sweep baru
        if sweeps:
            bullish_sweeps = [s for s in sweeps if s["type"] == "Bullish Sweep"]
            bearish_sweeps = [s for s in sweeps if s["type"] == "Bearish Sweep"]

            if bullish_sweeps and not bearish_sweeps:
                level = bullish_sweeps[-1]["level"]
                return f"Bullish ({level} Sweep)"
            if bearish_sweeps and not bullish_sweeps:
                level = bearish_sweeps[-1]["level"]
                return f"Bearish ({level} Sweep)"
            if bullish_sweeps and bearish_sweeps:
                return "Mixed Sweep (Choppy)"

        # Prioritas 2: Proximity ke pool (harga dekat pool)
        for pool in pools.get("lows", []):
            proximity = abs(current_price - pool["price"]) / current_price
            if proximity < 0.003:
                return f"Bullish Pressure (Near Low Pool ~{pool['price']:.0f})"

        for pool in pools.get("highs", []):
            proximity = abs(current_price - pool["price"]) / current_price
            if proximity < 0.003:
                return f"Bearish Pressure (Near High Pool ~{pool['price']:.0f})"

        return "Neutral"

    @staticmethod
    def _generate_interpretation(result: Dict) -> str:
        """Teks ringkas yang mudah dibaca LLM."""
        parts = []

        if result["recent_sweeps"]:
            sweep_desc = ", ".join(
                f"{s['level']} @ {s['level_price']}" for s in result["recent_sweeps"]
            )
            parts.append(f"Recent sweeps: [{sweep_desc}]")

        h = len(result["liquidity_pools"]["highs"])
        lo = len(result["liquidity_pools"]["lows"])
        if h > 0 or lo > 0:
            parts.append(f"{h} resistance pool(s) dan {lo} support pool(s) aktif")

        if result["key_levels"]:
            kl = result["key_levels"]
            parts.append(f"PDH={kl.get('pdh')}, PDL={kl.get('pdl')}")

        if not parts:
            return "No significant liquidity structure detected"

        return " | ".join(parts)

    @staticmethod
    def get_latest_summary(result: Dict) -> Dict:
        """Summary ringkas untuk LLM."""
        if "error" in result:
            return result

        return {
            "timeframe": result.get("timeframe"),
            "current_price": result.get("current_price"),
            "liquidity_sentiment": result.get("liquidity_sentiment"),
            "recent_sweeps": result.get("recent_sweeps", []),
            "key_levels": result.get("key_levels", {}),
            "liquidity_pools": {
                "highs": result["liquidity_pools"].get("highs", []),
                "lows": result["liquidity_pools"].get("lows", []),
            },
            "interpretation": result.get("interpretation", ""),
        }


def calculate_liquidity_features(
    df: pd.DataFrame, daily_bias: Dict = None, timeframe: str = "5m"
):
    result = LiquidityEngine.calculate(df, daily_bias, timeframe)
    summary = LiquidityEngine.get_latest_summary(result)
    return df, summary
