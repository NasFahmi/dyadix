"""
features/sentiment/economic_analysis.py
"""

from typing import Dict, Any, List
from datetime import datetime


class EconomicAnalysis:
    @staticmethod
    def analyze(events: List[Dict]) -> Dict[str, Any]:
        if not events:
            return {
                "count": 0,
                "high_impact_today": 0,
                "score_contribution": 0,
                "impact": "None",
            }

        high_impact_count = len(events)

        # Economic events high-impact biasanya memberikan tekanan negatif jangka pendek ke crypto
        contribution = (
            -10
            if high_impact_count >= 3
            else -6
            if high_impact_count == 2
            else -3
            if high_impact_count == 1
            else 0
        )

        today = datetime.utcnow().strftime("%Y-%m-%d")
        today_events = [e["title"] for e in events if e.get("date") == today]

        return {
            "count": high_impact_count,
            "high_impact_today": len(today_events),
            "events": today_events[:5],
            "score_contribution": contribution,
            "impact": "High"
            if high_impact_count >= 2
            else "Medium"
            if high_impact_count == 1
            else "Low",
        }
