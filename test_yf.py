from curl_cffi import requests
import json

def test_yf_api(ticker):
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={ticker}&quotesCount=0&newsCount=10"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://finance.yahoo.com",
        "Referer": f"https://finance.yahoo.com/quote/{ticker}?p={ticker}"
    }
    
    try:
        response = requests.get(url, headers=headers, impersonate="chrome120", timeout=15)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            news = data.get("news", [])
            print(f"Got {len(news)} news items")
            for item in news[:2]:
                print(f" - {item.get('title')}")
        else:
            print("Response:", response.text[:200])
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_yf_api("BTC-USD")
