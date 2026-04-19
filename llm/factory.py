"""
llm/factory.py

Factory untuk memilih LLM Client berdasarkan konfigurasi.
Mendukung environment variables dan settings.yaml
"""

import os
import logging
from typing import Dict, Any

from llm.base import BaseLLMClient
from llm.groq_client import GroqClient
from llm.gemini_client import GeminiClient
from llm.local_client import LocalClient
from config.settings import get_config

logger = logging.getLogger(__name__)


def get_llm_client(provider_type: str = "decision") -> BaseLLMClient:
    """
    Mengembalikan LLM Client sesuai konfigurasi.

    provider_type: "decision" atau "news_social"
        - decision  : untuk Decision Engine (final decision)
        - news_social: untuk analisis news + social

    Prioritas model:
        1. Env var (NEWS_SOCIAL_ANALYSIS_MODEL / DECISION_LLM_MODEL)
        2. settings.yml llm.news_social_model / llm.decision_model
        3. settings.yml llm.model
        4. Hardcoded default

    Prioritas provider:
        1. settings.yml llm.provider
        2. Env var LLM_PROVIDER
        3. "local"
    """
    config = get_config().get("llm", {})
    env = os.environ

    # Tentukan provider
    provider = config.get("provider", env.get("LLM_PROVIDER", "local")).lower()

    # Tentukan model per fungsi
    default_model = config.get("model", "llama-open-finance-8b")
    if provider_type == "news_social":
        model = env.get(
            "NEWS_SOCIAL_ANALYSIS_MODEL",
            config.get("news_social_model", default_model),
        )
    else:  # decision
        model = env.get(
            "DECISION_LLM_MODEL",
            config.get("decision_model", default_model),
        )

    # Base URL untuk Local LLM
    local_base_url = env.get("LOCAL_BASE_URL_LLM", "http://localhost:1234")
    # Pastikan ada http:// prefix
    if not local_base_url.startswith(("http://", "https://")):
        local_base_url = f"http://{local_base_url}"

    logger.info(
        f"[LLMFactory] provider={provider} | type={provider_type} | model={model}"
    )

    # Pilih client berdasarkan provider
    if provider == "groq":
        return GroqClient(model=model)

    elif provider == "gemini":
        return GeminiClient(model=model)

    elif provider == "local":
        return LocalClient(base_url=local_base_url, model=model)

    else:
        logger.warning(
            f"[LLMFactory] Provider '{provider}' tidak dikenal. Fallback ke local."
        )
        return LocalClient(base_url=local_base_url, model=model)


# ── Helper shortcuts ──────────────────────────────────────────────────────────

def get_decision_llm() -> BaseLLMClient:
    """Shortcut: Decision Engine LLM"""
    return get_llm_client(provider_type="decision")


def get_news_social_llm() -> BaseLLMClient:
    """Shortcut: News + Social Analysis LLM"""
    return get_llm_client(provider_type="news_social")
