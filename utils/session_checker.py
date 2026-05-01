from datetime import datetime
import logging
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def is_active_session(active_session_config: str) -> bool:
    """
    Cek apakah waktu saat ini (New York Time) berada di dalam session yang aktif.
    Session times in NY Time (America/New_York):
      Asia: 20:00 - 05:00
      London: 04:00 - 13:00
      NY: 09:00 - 18:00
    """
    config = active_session_config.lower().strip()

    if config == "all":
        return True

    # Ambil waktu saat ini di zona waktu New York
    ny_tz = ZoneInfo("America/New_York")
    now = datetime.now(ny_tz).time()
    hour = now.hour + now.minute / 60.0

    # Define session ranges dalam waktu New York (EDT/EST)
    # Asia: 20:00 malam sampai 05:00 pagi (melewati tengah malam)
    is_asia = hour >= 20 or hour <= 5
    # London: 04:00 pagi sampai 13:00 siang
    is_london = 4 <= hour <= 13
    # NY: 09:00 pagi sampai 18:00 sore
    is_ny = 8 <= hour <= 18

    if config == "asia":
        return is_asia
    elif config == "london":
        return is_london
    elif config == "ny":
        return is_ny
    elif config == "asia_london":
        return is_asia or is_london
    elif config == "london_ny":
        return is_london or is_ny
    elif config == "asia_ny":
        return is_asia or is_ny
    else:
        # Default if not recognized
        logger.warning(f"Unknown active_session config: {config}. Defaulting to 'all'.")
        return True
