"""
service/market/screening/screening_cache.py

Manajemen caching untuk hasil scan universe market Hyperliquid.
Menyimpan data ke file JSON lokal dan memeriksa TTL (Time-To-Live).
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class ScreeningCache:
    """
    Mengelola pencatatan dan pembacaan cache hasil scan universe.
    """

    def __init__(
        self,
        cache_file: str = "cache/screening_universe.json",
        ttl_minutes: float = 5.0,
        ttl_hours: Optional[float] = None,
    ):
        self.cache_file = cache_file
        if ttl_hours is not None:
            self.ttl_minutes = ttl_hours * 60.0
        else:
            self.ttl_minutes = ttl_minutes

    def load(self) -> Optional[List[Dict[str, Any]]]:
        """
        Membaca data cache jika file ada dan belum kadaluarsa.
        Returns List data market jika valid, atau None jika kadaluarsa/tidak ada.
        """
        if not os.path.exists(self.cache_file):
            logger.debug(f"Cache file {self.cache_file} does not exist.")
            return None

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                payload = json.load(f)

            saved_at_str = payload.get("timestamp")
            if not saved_at_str:
                return None

            saved_at = datetime.fromisoformat(saved_at_str)
            now = datetime.now(timezone.utc)

            # Jika saved_at naive timezone, buat utc
            if saved_at.tzinfo is None:
                saved_at = saved_at.replace(tzinfo=timezone.utc)

            age = now - saved_at
            if age > timedelta(minutes=self.ttl_minutes):
                logger.info(f"Screening cache expired (age: {age.total_seconds() / 60.0:.2f} minutes).")
                return None

            data = payload.get("data", [])
            logger.info(f"Loaded {len(data)} items from screening cache (age: {age.total_seconds() / 60.0:.2f} minutes).")
            return data

        except Exception as e:
            logger.warning(f"Failed to read screening cache from {self.cache_file}: {e}")
            return None

    def save(self, data: List[Dict[str, Any]]) -> bool:
        """
        Menyimpan data scan universe ke file cache JSON.
        """
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ttl_minutes": self.ttl_minutes,
                "count": len(data),
                "data": data,
            }
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)

            logger.info(f"Successfully saved {len(data)} items to screening cache ({self.cache_file}).")
            return True
        except Exception as e:
            logger.error(f"Failed to save screening cache to {self.cache_file}: {e}")
            return False

    def is_expired(self) -> bool:
        """Cek apakah cache saat ini sudah kadaluarsa."""
        return self.load() is None
