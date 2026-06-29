"""
service/market/screening/market_collector.py

Mengumpulkan metrik pasar dari Hyperliquid DEX untuk seluruh universe (200+ pair)
menggunakan endpoint batch metaAndAssetCtxs (1 HTTP Request, 0 Rate Limit Risk).
"""

import logging
from typing import List, Dict, Any
from datetime import datetime, timezone

from service.exchange.hyperliquid_client import HyperliquidClient

logger = logging.getLogger(__name__)


class MarketCollector:
    """
    Bertanggung jawab untuk mengambil data mentah seluruh market Hyperliquid.
    """

    def __init__(self, client: HyperliquidClient = None):
        self.client = client or HyperliquidClient()

    def collect_all_market_metrics(self) -> List[Dict[str, Any]]:
        """
        Mengambil metadata dan context seluruh market Hyperliquid dalam 1 request batch.
        Returns list of dict berisi metrik dasar per symbol.
        """
        logger.info("Collecting market metrics for all Hyperliquid perpetual pairs...")
        try:
            res = self.client.info.meta_and_asset_ctxs()
            if not isinstance(res, list) or len(res) < 2:
                logger.error(f"Unexpected response structure from meta_and_asset_ctxs: {type(res)}")
                return []

            meta, asset_ctxs = res[0], res[1]
            universe = meta.get("universe", [])
            
            if len(universe) != len(asset_ctxs):
                logger.warning(
                    f"Mismatch between universe length ({len(universe)}) and asset_ctxs length ({len(asset_ctxs)})"
                )

            collected_metrics = []
            now_str = datetime.now(timezone.utc).isoformat()

            for idx, symbol_info in enumerate(universe):
                symbol_name = symbol_info.get("name")
                if not symbol_name or idx >= len(asset_ctxs):
                    continue

                ctx = asset_ctxs[idx]

                try:
                    mark_px = float(ctx.get("markPx", 0.0))
                    prev_day_px = float(ctx.get("prevDayPx", 0.0))
                    volume_24h = float(ctx.get("dayNtlVlm", 0.0))
                    funding_rate = float(ctx.get("funding", 0.0))
                    open_interest_coin = float(ctx.get("openInterest", 0.0))
                    open_interest_usd = open_interest_coin * mark_px

                    # Calculate 24h price change and volatility proxy
                    price_change_pct = 0.0
                    volatility_24h_pct = 0.0
                    if prev_day_px > 0:
                        price_change_pct = ((mark_px - prev_day_px) / prev_day_px) * 100.0
                        volatility_24h_pct = (abs(mark_px - prev_day_px) / prev_day_px) * 100.0

                    metric_entry = {
                        "symbol": symbol_name,
                        "price": mark_px,
                        "prev_day_price": prev_day_px,
                        "price_change_24h_pct": round(price_change_pct, 4),
                        "volatility_24h_pct": round(volatility_24h_pct, 4),
                        "volume_24h": round(volume_24h, 2),
                        "open_interest_coin": round(open_interest_coin, 4),
                        "open_interest_usd": round(open_interest_usd, 2),
                        "funding_rate": funding_rate,
                        "sz_decimals": int(symbol_info.get("szDecimals", 3)),
                        "max_leverage": int(symbol_info.get("maxLeverage", 50)),
                        "collected_at": now_str,
                    }
                    collected_metrics.append(metric_entry)

                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse context for symbol {symbol_name}: {e}")
                    continue

            logger.info(f"Successfully collected metrics for {len(collected_metrics)} markets.")
            return collected_metrics

        except Exception as e:
            logger.error(f"Failed to collect market metrics: {e}", exc_info=True)
            return []
