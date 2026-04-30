"""
features/sentiment/news_social_analysis.py

Modul untuk mengirim data News + Social (Twitter + Reddit) ke LLM
menggunakan llm/factory.py → mendukung Gemini, Groq, dan Local (LM Studio).
"""

import json
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from llm.system_prompt import SystemPrompt

load_dotenv()

logger = logging.getLogger(__name__)

# JSON schema untuk structured output (digunakan oleh Gemini & LocalClient)
_NEWS_SOCIAL_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_sentiment": {
            "type": "string",
            "enum": [
                "Very Bullish",
                "Strong Bullish",
                "Bullish",
                "Moderate Bullish",
                "Neutral",
                "Moderate Bearish",
                "Bearish",
                "Strong Bearish",
                "Very Bearish",
            ],
        },
        "sentiment_score": {"type": "integer"},
        "confidence": {"type": "number"},
        "dominant_narrative": {"type": "string"},
        "news_impact": {"type": "string"},
        "social_mood": {"type": "string"},
        "key_insights": {"type": "array", "items": {"type": "string"}},
        "trading_implication": {"type": "string"},
    },
    "required": [
        "overall_sentiment",
        "sentiment_score",
        "confidence",
        "dominant_narrative",
        "news_impact",
        "social_mood",
        "key_insights",
        "trading_implication",
    ],
}


class NewsSocialLLMAnalyzer:
    """
    Mengirimkan data News + Social ke LLM via factory (Gemini / Groq / Local).
    """

    def analyze(
        self,
        news_list: List[Dict],
        twitter_data: Dict,
        reddit_data: Dict,
        fear_greed: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Kirim data News + Social ke LLM dan dapatkan analisis sentiment terstruktur.
        """
        from llm.factory import get_news_social_llm

        system_prompt = self._build_system_prompt()
        user_input = self._build_user_input(
            news_list, twitter_data, reddit_data, fear_greed
        )

        try:
            llm = get_news_social_llm()
            provider = type(llm).__name__

            logger.info(f"[NewsSocialAnalyzer] Sending data to LLM via {provider}...")

            # Coba structured_generate dulu (lebih terprediksi)
            try:
                result = llm.structured_generate(
                    system_prompt=system_prompt,
                    user_input=user_input,
                    json_schema=_NEWS_SOCIAL_SCHEMA,
                )
                if result and "error" not in result and "overall_sentiment" in result:
                    logger.info(
                        f"[NewsSocialAnalyzer] ✅ structured_generate OK "
                        f"| Sentiment: {result.get('overall_sentiment')} "
                        f"| Provider: {result.get('provider', provider)}"
                    )
                    self._save_to_db(result)
                    return result
            except Exception as e:
                logger.warning(
                    f"[NewsSocialAnalyzer] structured_generate gagal ({e}), "
                    "fallback ke generate()..."
                )

            # Fallback ke generate() biasa
            raw = llm.generate(system_prompt=system_prompt, user_input=user_input)
            content = raw.get("content", "")
            cleaned = self._clean_llm_output(content)

            try:
                parsed = json.loads(cleaned)
                logger.info(
                    f"[NewsSocialAnalyzer] ✅ generate() OK "
                    f"| Sentiment: {parsed.get('overall_sentiment')}"
                )
                self._save_to_db(parsed)
                return parsed
            except json.JSONDecodeError:
                logger.warning(
                    "[NewsSocialAnalyzer] LLM tidak mengembalikan JSON valid"
                )
                return self._fallback_response()

        except Exception as e:
            logger.error(f"[NewsSocialAnalyzer] Error memanggil LLM: {e}")
            return self._fallback_response()

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:

        return SystemPrompt().get_system_prompt_news_social_sentiment()

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
                if post.get("description"):
                    desc = post.get("description", "").strip()
                    if desc:
                        reddit_text += f"   Context: {desc[:3000]}\n"
                if post.get("comments"):
                    comments_list = post.get("comments", [])
                    if comments_list:
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
        """Membersihkan output LLM dari markdown atau teks ekstra."""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        # Cari JSON object jika ada teks sebelumnya
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
        return text.strip()

    def _fallback_response(self) -> Dict[str, Any]:
        """Fallback jika LLM gagal."""
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

    def _save_to_db(self, result: Dict[str, Any]):
        """Simpan hasil analisis sentimen LLM ke tabel sentiments di PostgreSQL."""
        try:
            from data.database import SessionFactory
            from data.models import SentimentRecord

            record = SentimentRecord(
                asset="CRYPTO",
                source_type="news_social",
                overall_sentiment=result.get("overall_sentiment"),
                sentiment_score=float(result.get("sentiment_score", 0)),
                confidence=float(result.get("confidence", 0)),
                dominant_narrative=result.get("dominant_narrative"),
                news_impact=result.get("news_impact"),
                social_mood=result.get("social_mood"),
                trading_implication=result.get("trading_implication"),
                key_insights=result.get("key_insights", []),
                summary=result.get("dominant_narrative", ""),
                raw_data=result,
            )

            with SessionFactory() as session:
                session.add(record)
                session.commit()
                logger.info(f"[NewsSocialAnalyzer] Sentiment saved to DB (id={record.id})")

        except Exception as e:
            logger.warning(f"[NewsSocialAnalyzer] Failed to save sentiment to DB: {e}")


# ── Module-level helper ────────────────────────────────────────────────────────


def analyze_news_social_with_llm(
    news_list: List[Dict],
    twitter_data: Dict,
    reddit_data: Dict,
    fear_greed: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Fungsi mudah dipanggil dari luar."""
    analyzer = NewsSocialLLMAnalyzer()
    return analyzer.analyze(news_list, twitter_data, reddit_data, fear_greed)
