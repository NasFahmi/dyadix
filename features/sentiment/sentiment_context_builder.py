import logging
from typing import Dict, Any

from service.sentiment.news.enhanced_news_scraper import EnhancedNewsScraper
from service.sentiment.news.reddit_scraper import RedditScraper
from service.sentiment.news.twitter_scraper import TwitterScraper
from service.sentiment.feer_greed.feer_greed_service import get_fear_and_greed_index
from service.economic.economic_calendar_service import EconomicCalendarService

logger = logging.getLogger(__name__)


def build_sentiment_context(
    news_limit: int = 15,
    reddit_limit_per_sub: int = 5,
    twitter_limit_per_user: int = 5,
    eco_days_ahead: int = 7,
    eco_days_back: int = 0,
) -> Dict[str, Any]:
    """
    Aggregates sentiment and economic calendar data from various sources to build a context object.

    Returns a dictionary containing:
    - news: List of articles
    - social: Dict with reddit and twitter data
    - fear_and_greed: Dict with current index
    - economic_calendar: List of high-impact events
    """
    logger.info("Building sentiment context...")

    context = {
        "news": [],
        "social": {"reddit": {}, "twitter": {}},
        "fear_and_greed": None,
        "economic_calendar": [],
    }

    # 1. Fetch News
    try:
        logger.info("Fetching news...")
        news_scraper = EnhancedNewsScraper()
        context["news"] = news_scraper.fetch_crypto_news(limit=news_limit)
    except Exception as e:
        logger.error(f"Error fetching news: {e}")

    # 2. Fetch Reddit
    try:
        logger.info("Fetching reddit data...")
        reddit_scraper = RedditScraper()
        context["social"]["reddit"] = reddit_scraper.scrape(
            limit_per_subreddit=reddit_limit_per_sub
        )
    except Exception as e:
        logger.error(f"Error fetching reddit: {e}")

    # 3. Fetch Twitter/Influencers
    try:
        logger.info("Fetching twitter/influencer data...")
        twitter_scraper = TwitterScraper()
        context["social"]["twitter"] = twitter_scraper.scrape(
            limit_per_user=twitter_limit_per_user
        )
    except Exception as e:
        logger.error(f"Error fetching twitter: {e}")

    # 4. Fetch Fear & Greed Index
    try:
        logger.info("Fetching fear & greed index...")
        fng_data = get_fear_and_greed_index(limit=1)
        if fng_data and len(fng_data) > 0:
            # fng_data is a list of FearGreedData objects
            context["fear_and_greed"] = {
                "value": fng_data[0].value,
                "classification": fng_data[0].value_classification,
                "timestamp": fng_data[0].timestamp,
            }
    except Exception as e:
        logger.error(f"Error fetching fear & greed: {e}")

    # 5. Fetch Economic Calendar
    try:
        logger.info("Fetching economic calendar...")
        eco_service = EconomicCalendarService()
        context["economic_calendar"] = eco_service.get_high_impact_events(
            days_ahead=eco_days_ahead, days_back=eco_days_back, countries=["USD"]
        )
    except Exception as e:
        logger.error(f"Error fetching economic calendar: {e}")

    logger.info("Sentiment context building completed.")
    return context
