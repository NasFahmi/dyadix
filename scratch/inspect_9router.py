import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

base_url = os.getenv("NINEROUTER_BASE_URL", "http://localhost:20128/v1")
api_key = os.getenv("NINEROUTER_API_KEY", "nr-placeholder")
headers = {
    "Authorization": f"Bearer {api_key}"
}

try:
    print("\n--- Try Direct API Call ---")
    payload = {
        "model": os.getenv("DECISION_LLM_MODEL", "ds/deepseek-v4-pro-max"),
        "messages": [
            {"role": "system", "content": "You are a trading assistant. You MUST return JSON with fields: 'bias' (string), 'confidence' (number), and 'reason' (string)."},
            {"role": "user", "content": "Analyze ETHUSDC real-time price: 1820.95"}
        ],
        "temperature": 0.2,
        "max_tokens": 1000,
        "response_format": {"type": "json_object"}
    }
    
    resp = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload)
    print(f"Status: {resp.status_code}")
    
    text = resp.text.strip()
    print("Raw text:", text[:200], "...", text[-200:])
    
    # Apply our fix
    last_bracket = text.rfind("}")
    if last_bracket != -1:
        text = text[:last_bracket + 1]
        
    try:
        data = json.loads(text)
        print("[SUCCESS] Parsed JSON:")
        print(json.dumps(data, indent=2))
        content = data["choices"][0]["message"]["content"]
        print("Parsed choice content:")
        print(content)
    except Exception as je:
        print(f"[FAILED] Parsing failed: {je}")
except Exception as e:
    print(f"Failed to call completions: {e}")
