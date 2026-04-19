"""
llm/gemini_client.py

Client untuk Google Gemini API (via google-genai SDK terbaru)
Mendukung structured output dan regular generation.
"""

import os
import json
import logging
from typing import Dict, Any

from google import genai
from google.genai import types

from llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


class GeminiClient(BaseLLMClient):
    """
    Client untuk Google Gemini API menggunakan SDK google-genai terbaru.
    """

    def __init__(self, model: str = "gemini-2.0-flash"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY tidak ditemukan di environment variables")

        self.client = genai.Client(api_key=api_key)
        self.model_id = model

        # Safety settings yang lebih longgar untuk analisis crypto
        self.safety_settings = [
            types.SafetySetting(
                category="HARM_CATEGORY_HARASSMENT",
                threshold="BLOCK_NONE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_HATE_SPEECH",
                threshold="BLOCK_NONE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                threshold="BLOCK_NONE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_DANGEROUS_CONTENT",
                threshold="BLOCK_NONE",
            ),
        ]

    def generate(self, system_prompt: str, user_input: str) -> Dict[str, Any]:
        """
        Generate text biasa (tanpa structured output)
        """
        try:
            full_prompt = f"{system_prompt}\n\n{user_input}"

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.25,
                    max_output_tokens=900,
                    safety_settings=self.safety_settings,
                ),
            )

            return {"content": response.text, "provider": "gemini"}

        except Exception as e:
            logger.error(f"Error calling Gemini: {e}")
            return {"content": "", "error": str(e), "provider": "gemini"}

    def structured_generate(
        self, system_prompt: str, user_input: str, json_schema: Dict
    ) -> Dict[str, Any]:
        """
        Generate dengan Structured Output menggunakan JSON Schema
        """
        try:
            full_prompt = f"{system_prompt}\n\n{user_input}"

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=1000,
                    response_mime_type="application/json",
                    response_schema=json_schema,
                    safety_settings=self.safety_settings,
                ),
            )

            content = response.text.strip()

            try:
                parsed = json.loads(content)
                parsed["provider"] = "gemini"
                return parsed
            except json.JSONDecodeError:
                logger.warning("Gemini tidak mengembalikan JSON yang valid")
                return {
                    "error": "Invalid JSON response from Gemini",
                    "raw_content": content,
                    "provider": "gemini",
                }

        except Exception as e:
            logger.error(f"Error in Gemini structured generate: {e}")
            return {"error": str(e), "provider": "gemini"}

    def health_check(self) -> bool:
        """Cek apakah Gemini API dapat diakses"""
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents="Hello",
            )
            return bool(response.text)
        except:
            return False
