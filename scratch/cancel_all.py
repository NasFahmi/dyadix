import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from service.exchange.hyperliquid_client import HyperliquidClient

def main():
    client = HyperliquidClient()
    orders = client.get_open_orders("SOLUSDT")
    print(f"Found {len(orders)} open orders for SOLUSDT.")
    for o in orders:
        oid = o["orderId"]
        print(f"Cancelling order {oid}...")
        res = client.cancel_order("SOLUSDT", oid)
        print(f"Result: {res}")

if __name__ == "__main__":
    main()
