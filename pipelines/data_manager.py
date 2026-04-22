"""
pipelines/data_manager.py

Cache layer dengan staggered interval fetching.
Setiap jenis data memiliki interval refresh sendiri:
  - M3 & M5 OHLCV : setiap 60 detik
  - M15 OHLCV     : setiap 90 detik
  - H1 OHLCV      : setiap 3 menit
  - Daily OHLCV    : setiap 1 jam
  - Funding Rate   : setiap 60 detik
  - Open Interest  : setiap 2 menit
  - Correlation    : setiap 2 menit
  - Sentiment      : setiap 15 menit

Hanya data yang sudah expired akan di-refetch, sisanya pakai cache.
"""

import time
import logging
import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import datetime

from config.settings import get_config

logger = logging.getLogger(__name__)


class DataManager:
    """
    Mengelola cache data market + sentiment dengan interval refresh berbeda-beda.
    Desain: fetch hanya data yang stale, cache sisanya.
    """

    # Default intervals (bisa di-override dari settings.yml)
    DEFAULT_INTERVALS = {
        "ohlcv_fast": 60,        # M3 & M5: setiap 60 detik
        "ohlcv_m15": 90,         # M15: setiap 90 detik
        "ohlcv_h1": 180,         # H1: setiap 3 menit
        "ohlcv_daily": 3600,     # Daily: setiap 1 jam
        "funding_rate": 60,      # Funding Rate: setiap 60 detik
        "open_interest": 120,    # OI: setiap 2 menit
        "correlation": 120,      # Correlation: setiap 2 menit
        "sentiment": 900,        # Sentiment: setiap 15 menit
    }

    MARKET_DATA_LIMIT = 250  # candle per timeframe

    def __init__(self):
        config = get_config()

        # Load intervals dari config, fallback ke default
        scheduler_config = config.get("scheduler", {})
        config_intervals = scheduler_config.get("intervals", {})
        self.intervals = {**self.DEFAULT_INTERVALS, **config_intervals}

        # Cache storage
        self._cache: Dict[str, Any] = {}
        self._last_updated: Dict[str, float] = {}

        # Services (lazy init)
        self._market_service = None
        self._derivatives_service = None

        # Pairs dari config
        trading_config = config.get("trading", {})
        self.pairs: List[str] = trading_config.get("pairs") or ["BTCUSDT"]
        self.correlation_pairs: List[str] = trading_config.get("correlation_pairs", [])
        self.timeframes: List[str] = trading_config.get("timeframes", ["3m", "5m", "15m", "1h"])

        # Pastikan 1d ada untuk daily bias
        if "1d" not in self.timeframes:
            self.timeframes.append("1d")

        logger.info(
            f"DataManager initialized | "
            f"pairs={self.pairs} | intervals={self.intervals}"
        )

    # ─────────────────────────────────────────────────────────────────────
    #  LAZY SERVICE INIT
    # ─────────────────────────────────────────────────────────────────────

    @property
    def market_service(self):
        if self._market_service is None:
            from service.market.market_service import MarketService
            self._market_service = MarketService()
        return self._market_service

    @property
    def derivatives_service(self):
        if self._derivatives_service is None:
            from service.market.binance.binance_derivatives import BinanceDerivativesService
            self._derivatives_service = BinanceDerivativesService()
        return self._derivatives_service

    # ─────────────────────────────────────────────────────────────────────
    #  CACHE MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────

    def is_stale(self, key: str) -> bool:
        """Cek apakah data sudah expired berdasarkan interval."""
        if key not in self._last_updated:
            return True  # belum pernah fetch
        elapsed = time.time() - self._last_updated[key]
        interval = self.intervals.get(key, 60)
        return elapsed >= interval

    def get_cache(self, key: str) -> Any:
        """Ambil data dari cache."""
        return self._cache.get(key)

    def set_cache(self, key: str, data: Any) -> None:
        """Set data ke cache dan update timestamp."""
        self._cache[key] = data
        self._last_updated[key] = time.time()

    def get_cache_age(self, key: str) -> float:
        """Return umur cache dalam detik. -1 jika belum pernah fetch."""
        if key not in self._last_updated:
            return -1.0
        return time.time() - self._last_updated[key]

    # ─────────────────────────────────────────────────────────────────────
    #  STAGGERED REFRESH
    # ─────────────────────────────────────────────────────────────────────

    def refresh_stale_data(self) -> Dict[str, bool]:
        """
        Cek dan refresh semua data yang sudah expired.
        Return dict {data_key: was_refreshed}.
        """
        refreshed = {}

        # ── OHLCV Fast (M3 & M5) ────────────────────────────────────────
        if self.is_stale("ohlcv_fast"):
            logger.info("🔄 Refreshing M3 & M5 OHLCV...")
            self._fetch_ohlcv_timeframes(["3m", "5m"])
            self.set_cache("ohlcv_fast", True)
            refreshed["ohlcv_fast"] = True
        else:
            refreshed["ohlcv_fast"] = False

        # ── OHLCV M15 ───────────────────────────────────────────────────
        if self.is_stale("ohlcv_m15"):
            logger.info("🔄 Refreshing M15 OHLCV...")
            self._fetch_ohlcv_timeframes(["15m"])
            self.set_cache("ohlcv_m15", True)
            refreshed["ohlcv_m15"] = True
        else:
            refreshed["ohlcv_m15"] = False

        # ── OHLCV H1 ────────────────────────────────────────────────────
        if self.is_stale("ohlcv_h1"):
            logger.info("🔄 Refreshing H1 OHLCV...")
            self._fetch_ohlcv_timeframes(["1h"])
            self.set_cache("ohlcv_h1", True)
            refreshed["ohlcv_h1"] = True
        else:
            refreshed["ohlcv_h1"] = False

        # ── OHLCV Daily ─────────────────────────────────────────────────
        if self.is_stale("ohlcv_daily"):
            logger.info("🔄 Refreshing Daily OHLCV...")
            self._fetch_ohlcv_timeframes(["1d"])
            self.set_cache("ohlcv_daily", True)
            refreshed["ohlcv_daily"] = True
        else:
            refreshed["ohlcv_daily"] = False

        # ── Funding Rate ─────────────────────────────────────────────────
        if self.is_stale("funding_rate"):
            logger.info("🔄 Refreshing Funding Rate...")
            self._fetch_funding_rate()
            refreshed["funding_rate"] = True
        else:
            refreshed["funding_rate"] = False

        # ── Open Interest ────────────────────────────────────────────────
        if self.is_stale("open_interest"):
            logger.info("🔄 Refreshing Open Interest...")
            self._fetch_open_interest()
            refreshed["open_interest"] = True
        else:
            refreshed["open_interest"] = False

        # ── Correlation ──────────────────────────────────────────────────
        if self.is_stale("correlation"):
            logger.info("🔄 Refreshing Correlation...")
            self._fetch_correlation()
            refreshed["correlation"] = True
        else:
            refreshed["correlation"] = False

        # ── Sentiment ────────────────────────────────────────────────────
        if self.is_stale("sentiment"):
            logger.info("🔄 Refreshing Sentiment...")
            self._fetch_sentiment()
            refreshed["sentiment"] = True
        else:
            refreshed["sentiment"] = False

        # Log summary
        refreshed_keys = [k for k, v in refreshed.items() if v]
        if refreshed_keys:
            logger.info(f"📊 Refreshed: {', '.join(refreshed_keys)}")
        else:
            logger.debug("📊 All data still fresh, no refresh needed")

        return refreshed

    # ─────────────────────────────────────────────────────────────────────
    #  GETTERS (untuk LoopScheduler)
    # ─────────────────────────────────────────────────────────────────────

    def get_market_data(self) -> Dict:
        """Return cached market data (OHLCV semua timeframe semua pair)."""
        return self._cache.get("market_data", {})

    def get_derivatives_data(self) -> Dict:
        """Return cached derivatives data per pair."""
        return self._cache.get("derivatives_data", {})

    def get_correlation_data(self) -> Dict:
        """Return cached correlation data."""
        return self._cache.get("correlation_data", {})

    def get_sentiment_result(self) -> Dict:
        """Return cached sentiment result."""
        return self._cache.get("sentiment_result", {})

    def get_status(self) -> Dict:
        """Return status semua cache untuk monitoring."""
        status = {}
        for key in self.intervals:
            age = self.get_cache_age(key)
            interval = self.intervals[key]
            status[key] = {
                "age_seconds": round(age, 1) if age >= 0 else None,
                "interval_seconds": interval,
                "is_stale": self.is_stale(key),
                "next_refresh_in": round(max(0, interval - age), 1)
                if age >= 0
                else 0,
            }
        return status

    # ─────────────────────────────────────────────────────────────────────
    #  PRIVATE FETCH METHODS
    # ─────────────────────────────────────────────────────────────────────

    def _fetch_ohlcv_timeframes(self, timeframes: List[str]) -> None:
        """
        Fetch OHLCV untuk timeframe tertentu saja, merge ke cache.
        Fetch untuk semua pairs (trading + correlation).
        """
        from utils.ohlcv_aggregator import OHLCVAggregator

        market_data = self._cache.get("market_data", {})
        fetch_list = list(set(self.pairs + self.correlation_pairs))

        for pair in fetch_list:
            if pair not in market_data:
                market_data[pair] = {}

            for tf in timeframes:
                if tf not in self.timeframes:
                    continue
                try:
                    df_binance = self.market_service.binance.fetch_ohlcv(
                        symbol=pair, timeframe=tf, limit=self.MARKET_DATA_LIMIT
                    )
                    df_bybit = self.market_service.bybit.fetch_ohlcv(
                        symbol=pair, timeframe=tf, limit=self.MARKET_DATA_LIMIT
                    )
                    df_aggregated = OHLCVAggregator.aggregate(
                        df_binance=df_binance,
                        df_bybit=df_bybit,
                        method="volume_weighted",
                    )

                    market_data[pair][tf] = {
                        "binance": df_binance,
                        "bybit": df_bybit,
                        "aggregated": df_aggregated,
                        "last_updated": datetime.utcnow(),
                    }

                    logger.debug(f"✓ {pair} {tf} refreshed | Rows: {len(df_aggregated)}")

                except Exception as e:
                    logger.error(f"❌ Failed to fetch {pair} {tf}: {e}")

        self._cache["market_data"] = market_data

    def _fetch_funding_rate(self) -> None:
        """Fetch funding rate untuk semua trading pairs."""
        try:
            derivatives_data = self._cache.get("derivatives_data", {})

            for pair in self.pairs:
                df_funding = self.derivatives_service.fetch_funding_rate(pair)
                if pair not in derivatives_data:
                    derivatives_data[pair] = {}
                derivatives_data[pair]["funding_rate"] = df_funding

            self._cache["derivatives_data"] = derivatives_data
            self.set_cache("funding_rate", True)

        except Exception as e:
            logger.error(f"Failed to fetch funding rates: {e}")

    def _fetch_open_interest(self) -> None:
        """
        Fetch current open interest dan accumulate ke historis.
        Karena Binance hanya memberikan OI saat ini, kita kumpulkan
        data point baru dan simpan di cache.
        """
        try:
            derivatives_data = self._cache.get("derivatives_data", {})
            oi_history = self._cache.get("oi_history", {})

            for pair in self.pairs:
                df_oi_now = self.derivatives_service.fetch_open_interest(pair)

                if pair not in derivatives_data:
                    derivatives_data[pair] = {}

                # Accumulate OI history
                if pair not in oi_history:
                    oi_history[pair] = pd.DataFrame()

                if not df_oi_now.empty:
                    oi_history[pair] = pd.concat(
                        [oi_history[pair], df_oi_now], ignore_index=True
                    )
                    # Keep only last 24 entries (≈24 data points)
                    oi_history[pair] = oi_history[pair].tail(24)

                    # Hitung OI change jika ada cukup data
                    if len(oi_history[pair]) >= 2:
                        oi_df = oi_history[pair].copy()
                        oi_df["oi_change"] = oi_df["open_interest"].pct_change() * 100

                        # Tambah close price dari M5 cache jika ada
                        market_data = self._cache.get("market_data", {})
                        df_m5 = (
                            market_data.get(pair, {})
                            .get("5m", {})
                            .get("aggregated", pd.DataFrame())
                        )
                        if not df_m5.empty:
                            oi_df["close"] = df_m5["close"].iloc[-1]

                        derivatives_data[pair]["open_interest"] = oi_df
                    else:
                        derivatives_data[pair]["open_interest"] = oi_history[pair]

            self._cache["derivatives_data"] = derivatives_data
            self._cache["oi_history"] = oi_history
            self.set_cache("open_interest", True)

        except Exception as e:
            logger.error(f"Failed to fetch open interest: {e}")

    def _fetch_correlation(self) -> None:
        """Hitung correlation dari cached market data."""
        try:
            from features.correlation.correlation import calculate_correlation

            market_data = self._cache.get("market_data", {})
            if not market_data:
                logger.warning("No market data for correlation calculation")
                return

            result = calculate_correlation(
                market_data, timeframe="1h", lookback=120
            )

            if result.get("error"):
                logger.warning(f"Correlation skipped: {result['error']}")
                self._cache["correlation_data"] = {}
            else:
                self._cache["correlation_data"] = result

            self.set_cache("correlation", True)

        except Exception as e:
            logger.error(f"Failed to calculate correlation: {e}")

    def _fetch_sentiment(self) -> None:
        """Fetch dan analyze sentiment (news, social, F&G, economic)."""
        try:
            from features.sentiment.sentiment_context_builder import (
                build_sentiment_context,
            )
            from features.sentiment.news_social_analysis import (
                analyze_news_social_with_llm,
            )
            from features.sentiment.sentiment_engine import SentimentEngine

            logger.info("🔄 Building sentiment context (news, social, F&G, eco)...")

            sentiment_ctx = build_sentiment_context(
                news_limit=15,
                reddit_limit_per_sub=5,
                twitter_limit_per_user=5,
                eco_days_ahead=7,
                eco_days_back=1,
            )

            llm_result = analyze_news_social_with_llm(
                news_list=sentiment_ctx.get("news", []),
                twitter_data=sentiment_ctx.get("social", {}).get("twitter", {}),
                reddit_data=sentiment_ctx.get("social", {}).get("reddit", {}),
                fear_greed=sentiment_ctx.get("fear_and_greed"),
            )

            result = SentimentEngine.aggregate(
                llm_result=llm_result,
                fear_greed_data=sentiment_ctx.get("fear_and_greed"),
                economic_data=sentiment_ctx.get("economic_calendar"),
            )

            self._cache["sentiment_result"] = result
            self.set_cache("sentiment", True)

            logger.info(
                f"✅ Sentiment refreshed → {result.get('overall_sentiment')} "
                f"(score {result.get('sentiment_score')})"
            )

        except Exception as e:
            logger.error(f"Failed to refresh sentiment: {e}")
