"""
service/market/binance/binance_derivatives.py

Fetch real derivatives data dari Binance Futures API:
- Funding Rate History (GET /fapi/v1/fundingRate)
- Open Interest (GET /fapi/v1/openInterest)

Rate limit aman:
- Funding Rate: 500 requests per 5 minutes (shared limit)
- Open Interest: Weight 1 per request (budget 6,000/minute)

Dengan 5 pairs × (1 FR + 1 OI) per cycle, kita hanya pakai ~10 requests per cycle.
"""

import logging
import pandas as pd
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class BinanceDerivativesService:
    """
    Service untuk fetch funding rate dan open interest dari Binance Futures.
    Menggunakan ccxt yang sudah dikonfigurasi di BinanceService.
    """

    def __init__(self):
        from service.market.binance.binance_service import BinanceService

        self._binance = BinanceService()
        # Pastikan kita pakai mode futures
        self._binance.exchange.options["defaultType"] = "future"

    def fetch_funding_rate(
        self, symbol: str, limit: int = 24
    ) -> pd.DataFrame:
        """
        Fetch funding rate history untuk satu pair.

        Parameters:
            symbol: e.g. "BTCUSDT" (akan dikonversi ke "BTC/USDT:USDT")
            limit: jumlah data yang diambil (default 24 = ~24 jam terakhir di 8h interval)

        Returns:
            DataFrame dengan kolom: timestamp, funding_rate
        """
        try:
            ccxt_symbol = self._to_ccxt_futures_symbol(symbol)

            # ccxt method: fetchFundingRateHistory
            data = self._binance.exchange.fetch_funding_rate_history(
                symbol=ccxt_symbol, limit=limit
            )

            if not data:
                logger.warning(f"No funding rate data for {symbol}")
                return pd.DataFrame()

            rows = []
            for entry in data:
                rows.append(
                    {
                        "timestamp": pd.to_datetime(
                            entry.get("timestamp"), unit="ms"
                        ),
                        "funding_rate": float(entry.get("fundingRate", 0)),
                    }
                )

            df = pd.DataFrame(rows)
            logger.debug(
                f"Fetched {len(df)} funding rate entries for {symbol}"
            )
            return df

        except Exception as e:
            logger.error(f"Error fetching funding rate for {symbol}: {e}")
            return pd.DataFrame()

    def fetch_open_interest(self, symbol: str) -> pd.DataFrame:
        """
        Fetch current open interest untuk satu pair.

        Note: Binance hanya memberikan data OI saat ini (bukan historis).
        Untuk historis, kita accumulate sendiri via cache di DataManager.

        Parameters:
            symbol: e.g. "BTCUSDT"

        Returns:
            DataFrame dengan satu baris: timestamp, open_interest
        """
        try:
            ccxt_symbol = self._to_ccxt_futures_symbol(symbol)

            # ccxt fetchOpenInterest returns current OI
            oi_data = self._binance.exchange.fetch_open_interest(
                symbol=ccxt_symbol
            )

            if not oi_data:
                logger.warning(f"No open interest data for {symbol}")
                return pd.DataFrame()

            oi_value = float(
                oi_data.get("openInterestAmount", 0)
                or oi_data.get("openInterest", 0)
            )

            df = pd.DataFrame(
                [
                    {
                        "timestamp": pd.to_datetime(
                            oi_data.get("timestamp", datetime.utcnow().timestamp() * 1000),
                            unit="ms",
                        ),
                        "open_interest": oi_value,
                    }
                ]
            )

            logger.debug(
                f"Fetched OI for {symbol}: {oi_value:,.0f}"
            )
            return df

        except Exception as e:
            logger.error(f"Error fetching open interest for {symbol}: {e}")
            return pd.DataFrame()

    def fetch_all_derivatives(
        self, pairs: list, funding_limit: int = 24
    ) -> Dict[str, Dict]:
        """
        Fetch funding rate + open interest untuk semua pairs.

        Returns:
            {
                "BTCUSDT": {
                    "funding_rate": DataFrame,
                    "open_interest": DataFrame,
                },
                ...
            }
        """
        result = {}

        for pair in pairs:
            try:
                df_funding = self.fetch_funding_rate(pair, limit=funding_limit)
                df_oi = self.fetch_open_interest(pair)

                result[pair] = {
                    "funding_rate": df_funding,
                    "open_interest": df_oi,
                }

            except Exception as e:
                logger.error(f"Failed to fetch derivatives for {pair}: {e}")
                result[pair] = {
                    "funding_rate": pd.DataFrame(),
                    "open_interest": pd.DataFrame(),
                }

        logger.info(
            f"Derivatives data fetched for {len(result)} pairs"
        )
        return result

    # ─────────────────────────────────────────────────────────────────────
    #  HELPERS
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_ccxt_futures_symbol(symbol: str) -> str:
        """
        Konversi "BTCUSDT" → "BTC/USDT:USDT" (format ccxt futures).
        """
        # Cari posisi 'USDT' di akhir symbol
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            return f"{base}/USDT:USDT"
        elif symbol.endswith("BUSD"):
            base = symbol[:-4]
            return f"{base}/BUSD:BUSD"
        else:
            # Fallback: coba split di posisi yang masuk akal
            return symbol
