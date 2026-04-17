import requests
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from pathlib import Path
import pandas as pd  # optional, for logging


class EconomicCalendarService:
    BASE_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    def __init__(self, cache_dir: str = "cache/economic"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self) -> Path:
        """Generates a cache filename based on the current ISO week."""
        now = datetime.now(timezone.utc)
        year, week, _ = now.isocalendar()
        return self.cache_dir / f"calendar_{year}_W{week:02d}.json"

    def get_high_impact_events(
        self, days_ahead: int = 7, days_back: int = 0, countries: list = None
    ) -> List[Dict]:
        """
        Fetch High-Impact (Red) events within the period (Today - days_back) to (Today + days_ahead).
        Countries example: ["USD", "EUR"] -> focus on macro factors affecting crypto.
        """
        if countries is None:
            countries = ["USD"]  # US macro has the strongest influence on BTC/ETH

        # 1. Attempt to load from cache
        cache_path = self._get_cache_path()
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    print(f"[CACHE] Loading economic calendar from {cache_path.name}")
                    return json.load(f)
            except Exception as e:
                print(f"[WARNING] Cache read failed: {e}")

        # 2. Fetch from network if cache missing or corrupted
        try:
            print(f"[FETCH] Downloading economic calendar from {self.BASE_URL}")
            response = requests.get(self.BASE_URL, timeout=10)
            response.raise_for_status()
            events = response.json()

            today = datetime.now(timezone.utc).date()
            start_date = today - timedelta(days=days_back)
            cutoff = today + timedelta(days=days_ahead)

            filtered = []
            for event in events:
                if event.get("impact") != "High":
                    continue
                if event.get("country") not in countries:
                    continue

                # Parse date (format Forex Factory ISO8601: "YYYY-MM-DDTHH:MM:SS-04:00")
                parsed_dt = datetime.fromisoformat(event["date"])
                event_date = parsed_dt.date()
                event_time_str = parsed_dt.strftime("%H:%M:%S")

                if start_date <= event_date <= cutoff:
                    filtered.append(
                        {
                            "title": event["title"],
                            "country": event["country"],
                            "date": str(event_date),
                            "time": event_time_str,
                            "impact": event["impact"],
                            "forecast": event.get("forecast", ""),
                            "previous": event.get("previous", ""),
                            "timestamp": parsed_dt.isoformat(),
                        }
                    )

            # Sort by date + time
            filtered.sort(key=lambda x: x["timestamp"])

            print(
                f"[OK] Economic Calendar: {len(filtered)} high-impact events within {days_ahead} days"
            )

            # 3. Save to cache
            self.save_raw(filtered)

            return filtered

        except Exception as e:
            print(f"[ERROR] fetch economic calendar: {e}")
            return []

    def save_raw(self, events: List[Dict]):
        """Persists the fetched events to a local JSON cache."""
        cache_path = self._get_cache_path()
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(events, f, indent=2)
            print(f"[OK] Economic cache saved to {cache_path.name}")
        except Exception as e:
            print(f"[ERROR] Failed to save economic cache: {e}")


if __name__ == "__main__":
    print("Starting economic calendar retrieval test...\n")
    service = EconomicCalendarService()
    # Setting days_back=2 to include past events from earlier this week
    events = service.get_high_impact_events(
        days_ahead=7, days_back=2, countries=["USD"]
    )

    print("-" * 50)
    if events:
        for idx, event in enumerate(events, 1):
            print(
                f"{idx}. [{event['date']} {event['time']} UTC] {event['country']} - {event['title']}"
            )
            print(
                f"   Impact: {event['impact']} | Fcast: {event['forecast']} | Prev: {event['previous']}"
            )
    else:
        print("No high-impact events found.")
