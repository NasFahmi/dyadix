"""
Enhanced News Scraper
=====================
Fetches crypto news from multiple RSS sources with:
- Retry logic and rate limiting
- File-based caching with TTL
- Article deduplication
- Source performance tracking
"""

import logging
import hashlib
import json
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict

import requests
import feedparser
import yfinance as yf
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class EnhancedCache:
    """File-based cache with TTL."""

    def __init__(self, cache_dir: str, ttl_minutes: int = 30):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_minutes = ttl_minutes
        self.hits = 0
        self.misses = 0

    def _get_cache_file(self, key: str) -> Path:
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{key_hash}.json"

    def get(self, key: str) -> Optional[Any]:
        cache_file = self._get_cache_file(key)
        if not cache_file.exists():
            self.misses += 1
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            cached_time = datetime.fromisoformat(data["timestamp"])
            if datetime.now() - cached_time < timedelta(minutes=self.ttl_minutes):
                self.hits += 1
                return data["content"]
            else:
                cache_file.unlink()
                self.misses += 1
                return None
        except Exception:
            self.misses += 1
            return None

    def set(self, key: str, content: Any):
        cache_file = self._get_cache_file(key)
        try:
            data = {
                "key": key,
                "content": content,
                "timestamp": datetime.now().isoformat(),
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not cache {key}: {e}")

    def get_stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": (self.hits / total * 100) if total > 0 else 0,
        }


class ResilientHTTPSession:
    """HTTP session with automatic retries and domain-level rate limiting."""

    def __init__(self, max_retries: int = 3, backoff_factor: float = 0.5):
        self.session = requests.Session()

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(
            {"User-Agent": "DyadixBot/1.0 (Crypto News Aggregator)"}
        )

        self.last_request_time: Dict[str, float] = defaultdict(float)
        self.min_interval = 1.0

    def get(self, url: str, timeout: int = 10, **kwargs) -> requests.Response:
        domain = re.match(r"https?://([^/]+)", url)
        domain_key = domain.group(1) if domain else "unknown"

        elapsed = time.time() - self.last_request_time[domain_key]
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        response = self.session.get(url, timeout=timeout, **kwargs)
        self.last_request_time[domain_key] = time.time()
        return response


