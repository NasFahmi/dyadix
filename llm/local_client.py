"""
llm/local_client.py

Client untuk menghubungkan ke LM Studio (Local LLM)
Menggunakan endpoint /api/v1/chat yang kamu gunakan sebelumnya.
"""

import json
import os
import requests
import logging
from typing import Dict, Any

from llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


class LocalClient(BaseLLMClient):
    """
    Client untuk LM Studio (Local LLM)
    """

    def __init__(
        self,
        base_url: str = None,
        model: str = "llama-open-finance-8b",
    ):
        # Gunakan dari env jika tidak dipassing secara eksplisit
        if base_url is None:
            base_url = os.getenv("LOCAL_BASE_URL_LLM", "http://localhost:1234")

        # Pastikan ada protocol (http/https)
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"

        self.base_url = base_url.rstrip("/")
        self.endpoint = f"{self.base_url}/api/v1/chat"
        self.model = model
        self.timeout = 90  # detik

    def generate(self, system_prompt: str, user_input: str) -> Dict[str, Any]:
        """
        Generate text biasa (tanpa structured output)
        """
        payload = {
            "model": self.model,
            "system_prompt": system_prompt,
            "input": user_input,
            "temperature": 0.25,
            "stream": False,
        }

        try:
            response = requests.post(
                self.endpoint,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                logger.error(
                    f"LM Studio error: {response.status_code} - {response.text}"
                )
                return {"content": "", "error": f"HTTP {response.status_code}"}

            result = response.json()

            # Ambil content dari output LM Studio
            if "output" in result and len(result["output"]) > 0:
                content = result["output"][0].get("content", "")
                return {"content": content}
            else:
                return {"content": "", "error": "No output from LM Studio"}

        except requests.exceptions.Timeout:
            logger.error("LM Studio request timeout")
            return {"content": "", "error": "Request timeout"}
        except Exception as e:
            logger.error(f"Error calling LM Studio: {e}")
            return {"content": "", "error": str(e)}

    def structured_generate(
        self, system_prompt: str, user_input: str, json_schema: Dict
    ) -> Dict[str, Any]:
        """
        Generate dengan Structured Output (JSON Schema enforcement)
        """
        payload = {
            "model": self.model,
            "system_prompt": system_prompt,
            "input": user_input,
            "temperature": 0.22,
            "stream": False,
        }

        try:
            response = requests.post(
                self.endpoint,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                logger.error(
                    f"LM Studio structured output error: {response.status_code} - {response.text}"
                )
                return {"error": f"HTTP {response.status_code}", "content": ""}

            result = response.json()

            if "output" in result and len(result["output"]) > 0:
                content = result["output"][0].get("content", "")

                # Bersihkan jika ada markdown
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]

                content = content.strip()

                try:
                    parsed = json.loads(content)
                    return parsed
                except json.JSONDecodeError:
                    logger.warning("LLM tidak mengembalikan JSON yang valid")
                    return {"error": "Invalid JSON response", "raw_content": content}
            else:
                return {"error": "No output from LM Studio"}

        except requests.exceptions.Timeout:
            logger.error("LM Studio structured request timeout")
            return {"error": "Request timeout"}
        except Exception as e:
            logger.error(f"Error in structured generate: {e}")
            return {"error": str(e)}

    def health_check(self) -> bool:
        """Cek apakah LM Studio sedang berjalan"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
