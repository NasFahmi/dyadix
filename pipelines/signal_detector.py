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
        trend_regime = trend.get("trend_regime", "")

        if "Strong Uptrend" in trend_regime:
            bull += 0.15
            br.append("Strong H1 Uptrend")
        elif "Uptrend" in trend_regime:
            bull += 0.10
            br.append("H1 Uptrend")
        elif "Strong Downtrend" in trend_regime:
            bear += 0.15
            ber.append("Strong H1 Downtrend")
        elif "Downtrend" in trend_regime:
            bear += 0.10
            ber.append("H1 Downtrend")

        # ── Momentum M15 (max 0.12) ─────────────────────────────────────
        momentum = technical.get("momentum_m15", {})
        mom_bias = momentum.get("momentum_bias", "Neutral")
        rsi = momentum.get("rsi", 50)

        if mom_bias == "Bullish" and rsi < 70:
            bull += 0.12
            br.append(f"Bullish momentum M15 (RSI {rsi:.0f})")
        elif mom_bias == "Bearish" and rsi > 30:
            bear += 0.12
            ber.append(f"Bearish momentum M15 (RSI {rsi:.0f})")

        # ── Price Action M5 (max 0.08) ──────────────────────────────────
        pa = technical.get("price_action_m5", {})
        pa_bias = pa.get("pa_bias", "Neutral")

        if "Bullish" in pa_bias:
            bull += 0.08
            br.append("Bullish price action M5")
        elif "Bearish" in pa_bias:
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
        daily_bias = daily.get("bias", "Neutral")

        if daily_bias == "Bullish":
            bull += 0.05
            br.append("Daily bias Bullish")
        elif daily_bias == "Bearish":
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

        liq_sent = liquidity.get("liquidity_sentiment", "Neutral")

        if liq_sent in ("Bullish (PDL Sweep)", "Bullish Pressure (Near Low Pool)"):
            bull += 0.20
            br.append(f"Liquidity: {liq_sent}")
        elif liq_sent in ("Bearish (PDH Sweep)", "Bearish Pressure (Near High Pool)"):
            bear += 0.20
            ber.append(f"Liquidity: {liq_sent}")
        elif "Bullish" in liq_sent:
            bull += 0.10
            br.append(f"Liquidity: {liq_sent}")
        elif "Bearish" in liq_sent:
            bear += 0.10
            ber.append(f"Liquidity: {liq_sent}")

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

        if sent_score >= 75:
            bull += 0.15
            br.append(f"Strong Bullish sentiment (score {sent_score})")
        elif sent_score >= 62:
            bull += 0.08
            br.append(f"Bullish sentiment (score {sent_score})")
        elif sent_score <= 25:
            bear += 0.15
            ber.append(f"Strong Bearish sentiment (score {sent_score})")
        elif sent_score <= 38:
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

        deriv_sent = derivatives.get("derivatives_sentiment", "Neutral")

        if deriv_sent == "Strong Bullish":
            bull += 0.15
            br.append("Derivatives: Strong Bullish")
        elif deriv_sent == "Moderate Bullish":
            bull += 0.08
            br.append("Derivatives: Moderate Bullish")
        elif deriv_sent == "Strong Bearish":
            bear += 0.15
            ber.append("Derivatives: Strong Bearish")
        elif deriv_sent == "Moderate Bearish":
            bear += 0.08
            ber.append("Derivatives: Moderate Bearish")

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
        trend_regime = trend.get("trend_regime", "")
        rsi = momentum.get("rsi", 50)

        # Bullish divergence: downtrend tapi RSI mulai naik (oversold)
        if "Downtrend" in trend_regime and rsi < 35:
            bull += 0.10
            br.append(f"Bullish divergence (downtrend + RSI oversold {rsi:.0f})")

        # Bearish divergence: uptrend tapi RSI mulai turun (overbought)
        if "Uptrend" in trend_regime and rsi > 65:
            bear += 0.10
            ber.append(f"Bearish divergence (uptrend + RSI overbought {rsi:.0f})")

        # Extreme RSI bonus
        if rsi < 25:
            bull += 0.05
            br.append(f"Extreme RSI oversold ({rsi:.0f})")
        elif rsi > 75:
            bear += 0.05
            ber.append(f"Extreme RSI overbought ({rsi:.0f})")

        return bull, bear, br, ber
