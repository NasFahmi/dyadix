"""
llm/groq_client.py

Client untuk Groq API (sangat cepat dan efisien untuk DSS)
Mendukung structured output (JSON mode)
"""

import os
import json
import logging
from typing import Dict, Any

from groq import Groq
from groq.types.chat.chat_completion import ChatCompletion

from llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


class GroqClient(BaseLLMClient):
    """
    Client untuk Groq API.
    Sangat direkomendasikan untuk kecepatan dan biaya rendah.
    """

    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY tidak ditemukan di environment variables")

        self.client = Groq(api_key=api_key)
        self.model = model

    def generate(self, system_prompt: str, user_input: str) -> Dict[str, Any]:
        """
        Generate text biasa (tanpa structured output)
        """
        try:
            response: ChatCompletion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.25,
                max_tokens=900,
                top_p=0.95,
            )

            return {
                "content": response.choices[0].message.content,
                "provider": "groq",
                "model": self.model,
            }

        except Exception as e:
            logger.error(f"Error calling Groq: {e}")
            return {"content": "", "error": str(e), "provider": "groq"}

    def structured_generate(
        self, system_prompt: str, user_input: str, json_schema: Dict
    ) -> Dict[str, Any]:
        """
        Generate dengan Structured Output menggunakan JSON Mode Groq
        """
        try:
            response: ChatCompletion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.2,
                max_tokens=1000,
                response_format={"type": "json_object"},  # Groq JSON Mode
                top_p=0.9,
            )

            content = response.choices[0].message.content.strip()

            # Bersihkan jika ada markdown
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            try:
                parsed = json.loads(content)
                parsed["provider"] = "groq"
                parsed["model"] = self.model
                return parsed
            except json.JSONDecodeError as e:
                logger.warning(f"Groq tidak mengembalikan JSON yang valid: {e}")
                return {
                    "error": "Invalid JSON response from Groq",
                    "raw_content": content,
                    "provider": "groq",
                }

        except Exception as e:
            logger.error(f"Error in Groq structured generate: {e}")
            return {"error": str(e), "provider": "groq"}

    def health_check(self) -> bool:
        """Cek apakah Groq API dapat diakses"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10,
            )
            return bool(response.choices)
        except:
            return False
