"""
llm/deepseek_client.py

Client untuk DeepSeek API.
Menggunakan OpenAI SDK sesuai dengan dokumentasi DeepSeek.
"""

import os
import json
import logging
from typing import Dict, Any

from openai import OpenAI

from llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


class DeepseekClient(BaseLLMClient):
    """
    Client untuk DeepSeek API menggunakan OpenAI SDK.
    """

    def __init__(self, model: str = "deepseek-chat"):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY tidak ditemukan di environment variables")

        self.client = OpenAI(
            api_key=api_key, 
            base_url="https://api.deepseek.com"
        )
        self.model = model

    def generate(self, system_prompt: str, user_input: str) -> Dict[str, Any]:
        """
        Generate text biasa (tanpa structured output)
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.25,
                max_tokens=1000,
                top_p=0.95,
                stream=False
            )

            return {
                "content": response.choices[0].message.content,
                "provider": "deepseek",
                "model": self.model,
            }

        except Exception as e:
            logger.error(f"Error calling DeepSeek: {e}")
            return {"content": "", "error": str(e), "provider": "deepseek"}

    def structured_generate(
        self, system_prompt: str, user_input: str, json_schema: Dict
    ) -> Dict[str, Any]:
        """
        Generate dengan Structured Output menggunakan JSON Mode
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.2,
                max_tokens=1000,
                response_format={"type": "json_object"},
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
                parsed["provider"] = "deepseek"
                parsed["model"] = self.model
                return parsed
            except json.JSONDecodeError as e:
                logger.warning(f"DeepSeek tidak mengembalikan JSON yang valid: {e}")
                return {
                    "error": "Invalid JSON response from DeepSeek",
                    "raw_content": content,
                    "provider": "deepseek",
                }

        except Exception as e:
            logger.error(f"Error in DeepSeek structured generate: {e}")
            return {"error": str(e), "provider": "deepseek"}

    def health_check(self) -> bool:
        """Cek apakah DeepSeek API dapat diakses"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10,
            )
            return bool(response.choices)
        except Exception as e:
            logger.error(f"DeepSeek health check failed: {e}")
            return False
