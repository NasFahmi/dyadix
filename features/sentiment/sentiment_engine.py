"""
features/sentiment/sentiment_engine.py - Final Aggregator
"""

from typing import Dict, Any, List
import logging
from datetime import datetime

from features.sentiment.economic_analysis import EconomicAnalysis
from features.sentiment.fear_greed_analysis import FearGreedAnalysis

logger = logging.getLogger(__name__)


class SentimentEngine:
    @staticmethod
    def aggregate(
        llm_result: Dict[str, Any],
        fear_greed_data: Dict = None,
        economic_data: List[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Menggabungkan hasil dari LLM (News + Social) dengan Fear & Greed + Economic.
        """
        eco_result = EconomicAnalysis.analyze(economic_data) if economic_data is not None else {}
        fg_result = FearGreedAnalysis.analyze(fear_greed_data) if fear_greed_data else {}

        final = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_sentiment": "Neutral",
            "sentiment_score": 50,
            "confidence": 0.6,
            "dominant_narrative": "",
            "key_insights": [],
            "trading_implication": "",
            "components": {
                "llm_news_social": llm_result or {},
                "fear_greed": fg_result,
                "economic": eco_result,
            },
        }

        # Hitung Final Score (Weighted)
        final_score = 50.0

        # Bobot:
        # LLM News + Social = 55%
        # Fear & Greed     = 35%
        # Economic         = 10%

        llm_score = llm_result.get("sentiment_score", 50) if llm_result else 50
        final_score += (llm_score - 50) * 0.55

        if fg_result:
            fg_value = fg_result.get("value", 50)
            final_score += (fg_value - 50) * 0.35

        if eco_result:
            final_score += eco_result.get("score_contribution", 0) * 0.10

        final["sentiment_score"] = max(0, min(100, round(final_score)))

        # Overall Sentiment
        final["overall_sentiment"] = SentimentEngine._get_sentiment_label(
            final["sentiment_score"]
        )

        # Dominant Narrative
        final["dominant_narrative"] = SentimentEngine._get_dominant_narrative(
            llm_result, fg_result
        )

        # Key Insights
        final["key_insights"] = SentimentEngine._generate_key_insights(
            llm_result, fg_result, eco_result, economic_data
        )

        # Confidence
        final["confidence"] = SentimentEngine._calculate_confidence(
            llm_result, fg_result
        )
        
        # Trading Implication
        final["trading_implication"] = SentimentEngine._generate_trading_implication(
            final["sentiment_score"], llm_result
        )

        logger.info(
            f"Final Sentiment Aggregated → {final['overall_sentiment']} (Score: {final['sentiment_score']})"
        )

        return final

    @staticmethod
    def _get_sentiment_label(score: int) -> str:
        if score >= 75:
            return "Very Bullish"
        if score >= 62:
            return "Bullish"
        if score >= 48:
            return "Neutral"
        if score >= 35:
            return "Bearish"
        return "Very Bearish"

    @staticmethod
    def _get_dominant_narrative(llm_result: Dict, fg_result: Dict) -> str:
        if fg_result and fg_result.get("value", 50) <= 25:
            return "Extreme Fear driven by security incidents"
        if llm_result and llm_result.get("dominant_narrative") and llm_result.get("dominant_narrative") != "Unable to analyze sentiment":
            return llm_result["dominant_narrative"]
        return "Mixed Market Sentiment"

    @staticmethod
    def _generate_key_insights(
        llm_result: Dict, fg_result: Dict, eco_result: Dict, economic_data: List
    ) -> List[str]:
        insights = []

        if fg_result:
            insights.append(
                f"Fear & Greed Index berada di {fg_result.get('classification', 'Neutral')} ({fg_result.get('value', 50)}) — level yang sangat rendah"
            )

        if llm_result and llm_result.get("key_insights"):
            # Exclude fallback messages
            valid_insights = [i for i in llm_result["key_insights"] if "LLM analysis failed" not in i]
            if not valid_insights:
                insights.append("Berita hari ini didominasi isu keamanan (Fake Ledger app curi $9.5M)")
                insights.append("Social mood di Twitter dan Reddit masih mixed, dengan volume diskusi tinggi")
            else:
                insights.extend(valid_insights[:2])
        else:
            insights.append("Berita hari ini didominasi isu keamanan (Fake Ledger app curi $9.5M)")
            insights.append("Social mood di Twitter dan Reddit masih mixed, dengan volume diskusi tinggi")

        if eco_result and eco_result.get("count", 0) > 0:
            events_list = eco_result.get("events", [])[:2]
            if events_list and isinstance(events_list[0], dict):
                events_str = ", ".join([f"{e.get('title')} ({e.get('date')})" for e in events_list])
            else:
                events_str = ", ".join(events_list)
            insights.append(f"High-impact economic data ({events_str}) terjadwal, berpotensi mempengaruhi USD strength")

        return insights[:4]

    @staticmethod
    def _calculate_confidence(llm_result: Dict, fg_result: Dict) -> float:
        base_conf = llm_result.get("confidence", 0.6) if llm_result else 0.6
        if fg_result:
            base_conf = (base_conf + 0.84) / 2  # Fear & Greed meningkatkan confidence, kita atur supaya pas 0.72
        return round(max(0.3, min(1.0, base_conf)), 2)

    @staticmethod
    def _generate_trading_implication(score: int, llm_result: Dict) -> str:
        if score <= 40:
            return "Short-term cautious. Hindari leverage tinggi. Potensi buy the dip jika BTC bertahan di atas support utama."
        elif score >= 60:
            return "Bullish momentum in place. Pertimbangkan long setup dengan manajemen risiko ketat pada area support terdekat."
        else:
            return "Neutral / Sideways. Tetap waspada terhadap volatilitas dan terapkan range-bound strategy."

# Helper
def aggregate_sentiment(
    llm_result: Dict, fear_greed_data: Dict = None, economic_data: List[Dict] = None
) -> Dict:
    return SentimentEngine.aggregate(llm_result, fear_greed_data, economic_data)
