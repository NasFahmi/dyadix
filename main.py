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
    from features.technical.daily_bias import get_daily_bias
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


def test_trend_engine():
    from service.market.market_service import MarketService
    from features.technical.trend import calculate_trend_features
    import json
    import pandas as pd

    print("\n" + "=" * 60)
    print(" TEST: Trend Engine Calculation")
    print("=" * 60)

    try:
        market_svc = MarketService()

        for pair in market_svc.pairs:
            print(f"\n[{pair}] Mengambil data untuk H1 (1h)...")
            market_data = market_svc.fetch_single_pair(
                pair=pair,
                timeframes=["1h"],
                limit=250,  # Ambil > 200 agar EMA200 valid
            )

            if (
                "1h" in market_data
                and not market_data["1h"].get("aggregated", pd.DataFrame()).empty
            ):
                h1_data = market_data["1h"]["aggregated"]

                print(
                    f"Berhasil mendapat {len(h1_data)} baris data H1. Kalkulasi Trend..."
                )

                df_with_features, summary = calculate_trend_features(h1_data, "1h")

                print(f"\n--- Hasil Trend {pair} (H1) ---")
                print(json.dumps(summary, indent=2))
            else:
                print(f"Gagal mengambil data 1h untuk {pair}.")

    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error pada saat testing Trend Engine: {e}")


def test_momentum_engine():
    from service.market.market_service import MarketService
    from features.technical.momentum import calculate_momentum_features
    import json
    import pandas as pd

    print("\n" + "=" * 60)
    print(" TEST: Momentum Engine Calculation")
    print("=" * 60)

    try:
        market_svc = MarketService()

        for pair in market_svc.pairs:
            print(f"\n[{pair}] Mengambil data untuk M15 (15m)...")
            market_data = market_svc.fetch_single_pair(
                pair=pair, timeframes=["15m"], limit=100
            )

            if (
                "15m" in market_data
                and not market_data["15m"].get("aggregated", pd.DataFrame()).empty
            ):
                m15_data = market_data["15m"]["aggregated"]

                print(
                    f"Berhasil mendapat {len(m15_data)} baris data M15. Kalkulasi Momentum..."
                )

                df_with_features, summary = calculate_momentum_features(m15_data, "15m")

                print(f"\n--- Hasil Momentum {pair} (M15) ---")
                print(json.dumps(summary, indent=2))
            else:
                print(f"Gagal mengambil data 15m untuk {pair}.")

    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error pada saat testing Momentum Engine: {e}")


def test_volatility_engine():
    from service.market.market_service import MarketService
    from features.technical.volatility import calculate_volatility_features
    import json
    import pandas as pd

    print("\n" + "=" * 60)
    print(" TEST: Volatility Engine Calculation")
    print("=" * 60)

    try:
        market_svc = MarketService()

        for pair in market_svc.pairs:
            print(f"\n[{pair}] Mengambil data untuk M5 (5m)...")
            market_data = market_svc.fetch_single_pair(
                pair=pair, timeframes=["5m"], limit=100
            )

            if (
                "5m" in market_data
                and not market_data["5m"].get("aggregated", pd.DataFrame()).empty
            ):
                m5_data = market_data["5m"]["aggregated"]

                print(
                    f"Berhasil mendapat {len(m5_data)} baris data M5. Kalkulasi Volatility..."
                )

                df_with_features, summary = calculate_volatility_features(m5_data, "5m")

                print(f"\n--- Hasil Volatility {pair} (M5) ---")
                print(json.dumps(summary, indent=2))
            else:
                print(f"Gagal mengambil data 5m untuk {pair}.")

    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error pada saat testing Volatility Engine: {e}")


def test_price_action_engine():
    from service.market.market_service import MarketService
    from features.technical.price_action import calculate_price_action_features
    import json
    import pandas as pd

    print("\n" + "=" * 60)
    print(" TEST: Price Action Engine Calculation")
    print("=" * 60)

    try:
        market_svc = MarketService()

        for pair in market_svc.pairs:
            print(f"\n[{pair}] Mengambil data untuk M5 (5m)...")
            market_data = market_svc.fetch_single_pair(
                pair=pair, timeframes=["5m"], limit=100
            )

            if (
                "5m" in market_data
                and not market_data["5m"].get("aggregated", pd.DataFrame()).empty
            ):
                m5_data = market_data["5m"]["aggregated"]

                print(
                    f"Berhasil mendapat {len(m5_data)} baris data M5. Kalkulasi Price Action..."
                )

                df_with_features, summary = calculate_price_action_features(
                    m5_data, "5m"
                )

                print(f"\n--- Hasil Price Action {pair} (M5) ---")
                print(json.dumps(summary, indent=2))
            else:
                print(f"Gagal mengambil data 5m untuk {pair}.")

    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error pada saat testing Price Action Engine: {e}")


