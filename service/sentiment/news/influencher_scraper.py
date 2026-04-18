"""
Influencer Content Aggregator (formerly Twitter Scraper)
========================================================
This module aggregates crypto influencer content from free alternative sources:
- RSS blogs / newsletters
- Reddit user posts
"""

import logging
import time
import json
import re
import requests
import feedparser
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class InfluencherScraper:
    """
    Aggregates crypto influencer content from alternative free sources
    (RSS feeds, Reddit posts) to approximate social trend data.
    """

    # RSS feeds of crypto influencers / news blogs
    RSS_FEEDS = {
        "aantonop": "https://aantonop.com/feed/",
        "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "cointelegraph": "https://cointelegraph.com/rss",
        "decrypt": "https://decrypt.co/feed",
        "blockworks": "https://blockworks.co/feed/",
    }

    # Influencer-specific sources
    INFLUENCER_SOURCES = {
        "VitalikButerin": {
            "reddit": "vbuterin",
            "rss": "https://blog.ethereum.org/feed.xml",
        },
        "APompliano": {
            "rss": "https://pomp.substack.com/feed",
        },
        "aantonop": {
            "rss": "https://aantonop.com/feed/",
        },
    }

    HEADERS = {
        "User-Agent": "DyadixBot/1.0 (Crypto Influencer Aggregator)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    def __init__(self, cache_dir: str = "cache/influencers", cache_ttl: int = 1800):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = cache_ttl  # seconds

    def scrape(
        self,
        usernames: Optional[List[str]] = None,
        limit_per_user: int = 5,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch crypto influencer content from alternative sources.

        Args:
            usernames: List of influencer handles.
            limit_per_user: Max posts per user.

        Returns:
            Dict mapping username -> list of post dicts.
        """
        if usernames is None:
            usernames = list(self.INFLUENCER_SOURCES.keys()) + list(self.RSS_FEEDS.keys())
            # deduplicate while preserving order
            seen = set()
            usernames = [u for u in usernames if not (u in seen or seen.add(u))]

        results: Dict[str, List[Dict[str, Any]]] = {}

        for username in usernames:
            username = username.lstrip("@")

            # Check cache
            cache_path = self.cache_dir / f"{username}.json"
            if self._is_cache_valid(cache_path):
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        results[username] = json.load(f)[:limit_per_user]
                    logger.info(f"Cache hit for {username}")
                    continue
                except Exception:
                    pass

            posts: List[Dict[str, Any]] = []

            # Try influencer-specific sources
            if username in self.INFLUENCER_SOURCES:
                info = self.INFLUENCER_SOURCES[username]
                if "rss" in info:
                    posts.extend(self._fetch_rss(username, info["rss"]))
                if "reddit" in info:
                    posts.extend(self._fetch_reddit_user(info["reddit"]))

            # Try general RSS feeds
            if username in self.RSS_FEEDS and not posts:
                posts.extend(self._fetch_rss(username, self.RSS_FEEDS[username]))

            posts = posts[:limit_per_user]
            results[username] = posts

            # Cache
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(posts, f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to cache {username}: {e}")

            time.sleep(1)  # rate limit

        total = sum(len(p) for p in results.values())
        logger.info(f"Fetched {total} posts from {len(results)} sources")
        return results

    def _fetch_rss(self, username: str, rss_url: str) -> List[Dict[str, Any]]:
        """Fetch content from an RSS feed."""
        try:
            response = requests.get(rss_url, headers=self.HEADERS, timeout=15)
            if response.status_code != 200:
                logger.warning(f"RSS {rss_url} returned {response.status_code}")
                return []

            feed = feedparser.parse(response.content)
            posts = []

            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                summary = self._clean_html(entry.get("summary", entry.get("description", "")))

                if not title:
                    continue

                posts.append({
                    "text": f"{title}: {summary[:200]}" if summary else title,
                    "username": username,
                    "published": entry.get("published", entry.get("updated", "")),
                    "source": "RSS",
                    "url": entry.get("link", ""),
                })

            logger.info(f"Fetched {len(posts)} RSS posts for {username}")
            return posts

        except Exception as e:
            logger.warning(f"Error fetching RSS for {username}: {e}")
            return []

    def _fetch_reddit_user(self, reddit_username: str) -> List[Dict[str, Any]]:
        """Fetch recent Reddit posts from a user."""
        try:
            url = f"https://www.reddit.com/user/{reddit_username}/submitted.json?limit=5"
            response = requests.get(url, headers=self.HEADERS, timeout=10)

            if response.status_code != 200:
                return []

            data = response.json()
            posts = []

            for post in data.get("data", {}).get("children", []):
                post_data = post.get("data", {})
                title = post_data.get("title", "")
                if title:
                    posts.append({
                        "text": title,
                        "username": reddit_username,
                        "published": datetime.fromtimestamp(
                            post_data.get("created_utc", 0), tz=timezone.utc
                        ).isoformat(),
                        "source": "Reddit",
                        "url": f"https://reddit.com{post_data.get('permalink', '')}",
                    })

            logger.info(f"Fetched {len(posts)} Reddit posts for u/{reddit_username}")
            return posts

        except Exception as e:
            logger.warning(f"Error fetching Reddit for u/{reddit_username}: {e}")
            return []

    def _is_cache_valid(self, path: Path) -> bool:
        if not path.exists():
            return False
        return (time.time() - path.stat().st_mtime) < self.cache_ttl

    @staticmethod
    def _clean_html(text: str) -> str:
        """Remove HTML tags from text."""
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        return " ".join(text.split())[:300]
