"""
Reddit Scraper
==============
Scrapes post titles from crypto subreddits using Reddit's public JSON API.
No authentication required.
"""

import logging
import requests
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class RedditScraper:
    """Scrapes post titles from crypto-related subreddits."""

    DEFAULT_SUBREDDITS = [
        "CryptoCurrency", "bitcoin", "ethereum",
        "CryptoMarkets", "solana", "binance"
    ]

    HEADERS = {
        "User-Agent": "DyadixBot/1.0 (Crypto Sentiment Aggregator)"
    }

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def scrape(
        self,
        subreddits: Optional[List[str]] = None,
        limit_per_subreddit: int = 15,
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Scrape recent posts from subreddits.

        Args:
            subreddits: List of subreddit names (without 'r/' prefix).
            limit_per_subreddit: Max posts per subreddit.

        Returns:
            Dict mapping subreddit name -> list of post dicts with keys:
            title, url, score, num_comments.
        """
        if subreddits is None:
            subreddits = self.DEFAULT_SUBREDDITS

        results: Dict[str, List[Dict[str, str]]] = {}

        for sub in subreddits:
            sub = sub.strip().replace("r/", "")
            url = f"https://www.reddit.com/r/{sub}/new.json?limit={limit_per_subreddit}"
            logger.info(f"Scraping /r/{sub} ...")

            try:
                response = requests.get(url, headers=self.HEADERS, timeout=self.timeout)
                response.raise_for_status()

                data = response.json()
                posts = data.get("data", {}).get("children", [])

                items = []
                for post in posts:
                    post_data = post.get("data", {})
                    title = post_data.get("title")
                    if title:
                        items.append({
                            "title": title,
                            "url": f"https://reddit.com{post_data.get('permalink', '')}",
                            "score": post_data.get("score", 0),
                            "num_comments": post_data.get("num_comments", 0),
                        })

                results[sub] = items
                logger.info(f"  Found {len(items)} posts from /r/{sub}")

            except requests.exceptions.Timeout:
                logger.warning(f"  Timeout for /r/{sub}")
                results[sub] = []
            except requests.exceptions.HTTPError as e:
                logger.warning(f"  HTTP error for /r/{sub}: {e}")
                results[sub] = []
            except requests.exceptions.RequestException as e:
                logger.warning(f"  Request error for /r/{sub}: {e}")
                results[sub] = []
            except (ValueError, KeyError) as e:
                logger.warning(f"  JSON parse error for /r/{sub}: {e}")
                results[sub] = []

        total = sum(len(v) for v in results.values())
        logger.info(f"Reddit scraping done. Total posts: {total}")
        return results
