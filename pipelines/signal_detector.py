"""
pipelines/signal_detector.py

Pre-filter cepat sebelum memanggil LLM.
Menggunakan scoring system berbasis confluence dari berbagai data source
untuk menentukan apakah ada potensi signal yang layak dikirim ke LLM.

Tujuan utama: HEMAT TOKEN LLM — hanya panggil LLM jika confidence >= threshold.
"""

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class SignalDetector:
    """
    Detector cepat untuk menemukan potensi signal sebelum memanggil LLM.
    Scoring berbasis confluence dari technical, liquidity, sentiment, dan derivatives.
    """

    def __init__(self, min_confidence: float = 0.65):
        self.min_confidence = min_confidence

    def detect(self, context: Dict) -> Dict:
        """
        Evaluasi context dan return signal assessment.

        Parameters:
            context: Full context dict dari ContextBuilder (sudah ada technical,
                     sentiment, derivatives, liquidity, dll)

        Returns:
            Dict berisi:
              - pair: str
              - has_potential_signal: bool
              - confidence: float (0.0 - 1.0)
              - reasons: List[str]
              - suggested_bias: "Bullish" | "Bearish" | "Neutral"
              - signal_type: "LONG" | "SHORT" | None
        """
        pair = context.get("pair", "UNKNOWN")
        technical = context.get("technical", {})
        sentiment = context.get("sentiment", {})
        liquidity = context.get("liquidity", {})
        derivatives = context.get("derivatives", {})

        from config.settings import get_config
        from utils.session_checker import is_active_session
        
        config = get_config()
        active_session = config.get("trading", {}).get("active_session", "all")
        
        if not is_active_session(active_session):
            return {
                "pair": pair,
                "has_potential_signal": False,
                "confidence": 0.0,
                "reasons": [f"Outside active session ('{active_session}')"],
                "suggested_bias": "Neutral",
                "signal_type": None,
                "scores": {"bullish": 0.0, "bearish": 0.0},
            }


        bullish_score = 0.0
        bearish_score = 0.0
        bullish_reasons: List[str] = []
        bearish_reasons: List[str] = []

        # ── 1. Technical Confluence (max ±0.35) ──────────────────────────
        b, be, br, ber = self._score_technical(technical)
        bullish_score += b
        bearish_score += be
        bullish_reasons.extend(br)
        bearish_reasons.extend(ber)

        # ── 2. Liquidity Confluence (max ±0.20) ─────────────────────────
        b, be, br, ber = self._score_liquidity(liquidity)
        bullish_score += b
        bearish_score += be
        bullish_reasons.extend(br)
        bearish_reasons.extend(ber)

        # ── 3. Sentiment Filter (max ±0.15) ─────────────────────────────
        b, be, br, ber = self._score_sentiment(sentiment)
        bullish_score += b
        bearish_score += be
        bullish_reasons.extend(br)
        bearish_reasons.extend(ber)

        # ── 4. Derivatives Filter (max ±0.15) ───────────────────────────
        b, be, br, ber = self._score_derivatives(derivatives)
        bullish_score += b
        bearish_score += be
        bullish_reasons.extend(br)
        bearish_reasons.extend(ber)

        # ── 5. Momentum Divergence Bonus (max ±0.15) ────────────────────
        b, be, br, ber = self._score_momentum_divergence(technical)
        bullish_score += b
        bearish_score += be
        bullish_reasons.extend(br)
        bearish_reasons.extend(ber)

        # ── 6. Order Block Spacial Filter (max ±0.20) ───────────────────
        current_price = context.get("current_price")
        b, be, br, ber = self._score_order_block(technical, current_price)
        bullish_score += b
        bearish_score += be
        bullish_reasons.extend(br)
        bearish_reasons.extend(ber)

        # ── Determine dominant direction ────────────────────────────────
        if bullish_score >= bearish_score:
            dominant_score = bullish_score
            reasons = bullish_reasons
            suggested_bias = "Bullish"
            signal_type = "LONG"
        else:
            dominant_score = bearish_score
            reasons = bearish_reasons
            suggested_bias = "Bearish"
            signal_type = "SHORT"

        final_confidence = min(1.0, max(0.0, dominant_score))

        if final_confidence >= self.min_confidence:
            logger.info(
                f"🎯 {pair} → SIGNAL DETECTED | "
                f"confidence={final_confidence:.2f} | "
                f"bias={suggested_bias} | "
                f"reasons={reasons}"
            )
            return {
                "pair": pair,
                "has_potential_signal": True,
                "confidence": round(final_confidence, 2),
                "reasons": reasons,
                "suggested_bias": suggested_bias,
                "signal_type": signal_type,
                "scores": {
                    "bullish": round(bullish_score, 2),
                    "bearish": round(bearish_score, 2),
                },
            }
        else:
            return {
                "pair": pair,
                "has_potential_signal": False,
                "confidence": round(final_confidence, 2),
                "reasons": ["Signal too weak"],
                "suggested_bias": "Neutral",
                "signal_type": None,
                "scores": {
                    "bullish": round(bullish_score, 2),
                    "bearish": round(bearish_score, 2),
                },
            }

    # ─────────────────────────────────────────────────────────────────────
    #  SCORING COMPONENTS
    #  Setiap method return: (bullish_score, bearish_score, bull_reasons, bear_reasons)
    # ─────────────────────────────────────────────────────────────────────

    def _score_technical(
        self, technical: Dict
    ) -> Tuple[float, float, List[str], List[str]]:
        """Score dari trend H1, momentum M15, price action M5, dan daily bias."""
        bull = 0.0
        bear = 0.0
        br: List[str] = []
        ber: List[str] = []

        # ── Trend H1 (max 0.15) ─────────────────────────────────────────
        trend = technical.get("trend_h1", {})
        trend_regime = str(trend.get("trend_regime", "")).lower()

        if "strong" in trend_regime and "uptrend" in trend_regime:
            bull += 0.15
            br.append("Strong H1 Uptrend")
        elif "uptrend" in trend_regime or "bullish" in trend_regime:
            bull += 0.10
            br.append("H1 Uptrend")
        elif "strong" in trend_regime and "downtrend" in trend_regime:
            bear += 0.15
            ber.append("Strong H1 Downtrend")
        elif "downtrend" in trend_regime or "bearish" in trend_regime:
            bear += 0.10
            ber.append("H1 Downtrend")

        # ── Momentum M15 (max 0.12) ─────────────────────────────────────
        momentum = technical.get("momentum_m15", {})
        mom_bias = str(momentum.get("momentum_bias", "Neutral")).lower()
        rsi = momentum.get("rsi", 50)

        # Removed strict RSI boundaries that penalized strong trends
        if "bullish" in mom_bias:
            bull += 0.12
            br.append(f"Bullish momentum M15 (RSI {rsi:.0f})")
        elif "bearish" in mom_bias:
            bear += 0.12
            ber.append(f"Bearish momentum M15 (RSI {rsi:.0f})")

        # ── Price Action M5 (max 0.08) ──────────────────────────────────
        pa = technical.get("price_action_m5", {})
        pa_bias = str(pa.get("pa_bias", "Neutral")).lower()

        if "bullish" in pa_bias:
            bull += 0.08
            br.append("Bullish price action M5")
        elif "bearish" in pa_bias:
            bear += 0.08
            ber.append("Bearish price action M5")

        # Candlestick patterns
        if pa.get("is_bullish_engulfing") or pa.get("is_hammer"):
            bull += 0.05
            br.append("Bullish candlestick pattern")
        if pa.get("is_bearish_engulfing") or pa.get("is_shooting_star"):
            bear += 0.05
            ber.append("Bearish candlestick pattern")

        # ── Daily Bias (max 0.05) ───────────────────────────────────────
        daily = technical.get("daily_bias", {})
        daily_bias = str(daily.get("bias", "Neutral")).lower()

        if "bullish" in daily_bias:
            bull += 0.05
            br.append("Daily bias Bullish")
        elif "bearish" in daily_bias:
            bear += 0.05
            ber.append("Daily bias Bearish")

        return bull, bear, br, ber

    def _score_liquidity(
        self, liquidity: Dict
    ) -> Tuple[float, float, List[str], List[str]]:
        """Score dari liquidity sweep dan pool proximity."""
        bull = 0.0
        bear = 0.0
        br: List[str] = []
        ber: List[str] = []

        liq_sent_raw = liquidity.get("liquidity_sentiment", "Neutral")
        liq_sent = str(liq_sent_raw).lower()

        if "pdl sweep" in liq_sent or "near low pool" in liq_sent:
            bull += 0.20
            br.append(f"Liquidity: {liq_sent_raw}")
        elif "pdh sweep" in liq_sent or "near high pool" in liq_sent:
            bear += 0.20
            ber.append(f"Liquidity: {liq_sent_raw}")
        elif "bullish" in liq_sent:
            bull += 0.10
            br.append(f"Liquidity: {liq_sent_raw}")
        elif "bearish" in liq_sent:
            bear += 0.10
            ber.append(f"Liquidity: {liq_sent_raw}")

        return bull, bear, br, ber

    def _score_sentiment(
        self, sentiment: Dict
    ) -> Tuple[float, float, List[str], List[str]]:
        """Score dari sentiment analysis (news, social, F&G)."""
        bull = 0.0
        bear = 0.0
        br: List[str] = []
        ber: List[str] = []

        sent_score = sentiment.get("sentiment_score", 50)

        # Relaxed slightly to capture more signals
        if sent_score >= 70:
            bull += 0.15
            br.append(f"Strong Bullish sentiment (score {sent_score})")
        elif sent_score >= 58:
            bull += 0.08
            br.append(f"Bullish sentiment (score {sent_score})")
        elif sent_score <= 30:
            bear += 0.15
            ber.append(f"Strong Bearish sentiment (score {sent_score})")
        elif sent_score <= 42:
            bear += 0.08
            ber.append(f"Bearish sentiment (score {sent_score})")

        return bull, bear, br, ber

    def _score_derivatives(
        self, derivatives: Dict
    ) -> Tuple[float, float, List[str], List[str]]:
        """Score dari derivatives sentiment (funding rate + OI)."""
        bull = 0.0
        bear = 0.0
        br: List[str] = []
        ber: List[str] = []

        deriv_sent_raw = derivatives.get("derivatives_sentiment", "Neutral")
        deriv_sent = str(deriv_sent_raw).lower()

        if "strong bullish" in deriv_sent:
            bull += 0.15
            br.append("Derivatives: Strong Bullish")
        elif "moderate bullish" in deriv_sent or "bullish" in deriv_sent:
            bull += 0.08
            br.append("Derivatives: Bullish")
        elif "strong bearish" in deriv_sent:
            bear += 0.15
            ber.append("Derivatives: Strong Bearish")
        elif "moderate bearish" in deriv_sent or "bearish" in deriv_sent:
            bear += 0.08
            ber.append("Derivatives: Bearish")

        return bull, bear, br, ber

    def _score_momentum_divergence(
        self, technical: Dict
    ) -> Tuple[float, float, List[str], List[str]]:
        """
        Bonus jika ada divergence antara RSI dan trend direction.
        Divergence = potensi reversal, meningkatkan signal.
        """
        bull = 0.0
        bear = 0.0
        br: List[str] = []
        ber: List[str] = []

        trend = technical.get("trend_h1", {})
        momentum = technical.get("momentum_m15", {})
        trend_regime = str(trend.get("trend_regime", "")).lower()
        rsi = momentum.get("rsi", 50)

        # Bullish divergence: downtrend tapi RSI mulai naik (oversold)
        # Increased to 0.15 to better overcome the negative trend penalty
        if ("downtrend" in trend_regime or "bearish" in trend_regime) and rsi < 35:
            bull += 0.15
            br.append(f"Bullish divergence (downtrend + RSI oversold {rsi:.0f})")

        # Bearish divergence: uptrend tapi RSI mulai turun (overbought)
        if ("uptrend" in trend_regime or "bullish" in trend_regime) and rsi > 65:
            bear += 0.15
            ber.append(f"Bearish divergence (uptrend + RSI overbought {rsi:.0f})")

        # Extreme RSI bonus
        if rsi < 25:
            bull += 0.05
            br.append(f"Extreme RSI oversold ({rsi:.0f})")
        elif rsi > 75:
            bear += 0.05
            ber.append(f"Extreme RSI overbought ({rsi:.0f})")

        return bull, bear, br, ber

    def _score_order_block(
        self, technical: Dict, current_price: float
    ) -> Tuple[float, float, List[str], List[str]]:
        """Score if price is inside or very close to an unmitigated Order Block."""
        bull = 0.0
        bear = 0.0
        br: List[str] = []
        ber: List[str] = []

        if not current_price:
            return bull, bear, br, ber

        ob_h1 = technical.get("order_block_h1", {})
        bull_ob_h1 = ob_h1.get("nearest_bullish_ob")
        bear_ob_h1 = ob_h1.get("nearest_bearish_ob")
        
        ob_m15 = technical.get("order_block_m15", {})
        bull_ob_m15 = ob_m15.get("nearest_bullish_ob")
        bear_ob_m15 = ob_m15.get("nearest_bearish_ob")

        # Threshold to consider "in or near" OB (e.g. within 0.2% of the OB boundary)
        threshold_pct = 0.002
        
        if bull_ob_h1:
            top = bull_ob_h1["top"]
            bottom = bull_ob_h1["bottom"]
            # If price is inside the OB or very close to the top
            if (current_price >= bottom) and (current_price <= top * (1 + threshold_pct)):
                bull += 0.20
                br.append(f"Price in Bullish OB H1 ({bottom}-{top})")
                
        if bear_ob_h1:
            top = bear_ob_h1["top"]
            bottom = bear_ob_h1["bottom"]
            # If price is inside the OB or very close to the bottom
            if (current_price <= top) and (current_price >= bottom * (1 - threshold_pct)):
                bear += 0.20
                ber.append(f"Price in Bearish OB H1 ({bottom}-{top})")

        if bull_ob_m15:
            top = bull_ob_m15["top"]
            bottom = bull_ob_m15["bottom"]
            if (current_price >= bottom) and (current_price <= top * (1 + threshold_pct)):
                bull += 0.10
                br.append(f"Price in Bullish OB M15 ({bottom}-{top})")
                
        if bear_ob_m15:
            top = bear_ob_m15["top"]
            bottom = bear_ob_m15["bottom"]
            if (current_price <= top) and (current_price >= bottom * (1 - threshold_pct)):
                bear += 0.10
                ber.append(f"Price in Bearish OB M15 ({bottom}-{top})")

        return bull, bear, br, ber

