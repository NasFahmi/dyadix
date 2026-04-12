import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict
import pandas as pd  # optional, buat logging


class EconomicCalendarService:
    BASE_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    def get_high_impact_events(
        self, days_ahead: int = 7, days_back: int = 0, countries: list = None
    ) -> List[Dict]:
        """
        Ambil hanya high-impact (merah) dalam periode (H - days_back) s/d (H + days_ahead)
        countries contoh: ["USD", "EUR"] → fokus macro yang pengaruh crypto
        """
        if countries is None:
            countries = ["USD"]  # default US macro paling kuat pengaruhnya ke BTC/ETH

        try:
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
                f"[OK] Economic Calendar: {len(filtered)} high-impact events dalam {days_ahead} hari"
            )
            return filtered

        except Exception as e:
            print(f"[ERROR] fetch economic calendar: {e}")
            return []

    def save_raw(self, events: List[Dict]):
        """Simpan ke data/raw/economic/ sesuai struktur project kamu"""
        # Implementasi sesuai folder structure kamu (contoh pakai pandas atau json)
        pass  # kamu bisa tambah sendiri


if __name__ == "__main__":
    print("Memulai test pengambilan data kalender ekonomi...\n")
    service = EconomicCalendarService()
    # Mengeset days_back=2 agar berita tanggal 10 yang sudah berlalu (kemarin) ikut masuk
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
        print("Tidak ada event high-impact yang ditemukan.")
