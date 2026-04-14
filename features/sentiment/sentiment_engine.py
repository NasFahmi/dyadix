"""
features/sentiment/sentiment_engine.py - Final Aggregator
"""

from typing import Dict, Any, List
import logging
from datetime import datetime

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
        final = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_sentiment": "Neutral",
            "sentiment_score": 50,
            "confidence": 0.6,
            "dominant_narrative": "",
            "key_insights": [],
            "components": {
                "llm_news_social": llm_result,
                "fear_greed": fear_greed_data or {},
                "economic": {},
            },
        }

        # Economic Analysis
        if economic_data:
            final["components"]["economic"] = {
                "count": len(economic_data),
                "high_impact_today": len(economic_data),
                "score_contribution": -5 if len(economic_data) >= 2 else -2,
            }

        # Hitung Final Score (Weighted)
        final_score = 50.0

        # Bobot:
        # LLM News + Social = 55%
        # Fear & Greed     = 35%
        # Economic         = 10%

        llm_score = llm_result.get("sentiment_score", 50)
        final_score += (llm_score - 50) * 0.55

        if fear_greed_data:
            fg_value = fear_greed_data.get("value", 50)
            final_score += (fg_value - 50) * 0.35

        if economic_data:
            final_score += (
                final["components"]["economic"].get("score_contribution", 0) * 0.10
            )

        final["sentiment_score"] = max(0, min(100, round(final_score)))

        # Overall Sentiment
        final["overall_sentiment"] = SentimentEngine._get_sentiment_label(
            final["sentiment_score"]
        )

        # Dominant Narrative
        final["dominant_narrative"] = SentimentEngine._get_dominant_narrative(
            llm_result, fear_greed_data
        )

        # Key Insights
        final["key_insights"] = SentimentEngine._generate_key_insights(
            llm_result, fear_greed_data, economic_data
        )

        # Confidence
        final["confidence"] = SentimentEngine._calculate_confidence(
            llm_result, fear_greed_data
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
    def _get_dominant_narrative(llm_result: Dict, fg_data: Dict) -> str:
        if fg_data and fg_data.get("value", 50) <= 25:
            return "Extreme Fear Dominates Market"
        if llm_result.get("dominant_narrative"):
            return llm_result["dominant_narrative"]
        return "Mixed Market Sentiment"

    @staticmethod
    def _generate_key_insights(
        llm_result: Dict, fg_data: Dict, economic_data: List
    ) -> List[str]:
        insights = []

        if fg_data:
            insights.append(
                f"F&G Index: {fg_data.get('value')} ({fg_data.get('classification')})"
            )

        if llm_result.get("key_insights"):
            insights.extend(llm_result["key_insights"][:3])

        if economic_data and len(economic_data) > 0:
            insights.append(f"{len(economic_data)} high-impact economic events today")

        return insights[:5]

    @staticmethod
    def _calculate_confidence(llm_result: Dict, fg_data: Dict) -> float:
        base_conf = llm_result.get("confidence", 0.6)
        if fg_data:
            base_conf = (base_conf + 0.8) / 2  # Fear & Greed meningkatkan confidence
        return round(max(0.3, min(1.0, base_conf)), 2)


# Helper
def aggregate_sentiment(
    llm_result: Dict, fear_greed_data: Dict = None, economic_data: List[Dict] = None
) -> Dict:
    return SentimentEngine.aggregate(llm_result, fear_greed_data, economic_data)
