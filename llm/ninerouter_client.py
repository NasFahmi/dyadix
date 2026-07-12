"""
llm/ninerouter_client.py

Client untuk 9router API menggunakan requests secara langsung.
Menjamin parameter "stream": false diserialisasi secara eksplisit dalam request body.
"""

import os
import re
import json
import logging
import requests
from typing import Dict, Any
from dotenv import load_dotenv

# Pastikan file .env dibaca
load_dotenv()

from llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


def strip_thinking(content: str) -> str:
    """
    Menghapus blok <think>...</think> dari output model jika ada,
    agar parser JSON tidak error saat thinking mode aktif.
    """
    cleaned = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    return cleaned.strip()


class NinerouterClient(BaseLLMClient):
    """
    Client untuk 9router API menggunakan requests library.
    """

    def __init__(self, model: str = "cmc/deepseek/deepseek-v4-pro", base_url: str = None, api_key: str = None):
        if not api_key:
            api_key = os.getenv("NINEROUTER_API_KEY")
        if not api_key:
            api_key = "nr-placeholder"

        if not base_url:
            base_url = os.getenv("NINEROUTER_BASE_URL", "http://localhost:20128/v1")
            
        self.endpoint = f"{base_url.rstrip('/')}/chat/completions"
        
        # Gunakan NINEROUTER_COMBO jika didefinisikan di environment
        combo = os.getenv("NINEROUTER_COMBO")
        if combo:
            self.model = combo
            logger.info(f"NinerouterClient: Using combo override '{self.model}'")
        else:
            self.model = model
            
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        self.timeout = 90  # detik


    def generate(self, system_prompt: str, user_input: str) -> Dict[str, Any]:
        """
        Generate text biasa (tanpa structured output)
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            "temperature": 0.25,
            "max_tokens": 8192,
            "top_p": 0.95,
            "stream": False,  # Eksplisit False
            "thinking": {"type": "disabled"},  # Force nonaktifkan reasoning/thinking
        }

        try:
            response = requests.post(
                self.endpoint,
                headers=self.headers,
                json=payload,
                timeout=self.timeout
            )

            if response.status_code != 200:
                logger.error(f"9router error: {response.status_code} - {response.text}")
                return {"content": "", "error": f"HTTP {response.status_code}", "provider": "ninerouter"}

            text = response.text.strip()
            last_bracket = text.rfind("}")
            if last_bracket != -1:
                text = text[:last_bracket + 1]
            result = json.loads(text)
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"].get("content", "")
                content = strip_thinking(content)
                return {
                    "content": content,
                    "provider": "ninerouter",
                    "model": self.model,
                }
            else:
                return {"content": "", "error": "No output from 9router", "provider": "ninerouter"}

        except Exception as e:
            logger.error(f"Error calling 9router: {e}")
            return {"content": "", "error": str(e), "provider": "ninerouter"}

    def structured_generate(
        self, system_prompt: str, user_input: str, json_schema: Dict
    ) -> Dict[str, Any]:
        """
        Generate dengan Structured Output menggunakan JSON Mode
        """
        # Coba dengan response_format json_object
        payload_json = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            "temperature": 0.2,
            "max_tokens": 8192,
            "top_p": 0.9,
            "response_format": {"type": "json_object"},
            "stream": False,
            "thinking": {"type": "disabled"},  # Force nonaktifkan reasoning/thinking
        }

        try:
            response = requests.post(
                self.endpoint,
                headers=self.headers,
                json=payload_json,
                timeout=self.timeout
            )

            # Jika JSON mode gagal/tidak didukung, coba tanpa response_format
            if response.status_code != 200:
                logger.warning("9router JSON mode request failed, falling back to standard prompt format.")
                payload_fallback = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt + "\nFormat response Anda harus berupa JSON yang valid sesuai dengan skema."},
                        {"role": "user", "content": user_input},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 8192,
                    "top_p": 0.9,
                    "stream": False,
                    "thinking": {"type": "disabled"},  # Force nonaktifkan reasoning/thinking
                }
                response = requests.post(
                    self.endpoint,
                    headers=self.headers,
                    json=payload_fallback,
                    timeout=self.timeout
                )

            if response.status_code != 200:
                logger.error(f"9router structured error: {response.status_code} - {response.text}")
                return {"error": f"HTTP {response.status_code}", "provider": "ninerouter"}

            text = response.text.strip()
            last_bracket = text.rfind("}")
            if last_bracket != -1:
                text = text[:last_bracket + 1]
            result = json.loads(text)
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"].get("content", "").strip()
                content = strip_thinking(content)

                # Bersihkan markdown jika ada
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

                try:
                    parsed = json.loads(content)
                    parsed["provider"] = "ninerouter"
                    parsed["model"] = self.model
                    return parsed
                except json.JSONDecodeError as e:
                    logger.warning(f"9router tidak mengembalikan JSON yang valid: {e}")
                    return {
                        "error": "Invalid JSON response from 9router",
                        "raw_content": content,
                        "provider": "ninerouter",
                    }
            else:
                return {"error": "No output from 9router", "provider": "ninerouter"}

        except Exception as e:
            logger.error(f"Error in 9router structured generate: {e}")
            return {"error": str(e), "provider": "ninerouter"}

    def health_check(self) -> bool:
        """Cek apakah 9router API dapat diakses"""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 10,
            "stream": False,
            "thinking": {"type": "disabled"}
        }
        try:
            response = requests.post(
                self.endpoint,
                headers=self.headers,
                json=payload,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"9router health check failed: {e}")
            return False
