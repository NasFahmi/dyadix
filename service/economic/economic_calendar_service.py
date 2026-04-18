import requests
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from pathlib import Path
import hashlib
from dataclasses import dataclass
import os


@dataclass
class CacheMetadata:
    """Metadata disimpan bersama data cache untuk validasi"""

    timestamp: str
    created_date: str
    target_week: str
    days_ahead: int
    countries: List[str]
    event_count: int
    cache_duration_hours: float


class EconomicCalendarService:
    """
    Layanan Economic Calendar dengan sistem caching yang robust.

    Features:
    - Auto-expires cache based on time limit (default 6 hours)
    - Auto-refresh when week changes (detects every Monday automatically)
    - Stores metadata to validate cache integrity
    - Supports multi-country filtering
    - Period-based filtering (past + future events)
    """

    # Configuration
    BASE_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    DEFAULT_CACHE_DURATION_HOURS = 6

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        cache_duration_hours: float = DEFAULT_CACHE_DURATION_HOURS,
        force_refresh_if_week_changed: bool = True,
    ):
        """
        Initialize the economic calendar service.

        Args:
            cache_dir: Cache directory (default: 'root_project/cache/economic/')
            cache_duration_hours: How long cache stays valid (default: 6 hours)
            force_refresh_if_week_changed: Force refresh if ISO week changed
        """
        # Get the directory where THIS script is located
        script_path = Path(__file__).resolve()
        root_project_dir = script_path.parent.parent

        # Setup cache path relative to ROOT_PROJECT, not current working directory
        if cache_dir is None:
            # Use absolute path for consistency
            cache_dir = f"{root_project_dir}/cache/economic"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        print(f"[INIT] Using cache directory: {self.cache_dir}")
        try:
            print(
                f"[INIT] Relative path from project root: {self.cache_dir.relative_to(root_project_dir)}"
            )
        except ValueError:
            # Fallback jika cache_dir berada di luar root_project_dir
            print(f"[INIT] Absolute cache path: {self.cache_dir.resolve()}")

        self.cache_duration_hours = cache_duration_hours
        self.force_refresh_if_week_changed = force_refresh_if_week_changed

        print(f"[INIT] Cache duration: {self.cache_duration_hours} hours")

    def _get_iso_week_key(self) -> str:
        """
        Dapatkan key minggu ISO saat ini.

        Returns:
            Format: "YYYY_WXX" e.g., "2026_W16"
        """
        now = datetime.now(timezone.utc)
        year, week, _ = now.isocalendar()
        return f"{year}_W{week:02d}"

    def _get_cache_key(self, days_ahead: int, countries: List[str]) -> str:
        """
        Generate unique hash from parameters for filename uniqueness.
        Prevents different queries from sharing same cache file.

        Returns:
            Short MD5 hash (8 chars)
        """
        params = f"{days_ahead}_{json.dumps(countries)}"
        return hashlib.md5(params.encode()).hexdigest()[:8]

    def _get_cache_path(self, days_ahead: int = 7, countries: List[str] = None) -> Path:
        """Get full path for cache file including week and hash."""
        week_key = self._get_iso_week_key()
        params_hash = self._get_cache_key(days_ahead, countries or [])
        return self.cache_dir / f"calendar_{week_key}_k{params_hash}.json"

    def _load_metadata(self, cache_path: Path) -> Optional[CacheMetadata]:
        """Load and parse metadata from cache file."""
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "metadata" not in data:
                return None

            meta = data["metadata"]
            return CacheMetadata(
                timestamp=meta.get("timestamp", ""),
                created_date=meta.get("date", ""),
                target_week=meta.get("target_week", ""),
                days_ahead=meta.get("days_ahead", 0),
                countries=meta.get("countries", []),
                event_count=meta.get("event_count", 0),
                cache_duration_hours=meta.get("cache_duration_hours", 6.0),
            )
        except Exception as e:
            print(f"[WARNING] Failed to load metadata: {e}")
            return None

    def _is_cache_valid(
        self, cache_path: Path, days_ahead: int, countries: List[str]
    ) -> bool:
        """
        Validasi apakah cache masih bisa digunakan.

        Conditions met if ALL are TRUE:
        1. File exists
        2. Has valid metadata
        3. Time elapsed < cache_duration_hours
        4. Target week matches current week
        5. Query parameters match cached parameters
        """
        if not cache_path.exists():
            print(f"[CACHE MISS] No cache file found")
            return False

        meta = self._load_metadata(cache_path)
        if not meta:
            print("[CACHE ERROR] Corrupt metadata, invalidating cache")
            return False

        # Check: Is this a different query?
        if meta.days_ahead != days_ahead or meta.countries != countries:
            print(f"[CACHE MISMATCH] Parameters differ from cache")
            return False

        # Check: Has week changed?
        if self.force_refresh_if_week_changed:
            if meta.target_week != self._get_iso_week_key():
                print(
                    f"[WEEK CHANGE] Week changed: {meta.target_week} → {self._get_iso_week_key()}"
                )
                return False

        # Check: Is cache expired by time?
        try:
            cache_time = datetime.fromisoformat(meta.timestamp.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            hours_elapsed = (now - cache_time).total_seconds() / 3600

            if hours_elapsed > meta.cache_duration_hours:
                print(
                    f"[EXPIRED] Cache age: {hours_elapsed:.1f}h (> {meta.cache_duration_hours}h)"
                )
                return False

            print(f"[VALID] Cache status: Fresh ({hours_elapsed:.1f}h old)")
            return True

        except Exception as e:
            print(f"[ERROR] Timestamp parsing failed: {e}")
            return False

    def get_high_impact_events(
        self, days_ahead: int = 7, days_back: int = 0, countries: List[str] = None
    ) -> List[Dict]:
        """
        Fetch high-impact economic events.

        Args:
            days_ahead: Events to fetch after today (default: 7)
            days_back: Events to fetch before today (default: 0)
            countries: Country codes like ["USD", "EUR", "GBP"]

        Returns:
            List of event dictionaries sorted by date+time
        """
        if countries is None:
            countries = ["USD"]

        print("\n" + "=" * 60)
        print(f"ECONOMIC CALENDAR REQUEST")
        print(
            f"Params: days_ahead={days_ahead}, days_back={days_back}, countries={countries}"
        )
        print("=" * 60)

        cache_path = self._get_cache_path(days_ahead, countries)

        # Step 1: Try to use cache
        if self._is_cache_valid(cache_path, days_ahead, countries):
            try:
                print("[USE CACHE] Loading from cache...")
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)

                raw_events = cached_data.get("data", [])
                filtered = self._filter_by_period(raw_events, days_ahead, days_back)

                print(f"[OK] Retrieved {len(filtered)} events from cache")
                return filtered

            except Exception as e:
                print(f"[WARN] Cache read failed: {e}")

        # Step 2: Fetch from network if cache unavailable
        print("[FETCH] Network fetch required")
        try:
            response = requests.get(self.BASE_URL, timeout=15)
            response.raise_for_status()
            raw_events = response.json()

            # Process and filter events
            processed = self._process_raw_events(raw_events, countries)
            filtered = self._filter_by_period(processed, days_ahead, days_back)

            # Save to cache
            self._save_to_cache(processed, days_ahead, countries)

            print(f"[OK] Fetched {len(filtered)} high-impact events from API")
            return filtered

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Network request failed: {e}")
            return []
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            return []

    def _process_raw_events(
        self, raw_events: List[Dict], countries: List[str]
    ) -> List[Dict]:
        """Convert raw API response to standardized format."""
        filtered = []

        for event in raw_events:
            # Filter: Only High impact
            if event.get("impact") != "High":
                continue

            # Filter: Specific countries only
            country = event.get("country", "")
            if countries and country not in countries:
                continue

            # Parse datetime
            try:
                parsed_dt = datetime.fromisoformat(event["date"])
            except (ValueError, TypeError) as e:
                continue

            event_date = parsed_dt.date()

            filtered.append(
                {
                    "title": event.get("title", ""),
                    "country": country,
                    "date": str(event_date),
                    "time": parsed_dt.strftime("%H:%M:%S"),
                    "impact": event.get("impact", ""),
                    "forecast": event.get("forecast", ""),
                    "previous": event.get("previous", ""),
                    "timestamp": parsed_dt.isoformat(),
                }
            )

        # Sort by datetime ascending
        filtered.sort(key=lambda x: x["timestamp"])
        return filtered

    def _filter_by_period(
        self, events: List[Dict], days_ahead: int, days_back: int
    ) -> List[Dict]:
        """Filter events to fall within the requested date range."""
        today = datetime.now(timezone.utc).date()
        start_date = today - timedelta(days=days_back)
        cutoff_date = today + timedelta(days=days_ahead)

        filtered = []

        for event in events:
            try:
                event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
                if start_date <= event_date <= cutoff_date:
                    filtered.append(event)
            except Exception:
                continue

        # Re-sort after filtering
        filtered.sort(key=lambda x: x["timestamp"])
        return filtered

    def _save_to_cache(self, events: List[Dict], days_ahead: int, countries: List[str]):
        """Save processed events to cache with metadata."""
        cache_path = self._get_cache_path(days_ahead, countries)

        now = datetime.now(timezone.utc)
        metadata = {
            "timestamp": now.isoformat(),
            "date": now.date().isoformat(),
            "target_week": self._get_iso_week_key(),
            "days_ahead": days_ahead,
            "countries": countries,
            "event_count": len(events),
            "cache_duration_hours": self.cache_duration_hours,
        }

        cache_data = {"metadata": metadata, "data": events}

        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
            print(f"[SAVE] Cache saved: {cache_path.name}")
            print(f"[SAVE] Full path: {cache_path.resolve()}")
        except Exception as e:
            print(f"[ERROR] Failed to save cache: {e}")

    def clear_cache(self) -> int:
        """
        Clear all cache files.

        Returns:
            Number of files deleted
        """
        cache_files = list(self.cache_dir.glob("*.json"))
        deleted = 0

        for f in cache_files:
            try:
                f.unlink()
                deleted += 1
            except Exception as e:
                print(f"[WARN] Failed to delete {f.name}: {e}")

        print(f"[CLEAR] Deleted {deleted} cache file(s)")
        return deleted

    def get_cache_info(self) -> Dict:
        """Get detailed information about current cache status."""
        cache_files = list(self.cache_dir.glob("*.json"))

        info = {
            "cache_dir": str(self.cache_dir),
            "files_count": len(cache_files),
            "max_age_hours": self.cache_duration_hours,
            "current_week": self._get_iso_week_key(),
            "files": [],
        }

        for path in cache_files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                meta = data.get("metadata", {})
                created_at = meta.get("timestamp", "N/A")

                # Calculate age
                try:
                    cache_time = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )
                    age_hours = (
                        datetime.now(timezone.utc) - cache_time
                    ).total_seconds() / 3600
                except:
                    age_hours = -1

                info["files"].append(
                    {
                        "name": path.name,
                        "events": meta.get("event_count", 0),
                        "countries": meta.get("countries", []),
                        "created": created_at,
                        "age_hours": round(age_hours, 1) if age_hours >= 0 else -1,
                        "valid": age_hours >= 0
                        and age_hours <= self.cache_duration_hours,
                        "target_week": meta.get("target_week", ""),
                    }
                )
            except Exception as e:
                info["files"].append({"name": path.name, "error": str(e)})

        return info

    def display_events(
        self, events: List[Dict], max_display: int = 20, show_all: bool = False
    ) -> None:
        """Pretty print events to console."""
        if not events:
            print("No high-impact events found.")
            return

        count = min(len(events), max_display) if not show_all else len(events)

        print("\n" + "=" * 70)
        print(f"HIGH IMPACT ECONOMIC EVENTS ({count}/{len(events)} shown)")
        print("=" * 70)

        for idx, event in enumerate(events[:count], 1):
            print(f"\n{idx}. [{event['date']} {event['time']} UTC]")
            print(f"   └─ Country: {event['country']}")
            print(f"   └─ Event:   {event['title']}")
            print(
                f"   └─ Forecast: {event['forecast'] or 'N/A'} | Previous: {event['previous'] or 'N/A'}"
            )

        if len(events) > max_display and not show_all:
            print(
                f"\n... and {len(events) - max_display} more events. Set show_all=True to display all."
            )

        print("\n" + "-" * 70)


