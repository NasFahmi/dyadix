"""
llm/base.py
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseLLMClient(ABC):
    """Base class untuk semua LLM provider"""

    @abstractmethod
    def generate(self, system_prompt: str, user_input: str) -> Dict[str, Any]:
        """Mengirim prompt dan mendapatkan response"""
        pass

    @abstractmethod
    def structured_generate(
        self, system_prompt: str, user_input: str, json_schema: Dict
    ) -> Dict:
        """Mengirim prompt dengan structured output (JSON Schema)"""
        pass
