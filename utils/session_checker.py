from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def is_active_session(active_session_config: str) -> bool:
    """
    Cek apakah waktu saat ini (UTC) berada di dalam session yang aktif.
    Session times in UTC:
      Asia: 00:00 - 09:00
      London: 08:00 - 17:00
      NY: 13:00 - 22:00
    """
    config = active_session_config.lower().strip()
    
    if config == "all":
        return True
        
    now = datetime.utcnow().time()
    hour = now.hour + now.minute / 60.0

    # Define session ranges (start_hour, end_hour)
    # If end_hour < start_hour, it wraps around midnight, but here all are within 0-24
    if config == "asia":
        return 0 <= hour <= 9
    elif config == "london":
        return 8 <= hour <= 17
    elif config == "ny":
        return 13 <= hour <= 22
    elif config == "asia_london":
        return 0 <= hour <= 17
    elif config == "london_ny":
        return 8 <= hour <= 22
    elif config == "asia_ny":
        return 0 <= hour <= 22
    else:
        # Default if not recognized
        logger.warning(f"Unknown active_session config: {config}. Defaulting to 'all'.")
        return True