def test_context_builder():
    from service.market.market_service import MarketService
    from features.context_builder import build_technical_context
    import json

    print("\n" + "=" * 60)
    print(" TEST: Context Builder (Aggregation)")
    print("=" * 60)

    try:
        market_svc = MarketService()

        # Tambahkan timeframe '1d' manual agar daily_bias dapat dihitung (tidak null)
        if "1d" not in market_svc.timeframes:
            market_svc.timeframes.append("1d")

        print(
            f"Mengambil data market untuk semua pair (limit 250) untuk TF {market_svc.timeframes}..."
        )
        market_data = market_svc.fetch_ohlcv_all(limit=250)

        print("Membangun technical context...")
        context = build_technical_context(market_data)

        print("\n--- Hasil Technical Context ---")
        print(json.dumps(context, indent=2))

    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error pada saat testing Context Builder: {e}")


def test_correlation():
    from service.market.market_service import MarketService
    from features.correlation.correlation import calculate_correlation
    import json

    print("\n" + "=" * 60)
    print(" TEST: Correlation Calculation")
    print("=" * 60)

    try:
        market_svc = MarketService()

        # Ambil correlation_pairs dari config
        config = market_svc.config.get("trading", {})
        correlation_pairs = config.get("correlation_pairs", [])

        # Filter duplicate (akibat copy_paste bug di config sebelumnya)
        unique_pairs = list(dict.fromkeys(correlation_pairs))

        # Gunakan semua pair yang ada di correlation_pairs config
        test_pairs = unique_pairs
        print(f"Target pairs untuk testing: {test_pairs}")

        # Overwrite pairs yang difetch oleh market_svc secara sementara
        market_svc.pairs = test_pairs

        # Fokus ke timeframe '1h' saja
        market_svc.timeframes = ["1h"]

        print("Mengambil data market (limit 200) khusus 1h...")
        market_data = market_svc.fetch_ohlcv_all(limit=200)

        print("Membangun correlation insight...")
        result = calculate_correlation(market_data, timeframe="1h", lookback=120)

        print("\n--- Hasil Correlation Insight ---")
        print(json.dumps(result, indent=2))

    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error pada saat testing Correlation: {e}")


def test_derivatives_engine():
    from features.derivatives.derivatives import calculate_derivatives_features
    import json
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta

    print("\n" + "=" * 60)
    print(" TEST: Derivatives Engine Calculation (Mock Data)")
    print("=" * 60)

    try:
        pair = "BTCUSDT"

        # Buat dummy data untuk 24 jam terakhir (1 data per jam)
        now = datetime.utcnow()
        timestamps = [now - timedelta(hours=i) for i in range(24)][::-1]

        # 1. Mock Funding Rate Data
        # Misal funding rate naik perlahan
        funding_rates = np.linspace(0.00005, 0.00015, 24)
        df_funding = pd.DataFrame(
            {"timestamp": timestamps, "funding_rate": funding_rates}
        )

        # 2. Mock Open Interest Data
        # Misal open interest naik bersama harga (Healthy Uptrend / Longs Increasing)
        open_interests = np.linspace(50000, 60000, 24)
        closes = np.linspace(70000, 72000, 24)

        df_oi = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open_interest": open_interests,
                "oi_change": np.random.normal(0, 1, 24),  # Dummy
                "close": closes,
            }
        )

        derivatives_data = {"funding_rate": df_funding, "open_interest": df_oi}

        print(f"[{pair}] Kalkulasi Derivatives dengan Mock Data...")
        result = calculate_derivatives_features(derivatives_data, pair)

        print(f"\n--- Hasil Derivatives {pair} ---")
        print(json.dumps(result, indent=2))

    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error pada saat testing Derivatives Engine: {e}")