# ============================================================
# MAIN DEMO & TEST
# ============================================================
if __name__ == "__main__":
    print("\n" + "#" * 70)
    print("#" + " " * 18 + "ECONOMIC CALENDAR SERVICE" + " " * 15 + "#")
    print("#" * 70)

    # Create service instance - cache auto-located at root_project/cache/economic/
    service = EconomicCalendarService(
        cache_duration_hours=6,  # Cache expires after 6 hours
        force_refresh_if_week_changed=True,  # Auto-refresh when week changes
    )

    print(f"\n📁 Cache Location: {service.cache_dir}")
    print(f"✅ Absolute Path: {service.cache_dir.resolve()}")

    # --- TEST 1: First Fetch (will create cache) ---
    print("\n" + "#" * 70)
    print("# TEST 1: Initial Fetch (Creates Cache)")
    print("#" * 70)

    events_1 = service.get_high_impact_events(
        days_ahead=7, days_back=2, countries=["USD", "EUR", "GBP"]
    )

    # Display results
    service.display_events(events_1, max_display=10)

    # Show cache info
    print("\n" + "#" * 70)
    print("# CACHE INFO")
    print("#" * 70)
    cache_info = service.get_cache_info()
    print(json.dumps(cache_info, indent=2))

    # --- TEST 2: Second Fetch (Should Use Cache) ---
    print("\n" + "#" * 70)
    print("# TEST 2: Second Fetch (Should Use Cache)")
    print("#" * 70)

    events_2 = service.get_high_impact_events(
        days_ahead=7, days_back=0, countries=["USD", "EUR"]
    )
    service.display_events(events_2, max_display=10)

    # --- TEST 3: Force Refresh (Clear Cache) ---
    print("\n" + "#" * 70)
    print("# TEST 3: Force Refresh (Clear Cache & Fetch Again)")
    print("#" * 70)

    service.clear_cache()
    events_3 = service.get_high_impact_events(
        days_ahead=3, days_back=0, countries=["USD"]
    )

    # Summary
    print("\n" + "#" * 70)
    print("# SUMMARY")
    print("#" * 70)
    print(f"Total Unique Events Fetched: {len(set([id(e) for e in events_1]))}")
    print(f"Cache Info:")
    print(json.dumps(service.get_cache_info(), indent=2))

    print("\n" + "#" * 70)
    print("# TEST COMPLETE")
    print("#" * 70 + "\n")
