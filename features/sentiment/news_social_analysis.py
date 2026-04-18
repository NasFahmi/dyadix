"""
features/sentiment/news_social_analysis.py

Modul untuk mengirim data News + Social (Twitter + Reddit) ke LLM (DragonLLM via LM Studio)
menggunakan API format yang kamu tunjukkan.
"""

import json
import os
import requests
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class NewsSocialLLMAnalyzer:
    """
    Mengirimkan data News + Social ke LLM via LM Studio API
    dan mengembalikan hasil analisis sentiment yang terstruktur.
    """

    def __init__(self, base_url: str = "http://localhost:1234"):
        self.base_url = base_url.rstrip("/")
        self.endpoint = f"{self.base_url}/api/v1/chat"
        self.model = os.getenv("NEWS_SOCIAL_ANALYSIS_MODEL", "llama-open-finance-8b")

    def analyze(
        self,
        news_list: List[Dict],
        twitter_data: Dict,
        reddit_data: Dict,
        fear_greed: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Kirim data News + Social ke LLM dan dapatkan analisis sentiment.
        """
        # Siapkan prompt + data
        system_prompt = self._build_system_prompt()
        user_input = self._build_user_input(
            news_list, twitter_data, reddit_data, fear_greed
        )

        payload = {
            "model": self.model,
            "system_prompt": system_prompt,
            "input": user_input,
            "temperature": 0.3,
            "stream": False,
        }

        try:
            logger.info("Sending News + Social data to LLM...")
            response = requests.post(
                self.endpoint,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=600,
            )

            if response.status_code != 200:
                logger.error(f"LLM API error: {response.status_code} - {response.text}")
                return self._fallback_response()

            result = response.json()

            # Ekstrak output dari response LM Studio
            if "output" in result and len(result["output"]) > 0:
                content = result["output"][0].get("content", "")

                # Bersihkan jika ada markdown atau extra text
                cleaned = self._clean_llm_output(content)

                try:
                    parsed = json.loads(cleaned)
                    logger.info(
                        f"LLM analysis successful | Sentiment: {parsed.get('overall_sentiment')}"
                    )
                    return parsed
                except json.JSONDecodeError:
                    logger.warning("LLM tidak mengembalikan JSON yang valid")
                    return self._fallback_response()

            return self._fallback_response()

        except requests.exceptions.Timeout:
            logger.error("LLM request timeout")
            return self._fallback_response()
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return self._fallback_response()

    def _build_system_prompt(self) -> str:
        return """You are DragonLLM Open Finance - Crypto Sentiment Analyst.

Analyze the provided news and social media data carefully.
Focus on market sentiment impact for the next 24-48 hours.
Be objective, concise, and trading-oriented.

Return ONLY a valid JSON object. Do not add any explanation or markdown."""

    def _build_user_input(
        self,
        news_list: List[Dict],
        twitter_data: Dict,
        reddit_data: Dict,
        fear_greed: Optional[Dict] = None,
    ) -> str:

        news_text = (
            "\n".join(
                [
                    f"- {item.get('title', '')} | {item.get('summary', '')[:150]}"
                    for item in news_list[:12]
                ]
            )
            if news_list
            else "No news data."
        )

        twitter_text = ""
        for user, posts in list(twitter_data.items())[:6]:
            for post in posts[:3]:
                twitter_text += f"[{user}] {post.get('text', '')[:120]}\n"

        reddit_text = ""
        for sub, posts in list(reddit_data.items())[:5]:
            for post in posts[:3]:
                reddit_text += f"[r/{sub}] {post.get('title', '')}\n"
                # Add description if available (Increased limit to 3000 for full context)
                if post.get("description"):
                    desc = post.get("description", "").strip()
                    if desc:
                        reddit_text += f"   Context: {desc[:3000]}\n"
                # Add top comments if available
                if post.get("comments"):
                    comments_list = post.get("comments", [])
                    if comments_list:
                        # Increased comment context as well
                        comments_summary = " | ".join([c[:200] for c in comments_list])
                        reddit_text += f"   Comments: {comments_summary[:500]}\n"

        fg_text = (
            f"Fear & Greed Index: {fear_greed.get('value')} ({fear_greed.get('classification')})"
            if fear_greed
            else "No F&G data."
        )

        return f"""=== NEWS (last 24h) ===
{news_text}

=== TWITTER / INFLUENCERS ===
{twitter_text or "No significant twitter data."}

=== REDDIT TOP POSTS ===
{reddit_text or "No significant reddit data."}

=== FEAR & GREED ===
{fg_text}

Analyze the sentiment and return JSON only."""

    def _clean_llm_output(self, text: str) -> str:
        """Membersihkan output LLM dari markdown atau text ekstra"""
        text = text.strip()
        # Hapus ```json dan ```
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _fallback_response(self) -> Dict[str, Any]:
        """Fallback jika LLM gagal"""
        return {
            "overall_sentiment": "Neutral",
            "sentiment_score": 50,
            "confidence": 0.3,
            "dominant_narrative": "Unable to analyze sentiment",
            "news_impact": "Neutral",
            "social_mood": "Mixed",
            "key_insights": ["LLM analysis failed or timed out"],
            "trading_implication": "Proceed with caution",
        }


# Helper function
def analyze_news_social_with_llm(
    news_list: List[Dict],
    twitter_data: Dict,
    reddit_data: Dict,
    fear_greed: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Fungsi mudah dipanggil dari luar"""
    analyzer = NewsSocialLLMAnalyzer()
    return analyzer.analyze(news_list, twitter_data, reddit_data, fear_greed)
