"""
test_hyperliquid.py

Test koneksi dan interaksi ke Hyperliquid DEX (Testnet).
Menguji pembacaan saldo, pengambilan harga mark price, penempatan order,
serta pembatalan order.

Jalankan dengan:
  uv run python test/test_hyperliquid.py
"""

import sys
import os
import logging
from dotenv import load_dotenv

# Tambahkan project root ke sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    print("=" * 60)
    print("  DYADIX - Hyperliquid Connection & API Test")
    print("=" * 60)

    from service.exchange.hyperliquid_client import HyperliquidClient

    client = HyperliquidClient()

    # 1. Cek Balance
    print("\n--- [STEP 1] Checking Balance ---")
    balance = client.get_usdt_balance()
    print(f"USDC Account Balance (Withdrawable): ${balance:.4f} USDC")

    # 2. Cek Realtime Price
    print("\n--- [STEP 2] Fetching Realtime Prices ---")
    pairs = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    for p in pairs:
        price = client.get_realtime_price(p)
        print(f"Price for {p:8s}: ${price:,.4f}")

    # 3. Cek Open Positions
    print("\n--- [STEP 3] Fetching Open Positions ---")
    positions = client.get_open_positions()
    print(f"Found {len(positions)} active positions.")
    for pos in positions:
        print(f"  - Pair: {pos['symbol']}, Size: {pos['positionAmt']}, Entry: ${pos['entryPrice']}, UnPnL: ${pos['unRealizedProfit']:.2f}")

    # 4. Cek Open Orders
    print("\n--- [STEP 4] Fetching Open Orders ---")
    orders = client.get_open_orders()
    print(f"Found {len(orders)} open orders.")
    for o in orders:
        print(f"  - OrderID: {o['orderId']}, Type: {o['type']}, Side: {o['side']}, Qty: {o['origQty']}")

    # 5. Simulasi Penempatan Limit Order & Cancel jika API Key diset
    if not os.getenv("HYPERLIQUID_PRIVATE_KEY"):
        print("\n[WARN] HYPERLIQUID_PRIVATE_KEY kosong di .env. Tes order placement dilewati.")
        print("Selesai.")
        return

    print("\n--- [STEP 5] Order Placement Simulation (Testnet) ---")
    pair = "SOLUSDT"
    price = client.get_realtime_price(pair)
    if price <= 0:
        print("Gagal mengambil harga realtime SOL. Pembatalan tes order.")
        return

    # Tempatkan order limit beli 5% di bawah harga mark price agar tidak langsung terisi (resting)
    limit_price = price * 0.95
    qty = 0.3 # 0.3 SOL (sehingga nilainya > $10)
    
    print(f"Mencoba menempatkan LIMIT BUY {qty} {pair} @ ${limit_price:,.4f}...")
    order = client.place_limit_order(pair, "BUY", qty, limit_price)
    
    if order:
        order_id = order["orderId"]
        print(f"[OK] Order berhasil ditempatkan! Order ID: {order_id}")
        
        # Cek Status
        print("\nMencek status order...")
        status = client.get_order_status(pair, order_id)
        if status:
            print(f"Status: {status['status']}, AvgPrice: ${status['avgPrice']}")
            
        # Cancel Order
        print("\nMembatalkan order...")
        canceled = client.cancel_order(pair, order_id)
        if canceled:
            print("[OK] Order berhasil dibatalkan!")
        else:
            print("[ERR] Gagal membatalkan order.")
    else:
        print("[ERR] Gagal menempatkan order limit. Pastikan saldo testnet USDC Anda mencukupi.")

    print("\n" + "=" * 60)
    print("  Test complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
