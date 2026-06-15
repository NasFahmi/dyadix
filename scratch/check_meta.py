import os
from hyperliquid.info import Info
from hyperliquid.utils import constants

info = Info(constants.TESTNET_API_URL, skip_ws=True)
meta = info.meta()
universe = [s["name"] for s in meta.get("universe", [])]
print(f"Total symbols on Testnet: {len(universe)}")
print("Does XRP exist?", "XRP" in universe)
print("Some symbols:", universe[:20])
