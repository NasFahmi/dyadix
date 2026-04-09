from dataclasses import dataclass
from typing import Optional


@dataclass
class FearGreedData:
    value: int
    value_classification: str
    timestamp: str
    time_until_update: Optional[str] = None
