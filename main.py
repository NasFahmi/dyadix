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


def test_market_service():
    from service.market.market_service import MarketService

    print("\n" + "=" * 60)
    print(" TEST: Market Service (Fetch & Save Raw Data)")
    print("=" * 60)

    try:
        # Initialize MarketService
        market_svc = MarketService()

        # Fetch data menggunakan properties dari settings.yml
        print("Mulai mengambil data (limit 100 untuk testing)...")
        results = market_svc.fetch_ohlcv_all(limit=100)

        # Print info
        for pair in results:
            print(f"\nPair: {pair}")
            for tf, data in results[pair].items():
                if not data["aggregated"].empty:
                    print(f"  - [{tf}] Aggregated Data Rows: {len(data['aggregated'])}")
                else:
                    print(f"  - [{tf}] Gagal ambil data.")

        # Save raw data
        base_path = "data/raw/market"
        print(f"\nMenyimpan data ke: {base_path} ...")
        market_svc.save_raw_data(results, base_path=base_path)

        print("Data berhasil disimpan! Cek folder:", base_path)

    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error pada saat testing MarketService: {e}")


def test_daily_bias():
    from service.market.market_service import MarketService
    from features.daily_bias import get_daily_bias
    import json

    print("\n" + "=" * 60)
    print(" TEST: Daily Bias Calculation")
    print("=" * 60)

    try:
        # Initialize MarketService
        market_svc = MarketService()
        
        # Iterasi mengambil seluruh pair dari konfigurasi settings.yml
        for pair in market_svc.pairs:
            print(f"\n[{pair}] Mengambil data daily (1d)...")
            market_data = market_svc.fetch_single_pair(
                pair=pair, timeframes=["1d"], limit=10
            )

            if (
                "1d" in market_data
                and not market_data["1d"].get("aggregated", pd.DataFrame()).empty
            ):
                daily_data = market_data["1d"]["aggregated"]

                print(
                    f"Berhasil mendapat {len(daily_data)} hari data. Kalkulasi Daily Bias..."
                )
                # Panggil fungsi daily bias
                bias_result = get_daily_bias(daily_data, pair)

                print(f"\n--- Hasil Daily Bias ({pair}) ---")
                print(json.dumps(bias_result, indent=2))
            else:
                print(f"Gagal mengambil data 1d untuk {pair}.")

    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error pada saat testing Daily Bias: {e}")


def main():
    # test_news_scraper() # Dinonaktifkan sementara untuk fokus test market
    # test_market_service()
    test_daily_bias()
    print("\nAll tests completed!")


if __name__ == "__main__":
    import pandas as pd  # Ensure pandas is imported for empty check in test_daily_bias

    main()
