"""
test/test_llm_providers.py

Test suite untuk memvalidasi semua LLM provider:
  - Gemini (Google Generative AI)
  - Groq
  - Local (LM Studio)

Jalankan:
    python test/test_llm_providers.py
"""

import io
import json
import logging
import os
import sys
import time

# Force UTF-8 output di Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Pastikan root project ada di path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_llm")

# ── Prompt sederhana untuk test ────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a crypto market analyst. "
    "Answer concisely and return ONLY a valid JSON object."
)

USER_INPUT = (
    "Bitcoin is trading at $84,500. RSI on H1 is 58, trend is bullish. "
    "Provide a brief sentiment analysis in JSON format with fields: "
    "sentiment (string), confidence (float 0-1), brief_reason (string)."
)

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string"},
        "confidence": {"type": "number"},
        "brief_reason": {"type": "string"},
    },
    "required": ["sentiment", "confidence", "brief_reason"],
}

SEP = "=" * 60
LINE = "-" * 50


def print_result(provider_name: str, method: str, result: dict, elapsed: float):
    print(f"\n{LINE}")
    print(f"  Provider : {provider_name}")
    print(f"  Method   : {method}")
    print(f"  Elapsed  : {elapsed:.2f}s")
    print(f"  Result   :")
    print(json.dumps(result, indent=4, ensure_ascii=False))
    has_error = "error" in result
    status = "[FAIL]" if has_error else "[ OK ]"
    print(f"  Status   : {status}")


def test_provider(provider_name: str, client):
    """Jalankan generate() dan structured_generate() untuk satu provider."""
    print(f"\n{SEP}")
    print(f"  Testing: {provider_name}")
    print(SEP)

    # ── 1. generate() ──────────────────────────────────────────────────────────
    print(f"\n[1/2] generate() ...")
    t0 = time.time()
    try:
        result = client.generate(system_prompt=SYSTEM_PROMPT, user_input=USER_INPUT)
        elapsed = time.time() - t0
        print_result(provider_name, "generate()", result, elapsed)
    except Exception as e:
        elapsed = time.time() - t0
        print_result(provider_name, "generate()", {"error": str(e)}, elapsed)

    # ── 2. structured_generate() ───────────────────────────────────────────────
    print(f"\n[2/2] structured_generate() ...")
    t0 = time.time()
    try:
        result = client.structured_generate(
            system_prompt=SYSTEM_PROMPT,
            user_input=USER_INPUT,
            json_schema=JSON_SCHEMA,
        )
        elapsed = time.time() - t0
        print_result(provider_name, "structured_generate()", result, elapsed)
    except Exception as e:
        elapsed = time.time() - t0
        print_result(provider_name, "structured_generate()", {"error": str(e)}, elapsed)


def test_factory_integration():
    """Test integrasi factory dengan provider dari settings.yml / env."""
    print(f"\n{SEP}")
    print("  Testing: LLM Factory Integration")
    print(SEP)

    from llm.factory import get_decision_llm, get_news_social_llm

    for fn_name, fn in [
        ("get_decision_llm()", get_decision_llm),
        ("get_news_social_llm()", get_news_social_llm),
    ]:
        print(f"\n  -> {fn_name}")
        try:
            client = fn()
            print(f"    Client type : {type(client).__name__}")

            t0 = time.time()
            result = client.generate(
                system_prompt=SYSTEM_PROMPT, user_input=USER_INPUT
            )
            elapsed = time.time() - t0
            print(f"    Elapsed     : {elapsed:.2f}s")
            print(f"    Result keys : {list(result.keys())}")
            has_error = "error" in result
            if has_error:
                print(f"    Status      : [FAIL] {result.get('error', '')}")
            else:
                print(f"    Status      : [ OK ]")
        except Exception as e:
            print(f"    [EXCEPTION] : {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'#' * 60}")
    print("  Dyadix LLM Provider Test Suite")
    print(f"{'#' * 60}")

    results = {}

    # ─── 1. Gemini ─────────────────────────────────────────────────────────────
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if gemini_api_key:
        try:
            from llm.gemini_client import GeminiClient

            client = GeminiClient(model="gemini-2.0-flash")
            test_provider("Gemini (gemini-2.0-flash)", client)
            results["gemini"] = "tested"
        except Exception as e:
            print(f"\n[FAIL] Gemini init failed: {e}")
            results["gemini"] = f"error: {e}"
    else:
        print("\n[SKIP] Gemini: GEMINI_API_KEY tidak ditemukan di .env")
        results["gemini"] = "skipped (no API key)"

    # ─── 2. Groq ───────────────────────────────────────────────────────────────
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        try:
            from llm.groq_client import GroqClient

            client = GroqClient(model="llama-3.3-70b-versatile")
            test_provider("Groq (llama-3.3-70b-versatile)", client)
            results["groq"] = "tested"
        except Exception as e:
            print(f"\n[FAIL] Groq init failed: {e}")
            results["groq"] = f"error: {e}"
    else:
        print("\n[SKIP] Groq: GROQ_API_KEY tidak ditemukan di .env")
        results["groq"] = "skipped (no API key)"

    # ─── 3. Local (LM Studio) ──────────────────────────────────────────────────
    local_url = os.getenv("LOCAL_BASE_URL_LLM", "http://localhost:1234")
    if not local_url.startswith(("http://", "https://")):
        local_url = f"http://{local_url}"

    local_model = os.getenv("DECISION_LLM_MODEL", "llama-open-finance-8b")

    try:
        from llm.local_client import LocalClient
        import requests as req

        # Cek apakah LM Studio running
        try:
            health = req.get(f"{local_url}/health", timeout=3)
            lm_running = health.status_code == 200
        except Exception:
            lm_running = False

        if lm_running:
            client = LocalClient(base_url=local_url, model=local_model)
            test_provider(f"Local LM Studio ({local_model})", client)
            results["local"] = "tested"
        else:
            print(f"\n[SKIP] Local: LM Studio tidak running di {local_url}")
            results["local"] = f"skipped (LM Studio not running at {local_url})"
    except Exception as e:
        print(f"\n[FAIL] Local init failed: {e}")
        results["local"] = f"error: {e}"

    # ─── 4. Factory integration ────────────────────────────────────────────────
    test_factory_integration()

    # ─── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'#' * 60}")
    print("  TEST SUMMARY")
    print(f"{'#' * 60}")
    for provider, status in results.items():
        if status == "tested":
            icon = "[ OK ]"
        elif "skipped" in status:
            icon = "[SKIP]"
        else:
            icon = "[FAIL]"
        print(f"  {icon} {provider.upper():<10} -> {status}")
    print(f"{'#' * 60}\n")


if __name__ == "__main__":
    main()
