import logging
from service.sentiment.news.enhanced_news_scraper import EnhancedNewsScraper
from service.sentiment.news.reddit_scraper import RedditScraper
from service.sentiment.news.twitter_scraper import TwitterScraper

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


def test_news_scraper():
    print("\n" + "=" * 60)
    print("📰 TEST: Enhanced News Scraper")
    print("=" * 60)
    scraper = EnhancedNewsScraper()
    articles = scraper.fetch_crypto_news(limit=20)
    print(f"Fetched {len(articles)} articles")
    for i, a in enumerate(articles, 1):
        print(f"\nArticle {i}:")
        print(f"  Title: {a.get('title')}")
        print(f"  Source: {a.get('source')}")
        print(f"  Published: {a.get('published')}")
        print(f"  Link: {a.get('link')}")
        print(f"  Summary: {a.get('summary')}")
    stats = scraper.get_source_stats()
    print(f"\nSource stats: {len(stats)} sources tried")


# def test_reddit_scraper():
#     print("\n" + "=" * 60)
#     print("🤖 TEST: Reddit Scraper")
#     print("=" * 60)
#     scraper = RedditScraper()
#     results = scraper.scrape(subreddits=["bitcoin", "CryptoCurrency"], limit_per_subreddit=3)
#     for sub, posts in results.items():
#         print(f"\n  /r/{sub} ({len(posts)} posts):")
#         for p in posts:
#             print(f"    - {p['title'][:80]}")


# def test_twitter_scraper():
#     print("\n" + "=" * 60)
#     print("🐦 TEST: Twitter/Influencer Scraper")
#     print("=" * 60)
#     scraper = TwitterScraper()
#     results = scraper.scrape(usernames=["cointelegraph", "VitalikButerin"], limit_per_user=3)
#     for user, posts in results.items():
#         print(f"\n  @{user} ({len(posts)} posts):")
#         for p in posts:
#             print(f"    - [{p['source']}] {p['text'][:80]}")


def main():
    test_news_scraper()
    # test_reddit_scraper()
    # test_twitter_scraper()
    print("\n✅ All tests completed!")


if __name__ == "__main__":
    main()
