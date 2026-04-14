"""
features/sentiment/fear_greed_analysis.py
"""

from typing import Dict, Any


class FearGreedAnalysis:
    @staticmethod
    def analyze(fear_greed_data: Dict) -> Dict[str, Any]:
        if not fear_greed_data or "value" not in fear_greed_data:
            return {
                "value": 50,
                "classification": "Neutral",
                "score_contribution": 0,
                "impact": "Low",
            }

        value = fear_greed_data["value"]
        classification = fear_greed_data.get("classification", "Neutral")

        # Konversi ke score contribution (range -30 sampai +30)
        contribution = (value - 50) * 0.7

        impact = (
            "Very High"
            if value <= 20 or value >= 80
            else "High"
            if value <= 35 or value >= 65
            else "Medium"
        )

        return {
            "value": value,
            "classification": classification,
            "score_contribution": round(contribution, 1),
            "impact": impact,
        }
