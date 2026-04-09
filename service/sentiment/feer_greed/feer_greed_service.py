from service.sentiment.model.feer_greed_model import FearGreedData
from typing import List, Optional
import requests


def get_fear_and_greed_index(limit: int = 1) -> Optional[List[FearGreedData]]:
    """
    Get Fear and Greed index from alternative.me
    :param limit: Number of days to retrieve
    :return: List of FearGreedData, or None if failed
    """
    url = f"https://api.alternative.me/fng/?limit={limit}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data and data.get("metadata", {}).get("error") is None:
            results = []
            for item in data.get("data", []):
                results.append(
                    FearGreedData(
                        value=int(item["value"]),
                        value_classification=item["value_classification"],
                        timestamp=item["timestamp"],
                        time_until_update=item.get("time_until_update"),
                    )
                )
            return results
        return None
    except Exception as e:
        print(f"Error fetching fear and greed index: {e}")
        return None