def test_liquidity_engine():
    from service.market.market_service import MarketService
    from features.liquidity.liquidity import calculate_liquidity_features
    import json
    import pandas as pd

    print("\n" + "=" * 60)
    print(" TEST: Liquidity Engine Calculation")
    print("=" * 60)

    try:
        market_svc = MarketService()
        pair = "BTCUSDT"

        print(f"Mengambil data market untuk {pair} (timeframe 15m)...")
        market_data = market_svc.fetch_single_pair(
            pair=pair, timeframes=["15m"], limit=200
        )

        if (
            "15m" in market_data
            and not market_data["15m"].get("aggregated", pd.DataFrame()).empty
        ):
            df_15m = market_data["15m"]["aggregated"]

            # Mock daily_bias untuk mengetes logic PDH/PDL Sweep
            # Set PDH sedikit di bawah highest high fetched data untuk men-simulate sweep
            recent_high = df_15m["high"].max()
            recent_low = df_15m["low"].min()

            mock_daily_bias = {
                "previous_day_high": float(recent_high * 0.999),
                "previous_day_low": float(recent_low * 1.001),
            }

            print(f"[{pair}] Kalkulasi Liquidity dengan Mock PDH/PDL...")
            df_with_features, summary = calculate_liquidity_features(
                df=df_15m, daily_bias=mock_daily_bias, timeframe="15m"
            )

            print(f"\n--- Hasil Liquidity Summary {pair} ---")
            print(json.dumps(summary, indent=2))
        else:
            print(f"Gagal mengambil data 15m untuk {pair}.")

    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error pada saat testing Liquidity Engine: {e}")


def test_sentiment_context_builder():
    from features.sentiment.sentiment_context_builder import build_sentiment_context
    import json

    print("\n" + "=" * 60)
    print(" TEST: Sentiment Context Builder")
    print("=" * 60)

    try:
        print("Starting sentiment context builder test. Ini mungkin memakan waktu beberapa detik karena fetching dari API...")
        context = build_sentiment_context(
            news_limit=3, 
            reddit_limit_per_sub=2, 
            twitter_limit_per_user=2, 
            eco_days_ahead=3
        )

        print("\n--- Hasil Sentiment Context (JSON) ---")
        print(json.dumps(context, indent=2, default=str))

        print("\n--- Summary Sentiment Context ---")
        print(f"News articles: {len(context.get('news', []))}")
        print(f"Reddit subreddits fetched: {len(context.get('social', {}).get('reddit', {}))}")
        print(f"Twitter accounts fetched: {len(context.get('social', {}).get('twitter', {}))}")
        
        fng = context.get('fear_and_greed')
        if fng:
            print(f"Fear & Greed Index: {fng.get('value')} ({fng.get('classification')})")
        else:
            print("Fear & Greed Index: Not available")
            
        print(f"Economic Calendar events: {len(context.get('economic_calendar', []))}")

    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error pada saat testing Sentiment Context Builder: {e}")


def test_sentiment_engine():
    from features.sentiment.sentiment_context_builder import build_sentiment_context
    from features.sentiment.sentiment_engine import SentimentEngine
    import json

    print("\n" + "=" * 60)
    print(" TEST: Sentiment Engine (Aggregation)")
    print("=" * 60)

    try:
        print("Gathering context for sentiment engine...")
        context = build_sentiment_context(
            news_limit=3, 
            reddit_limit_per_sub=1, 
            twitter_limit_per_user=1, 
            eco_days_ahead=3
        )
        
        print("Running SentimentEngine aggregation (Memanggil LLM - mungkin butuh waktu)...")
        result = SentimentEngine.aggregate(context)

        print("\n--- Final Sentiment Analysis Result ---")
        print(json.dumps(result, indent=2, default=str))

    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error pada saat testing Sentiment Engine: {e}")


def main():
    # test_news_scraper()  # Dinonaktifkan sementara untuk fokus test market
    # test_market_service()
    # test_daily_bias()
    # test_trend_engine()
    # test_momentum_engine()
    # test_volatility_engine()
    # test_price_action_engine()
    # test_context_builder()
    # test_correlation()
    # test_derivatives_engine()
    # test_liquidity_engine()
    # test_sentiment_context_builder()
    test_sentiment_engine()
    print("\nAll tests completed!")


if __name__ == "__main__":
    import pandas as pd  # Ensure pandas is imported for empty check in test_daily_bias

    main()
