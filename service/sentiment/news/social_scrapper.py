"""
Social Scrapper (formerly Reddit Scraper)
=========================================
Scrapes post titles from crypto subreddits using Reddit's public JSON API.
No authentication required.
"""

import logging
import requests
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)


class SocialScrapper:
    """Scrapes post titles from crypto-related subreddits."""

    DEFAULT_SUBREDDITS = [
        "CryptoCurrency",
        "bitcoin",
        "ethereum",
        "CryptoMarkets",
        "solana",
        "binance",
    ]

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def scrape(
        self,
        subreddits: Optional[List[str]] = None,
        limit_per_subreddit: int = 15,
        include_comments: bool = False,
        comments_limit: int = 3,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Scrape recent posts from subreddits with optional details.

        Args:
            subreddits: List of subreddit names (without 'r/' prefix).
            limit_per_subreddit: Max posts per subreddit.
            include_comments: Whether to fetch top comments for each post.
            comments_limit: Max comments per post to fetch.

        Returns:
            Dict mapping subreddit name -> list of post dicts with keys:
            title, description, url, score, num_comments, comments (optional).
        """
        if subreddits is None:
            subreddits = self.DEFAULT_SUBREDDITS

        results: Dict[str, List[Dict[str, Any]]] = {}

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
                    permalink = post_data.get("permalink", "")

                    if title:
                        item = {
                            "title": title,
                            "description": post_data.get("selftext", ""),
                            "url": f"https://reddit.com{permalink}",
                            "score": post_data.get("score", 0),
                            "num_comments": post_data.get("num_comments", 0),
                        }

                        if include_comments and permalink:
                            logger.info(f"    Fetching comments for: {title[:30]}...")
                            item["comments"] = self._fetch_comments(
                                permalink, limit=comments_limit
                            )

                        items.append(item)

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
        logger.info(f"Social scraping done. Total posts: {total}")
        return results

    def _fetch_comments(self, permalink: str, limit: int = 5) -> List[str]:
        """Fetch top comments for a specific post using the post's JSON endpoint."""
        url = f"https://www.reddit.com{permalink}.json?limit={limit}&sort=top"
        try:
            response = requests.get(url, headers=self.HEADERS, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            # Reddit post JSON returns a list: [post_data, comments_data]
            if isinstance(data, list) and len(data) > 1:
                comments_list = data[1].get("data", {}).get("children", [])

                results = []
                for comment in comments_list:
                    if comment.get("kind") == "t1":  # t1 is the kind for comments
                        body = comment.get("data", {}).get("body")
                        if body:
                            results.append(body.strip())
                return results
            return []
        except Exception as e:
            logger.warning(f"    Error fetching comments: {e}")
            return []
