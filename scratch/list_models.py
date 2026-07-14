import requests
import os
from dotenv import load_dotenv

load_dotenv()
url = f'{os.getenv("NINEROUTER_BASE_URL")}/models'
api_key = os.getenv("NINEROUTER_API_KEY")
headers = {'Authorization': f'Bearer {api_key}'}

try:
    resp = requests.get(url, headers=headers)
    print("Status:", resp.status_code)
    print(resp.json())
except Exception as e:
    print("Error:", e)
