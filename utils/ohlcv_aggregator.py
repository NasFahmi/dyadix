"""
utils/ohlcv_aggregator.py

Modul untuk mengagregasi OHLCV dari Binance Futures dan Bybit Futures.
Mendukung dua metode: simple_average dan volume_weighted (rekomendasi untuk MVP).
"""

import pandas as pd
from typing import Dict, Literal
import logging

logger = logging.getLogger(__name__)


class OHLCVAggregator:
    """
    Class untuk mengagregasi OHLCV dari dua exchange (Binance & Bybit).
    """

    @staticmethod
    def aggregate(
        df_binance: pd.DataFrame,
        df_bybit: pd.DataFrame,
        method: Literal["simple_average", "volume_weighted"] = "volume_weighted",
        align_method: Literal["inner", "outer"] = "inner",
    ) -> pd.DataFrame:
        """
        Aggregate OHLCV dari Binance dan Bybit.

        Parameters:
        -----------
        df_binance : pd.DataFrame
            DataFrame OHLCV dari Binance (kolom: open, high, low, close, volume)
        df_bybit : pd.DataFrame
            DataFrame OHLCV dari Bybit
        method : str
            Metode agregasi: 'simple_average' atau 'volume_weighted' (default)
        align_method : str
            Cara align timestamp: 'inner' (hanya timestamp sama) atau 'outer'

        Returns:
        --------
        pd.DataFrame : OHLCV agregat dengan kolom tambahan
        """
        if df_binance.empty or df_bybit.empty:
            logger.warning(
                "Salah satu DataFrame kosong. Mengembalikan DataFrame kosong."
            )
            return pd.DataFrame()

        # Copy untuk menghindari modifying original
        df_b = df_binance.copy()
        df_y = df_bybit.copy()

        # Pastikan index bertipe datetime
        if not isinstance(df_b.index, pd.DatetimeIndex):
            df_b.index = pd.to_datetime(df_b.index)
        if not isinstance(df_y.index, pd.DatetimeIndex):
            df_y.index = pd.to_datetime(df_y.index)

        # Align timestamp
        if align_method == "inner":
            common_index = df_b.index.intersection(df_y.index)
            if len(common_index) == 0:
                logger.error("Tidak ada timestamp yang sama antara Binance dan Bybit.")
                return pd.DataFrame()
            df_b = df_b.loc[common_index]
            df_y = df_y.loc[common_index]
        else:
            # Outer join (jarang dipakai)
            df_b, df_y = df_b.align(df_y, join="outer", axis=0)
            df_b = df_b.fillna(method="ffill").fillna(method="bfill")
            df_y = df_y.fillna(method="ffill").fillna(method="bfill")

        # Buat DataFrame agregat
        aggregated = pd.DataFrame(index=df_b.index)

        if method == "volume_weighted":
            # Hitung total volume
            total_vol = df_b["volume"] + df_y["volume"]
            total_vol = total_vol.replace(0, 1)  # hindari division by zero

            aggregated["open"] = (
                df_b["open"] * df_b["volume"] + df_y["open"] * df_y["volume"]
            ) / total_vol
            aggregated["high"] = (
                df_b["high"] * df_b["volume"] + df_y["high"] * df_y["volume"]
            ) / total_vol
            aggregated["low"] = (
                df_b["low"] * df_b["volume"] + df_y["low"] * df_y["volume"]
            ) / total_vol
            aggregated["close"] = (
                df_b["close"] * df_b["volume"] + df_y["close"] * df_y["volume"]
            ) / total_vol

            aggregated["volume"] = df_b["volume"] + df_y["volume"]

        elif method == "simple_average":
            aggregated["open"] = (df_b["open"] + df_y["open"]) / 2
            aggregated["high"] = (df_b["high"] + df_y["high"]) / 2
            aggregated["low"] = (df_b["low"] + df_y["low"]) / 2
            aggregated["close"] = (df_b["close"] + df_y["close"]) / 2
            aggregated["volume"] = df_b["volume"] + df_y["volume"]

        else:
            raise ValueError(
                "Method hanya mendukung 'simple_average' atau 'volume_weighted'"
            )

        # Tambahkan kolom metadata (sangat berguna untuk debugging & analisis)
        aggregated["volume_binance"] = df_b["volume"]
        aggregated["volume_bybit"] = df_y["volume"]
        aggregated["volume_ratio_binance"] = df_b["volume"] / (
            df_b["volume"] + df_y["volume"]
        )
        aggregated["agg_method"] = method

        # Round ke harga yang masuk akal (crypto biasanya 2-8 desimal)
        price_cols = ["open", "high", "low", "close"]
        for col in price_cols:
            aggregated[col] = aggregated[col].round(8)

        aggregated["volume"] = aggregated["volume"].round(4)

        logger.info(
            f"OHLCV aggregated successfully using {method} method. "
            f"Rows: {len(aggregated)} | Time range: {aggregated.index[0]} → {aggregated.index[-1]}"
        )

        return aggregated

    @staticmethod
    def aggregate_multi_tf(
        binance_data: Dict[str, pd.DataFrame],
        bybit_data: Dict[str, pd.DataFrame],
        method: Literal["simple_average", "volume_weighted"] = "volume_weighted",
    ) -> Dict[str, pd.DataFrame]:
        """
        Aggregate multiple timeframes sekaligus.

        Contoh input:
            binance_data = {"5m": df5m, "15m": df15m, "1h": df1h}
        """
        aggregated = {}

        for tf in binance_data.keys():
            if tf in bybit_data:
                try:
                    agg_df = OHLCVAggregator.aggregate(
                        binance_data[tf], bybit_data[tf], method=method
                    )
                    aggregated[tf] = agg_df
                except Exception as e:
                    logger.error(f"Failed to aggregate {tf}: {e}")
                    aggregated[tf] = pd.DataFrame()  # fallback kosong

        return aggregated


# Fungsi helper sederhana (untuk kemudahan import)
def aggregate_ohlcv(
    df_binance: pd.DataFrame,
    df_bybit: pd.DataFrame,
    method: Literal["simple_average", "volume_weighted"] = "volume_weighted",
) -> pd.DataFrame:
    """Helper function untuk dipanggil langsung"""
    return OHLCVAggregator.aggregate(df_binance, df_bybit, method=method)