class EnhancedNewsScraper:
    """Fetches crypto news from multiple RSS sources."""

    RSS_SOURCES = {
        # "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "cointelegraph": "https://cointelegraph.com/rss",
        "decrypt": "https://decrypt.co/feed",
        "cryptoslate": "https://cryptoslate.com/feed/",
        "blockworks": "https://blockworks.co/feed/",
        "bitcoinmagazine": "https://bitcoinmagazine.com/.rss/full/",
        "cryptonews": "https://cryptonews.com/news/feed/",
    }

    def __init__(self, cache_dir: str = "cache/news", cache_ttl: int = 30):
        self.cache = EnhancedCache(cache_dir, ttl_minutes=cache_ttl)
        self.http = ResilientHTTPSession()
        self.source_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"attempts": 0, "successes": 0, "failures": 0, "total_articles": 0}
        )

    def fetch_crypto_news(
        self,
        limit: int = 50,
        min_sources: int = 3,
        deduplicate: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Fetch crypto news from multiple RSS sources.

        Args:
            limit: Max articles to return.
            min_sources: Minimum successful sources required.
            deduplicate: Remove duplicate articles by title.

        Returns:
            List of article dicts sorted by published date (newest first).
        """
        logger.info(f"Fetching crypto news (limit={limit})")

        all_articles: List[Dict[str, Any]] = []
        successful_sources = 0

        for source_name, url in self.RSS_SOURCES.items():
            try:
                articles = self._fetch_from_rss(source_name, url, max_articles=10)
                if articles:
                    all_articles.extend(articles)
                    successful_sources += 1
                    logger.info(f"  {source_name}: {len(articles)} articles")
                else:
                    logger.warning(f"  {source_name}: no articles")
            except Exception as e:
                logger.warning(f"  {source_name} failed: {e}")

            if len(all_articles) >= limit and successful_sources >= min_sources:
                break

        # Fetch from Yahoo Finance
        try:
            yf_articles = self._fetch_from_yahoo_finance("BTC-USD", max_articles=10)
            if yf_articles:
                all_articles.extend(yf_articles)
                successful_sources += 1
                logger.info(f"  yahoo_finance: {len(yf_articles)} articles")
        except Exception as e:
            logger.warning(f"  yahoo_finance failed: {e}")

        if deduplicate:
            all_articles = self._deduplicate(all_articles)

        all_articles.sort(key=lambda x: x.get("published", ""), reverse=True)
        all_articles = all_articles[:limit]

        logger.info(
            f"Total: {len(all_articles)} articles from {successful_sources} sources"
        )
        return all_articles

    def _fetch_from_rss(
        self, source_name: str, url: str, max_articles: int = 10
    ) -> List[Dict[str, Any]]:
        self.source_stats[source_name]["attempts"] += 1

        cached = self.cache.get(f"rss_{source_name}")
        if cached:
            self.source_stats[source_name]["successes"] += 1
            return cached

        try:
            feed = feedparser.parse(url)
            articles = []

            for entry in feed.entries[:max_articles]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                if not title or not link:
                    continue

                articles.append(
                    {
                        "title": title,
                        "link": link,
                        "published": entry.get("published", entry.get("updated", "")),
                        "summary": self._clean_html(
                            entry.get("summary", entry.get("description", ""))
                        ),
                        "source": source_name,
                        "fetched_at": datetime.now().isoformat(),
                    }
                )

            if articles:
                self.cache.set(f"rss_{source_name}", articles)
                self.source_stats[source_name]["successes"] += 1
                self.source_stats[source_name]["total_articles"] += len(articles)
            else:
                self.source_stats[source_name]["failures"] += 1

            return articles

        except Exception as e:
            logger.warning(f"Error fetching {source_name}: {e}")
            self.source_stats[source_name]["failures"] += 1
            return []

    def _fetch_from_yahoo_finance(
        self, ticker_symbol: str, max_articles: int = 10
    ) -> List[Dict[str, Any]]:
        source_name = "yahoo_finance"
        self.source_stats[source_name]["attempts"] += 1

        cached = self.cache.get(f"yf_{ticker_symbol}")
        if cached:
            self.source_stats[source_name]["successes"] += 1
            return cached

        try:
            # Biarkan yfinance menggunakan internal curl_cffi session mereka sendiri
            ticker = yf.Ticker(ticker_symbol)
            news = ticker.news
            articles = []

            for item in news[:max_articles]:
                content = item.get("content", {})
                title = content.get("title", "").strip()
                link = content.get("canonicalUrl", {}).get("url", "")
                if not title or not link:
                    continue

                pub_date_raw = content.get("pubDate")
                pub_date_iso = ""
                if isinstance(pub_date_raw, str):
                    try:
                        dt = datetime.fromisoformat(pub_date_raw.replace("Z", "+00:00"))
                        pub_date_iso = dt.isoformat()
                    except ValueError:
                        pub_date_iso = pub_date_raw
                elif isinstance(pub_date_raw, (int, float)):
                    pub_date_iso = datetime.fromtimestamp(
                        pub_date_raw / 1000
                    ).isoformat()

                articles.append(
                    {
                        "title": title,
                        "link": link,
                        "published": pub_date_iso,
                        "summary": self._clean_html(content.get("summary", "")),
                        "source": source_name,
                        "fetched_at": datetime.now().isoformat(),
                    }
                )

            if articles:
                self.cache.set(f"yf_{ticker_symbol}", articles)
                self.source_stats[source_name]["successes"] += 1
                self.source_stats[source_name]["total_articles"] += len(articles)
            else:
                self.source_stats[source_name]["failures"] += 1

            return articles

        except Exception as e:
            logger.warning(f"Error fetching Yahoo Finance ({ticker_symbol}): {e}")
            self.source_stats[source_name]["failures"] += 1
            return []

    def _deduplicate(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique = []
        seen: Set[str] = set()
        for article in articles:
            normalized = re.sub(r"[^\w\s]", "", article["title"].lower())
            h = hashlib.sha256(normalized.encode()).hexdigest()[:16]
            if h not in seen:
                seen.add(h)
                unique.append(article)
        return unique

    @staticmethod
    def _clean_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        return " ".join(text.split())[:500]

    def get_source_stats(self) -> Dict[str, Any]:
        return dict(self.source_stats)
