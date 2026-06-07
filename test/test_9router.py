import os
import sys
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from llm.factory import get_llm_client

def main():
    print("============================================================")
    print("  9Router LLM Client Integration Test")
    print("============================================================")
    
    # Configure environment variables to use ninerouter
    os.environ["LLM_PROVIDER"] = "ninerouter"
    os.environ["DECISION_LLM_MODEL"] = "cmc/deepseek/deepseek-v4-pro"
    
    try:
        client = get_llm_client(provider_type="decision")
        print(f"[OK] Instantiated NinerouterClient with model: {client.model}")
    except Exception as e:
        print(f"[FAIL] Instantiation failed: {e}")
        return

    # 1. Health check
    print("\n--- 1. Testing Health Check ---")
    is_alive = client.health_check()
    print(f"Health Check status: {'ALIVE' if is_alive else 'DEAD'}")

    # 2. Text generation
    print("\n--- 2. Testing Standard Generate ---")
    try:
        res = client.generate(
            system_prompt="You are a helpful trading assistant. Answer in one short sentence.",
            user_input="What is the significance of the 200 SMA?"
        )
        print("Response:")
        print(res.get("content"))
    except Exception as e:
        print(f"Generate failed: {e}")

    # 3. Structured generation
    print("\n--- 3. Testing Structured Generate ---")
    schema = {
        "type": "object",
        "properties": {
            "bias": {"type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL"]},
            "confidence": {"type": "number"},
            "reason": {"type": "string"}
        },
        "required": ["bias", "confidence", "reason"]
    }
    try:
        res = client.structured_generate(
            system_prompt="You are a market analyst. Respond ONLY with a JSON object matching the requested schema.",
            user_input="Analyze this: BTC is trading above the daily open, funding rate is negative, and volume is rising.",
            json_schema=schema
        )
        print("Structured Response:")
        print(res)
    except Exception as e:
        print(f"Structured Generate failed: {e}")

if __name__ == "__main__":
    main()
