import json
import logging
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from service.exchange.hyperliquid_client import HyperliquidClient

logging.basicConfig(level=logging.INFO)

def test_raw_meta():
    print("Initializing HyperliquidClient...")
    client = HyperliquidClient()
    print("Fetching meta_and_asset_ctxs()...")
    res = client.info.meta_and_asset_ctxs()
    
    if isinstance(res, list) and len(res) == 2:
        meta, asset_ctxs = res[0], res[1]
        universe = meta.get("universe", [])
        print(f"Total Universe Symbols: {len(universe)}")
        print(f"Total Asset Contexts: {len(asset_ctxs)}")
        
        if universe and asset_ctxs:
            print("\nSample Symbol 0 Meta:", universe[0])
            print("Sample Symbol 0 Context:", asset_ctxs[0])
    else:
        print("Unexpected response format:", type(res))

if __name__ == "__main__":
    test_raw_meta()
