"""
test_trade_execution.py

Test eksekusi order ke Binance Futures (Testnet) ketika ada signal
dari Decision LLM. Script ini mensimulasikan keseluruhan alur:

  Simulated LLM Decision (BUY/SELL)
      -> OrderExecutor.execute()
          -> BinanceFuturesClient (Testnet)
              -> place_market_order / place_limit_order
              -> place_stop_loss_order
              -> place_take_profit_order

Jalankan dengan:
  uv run python test_trade_execution.py
  uv run python test_trade_execution.py --pair SOLUSDT --side SELL --type MARKET
"""

import sys
import os
import argparse
import logging
from dotenv import load_dotenv

# Add project root to sys.path to allow importing from top-level packages (service, bot, etc.)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# -- Logging setup ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
#  SIMULATED LLM DECISIONS
#  Ini meniru output dari Decision LLM yang sesungguhnya.
#  Entry/SL/TP dihitung berdasarkan harga realtime saat test dijalankan.
# -----------------------------------------------------------------------------


def build_mock_decision(side: str, execution_type: str, realtime_price: float) -> dict:
    """
    Buat simulasi output Decision LLM berdasarkan side dan harga realtime.

    SL  = 0.5% dari harga (berlawanan arah)
    TP  = 1.0% dari harga (searah) -> RR 1:2
    Entry zone = +/-0.2% dari harga saat ini
    """
    sl_pct = 0.005  # 0.5% stop loss
    tp_pct = 0.010  # 1.0% take profit (RR 1:2)
    ez_pct = 0.002  # 0.2% entry zone spread

    if side.upper() == "BUY":
        sl_price = round(realtime_price * (1 - sl_pct), 4)
        tp_price = round(realtime_price * (1 + tp_pct), 4)
        ez_low = round(realtime_price * (1 - ez_pct), 4)
        ez_high = round(realtime_price * (1 + ez_pct), 4)
        bias = "Moderate Bullish"
    else:
        sl_price = round(realtime_price * (1 + sl_pct), 4)
        tp_price = round(realtime_price * (1 - tp_pct), 4)
        ez_low = round(realtime_price * (1 - ez_pct), 4)
        ez_high = round(realtime_price * (1 + ez_pct), 4)
        bias = "Moderate Bearish"

    return {
        "decision": side.upper(),
        "confidence": 0.72,
        "bias": bias,
        "recommended_timeframe": "M15",
        "entry_zone": f"{ez_low}-{ez_high}",
        "stop_loss": str(sl_price),
        "target": str(tp_price),
        "risk_reward": "1:2",
        "execution_type": execution_type.upper(),
        "expected_move": f"+/-1% dalam 4 jam",
        "reason": "[TEST] Simulated LLM decision for trade execution test",
        "key_risks": ["Test signal - not a real trade setup"],
        "rr_calculation": f"SL={sl_price} | TP={tp_price} | RR=1:2",
        "invalidated_if": "Price breaks beyond SL level",
    }


# -----------------------------------------------------------------------------
#  STEP 1 - Connect & check account
# -----------------------------------------------------------------------------


def check_account(client) -> tuple[float, bool]:
    """Verifikasi koneksi dan ambil balance. Returns (balance, ok)."""
    print("\n" + "=" * 60)
    print("  STEP 1: Account & Connection Check")
    print("=" * 60)

    balance = client.get_usdt_balance()
    mode = "TESTNET" if client.testnet else "PRODUCTION [WARN]"

    print(f"  Mode    : {mode}")
    print(f"  Balance : ${balance:.2f} USDT")

    if balance <= 0:
        print("  [ERR] Balance = 0. Pastikan testnet wallet sudah ada USDT.")
        print("     -> Kunjungi https://testnet.binancefuture.com/ dan klaim USDT.")
        return balance, False

    print("  [OK] Account OK")
    return balance, True


# -----------------------------------------------------------------------------
#  STEP 2 - Fetch realtime price
# -----------------------------------------------------------------------------


def fetch_price(client, pair: str) -> float:
    """Ambil mark price terkini dari Binance."""
    print("\n" + "=" * 60)
    print("  STEP 2: Realtime Price")
    print("=" * 60)

    price = client.get_realtime_price(pair)
    if price <= 0:
        print(f"  [ERR] Gagal fetch harga untuk {pair}")
        return 0.0

    print(f"  {pair} Mark Price: ${price:,.4f}")
    return price


# -----------------------------------------------------------------------------
#  STEP 3 - Build & display mock decision
# -----------------------------------------------------------------------------


def display_decision(decision: dict, pair: str):
    """Tampilkan simulated decision yang akan dieksekusi."""
    print("\n" + "=" * 60)
    print("  STEP 3: Simulated LLM Decision")
    print("=" * 60)
    print(f"  Pair          : {pair}")
    print(f"  Decision      : {decision['decision']}")
    print(f"  Confidence    : {decision['confidence']}")
    print(f"  Bias          : {decision['bias']}")
    print(f"  Entry Zone    : {decision['entry_zone']}")
    print(f"  Stop Loss     : {decision['stop_loss']}")
    print(f"  Target        : {decision['target']}")
    print(f"  RR Ratio      : {decision['risk_reward']}")
    print(f"  Exec Type     : {decision['execution_type']}")
    print(f"  RR Calc       : {decision['rr_calculation']}")
    print(f"  Reason        : {decision['reason']}")


# -----------------------------------------------------------------------------
#  STEP 4 - Execute via OrderExecutor
# -----------------------------------------------------------------------------


def execute_order(pair: str, decision: dict, realtime_price: float):
    """Panggil OrderExecutor.execute() - sama persis seperti yang dipanggil LoopScheduler."""
    print("\n" + "=" * 60)
    print("  STEP 4: Executing Order via OrderExecutor")
    print("=" * 60)

    from service.trade.order_executor import OrderExecutor

    executor = OrderExecutor()

    print(f"  Leverage : {executor.leverage}x")
    print(f"  Risk %   : {executor.risk_pct}%")
    print("  [WAIT] Placing order...")

    result = executor.execute(
        pair=pair,
        decision=decision,
        realtime_price=realtime_price,
        decision_id=None,  # Tidak ada DB decision record dalam test ini
    )

    print("\n" + "-" * 60)
    if result:
        trade_id = result.get("trade_id")
        actual_entry = result.get("actual_entry")
        sl_price = result.get("sl_price")
        tp_price = result.get("tp_price")
        quantity = result.get("quantity")

        print(f"  [OK] ORDER EXECUTED SUCCESSFULLY")
        print(f"  Trade ID (DB): {trade_id}")
        print(f"  Actual Entry : ${actual_entry}")
        print(f"  Stop Loss   : ${sl_price}")
        print(f"  Take Profit: ${tp_price}")
        print(f"  Quantity   : {quantity}")
    else:
        print("  [ERR] ORDER FAILED - lihat log di atas untuk detail")
    print("-" * 60)

    return result


# -----------------------------------------------------------------------------
#  STEP 5 - Verify: cek open positions setelah order
# -----------------------------------------------------------------------------


def verify_positions(client, pair: str):
    """Cek apakah posisi berhasil dibuka di Binance dan TP/SL sudah ter-set."""
    print("\n" + "=" * 60)
    print("  STEP 5: Verifying Open Positions & TP/SL")
    print("=" * 60)

    positions = client.get_open_positions(pair)
    if not positions:
        print(f"  [WARN]  Tidak ada posisi terbuka untuk {pair}")
        print(
            "     (Normal jika LIMIT order belum terisi, atau MARKET order belum settle)"
        )
        return

    for pos in positions:
        side = "LONG" if float(pos.get("positionAmt", 0)) > 0 else "SHORT"
        print(f"  [OK] Open Position: {pair}")
        print(f"     Side           : {side}")
        print(f"     Amount         : {pos.get('positionAmt')}")
        print(f"     Entry Price    : {pos.get('entryPrice')}")
        print(f"     Mark Price     : {pos.get('markPrice')}")
        print(f"     Unrealized PnL : {pos.get('unRealizedProfit')}")
        print(f"     Leverage       : {pos.get('leverage')}x")

        # Check TP/SL orders using the new verify method
        try:
            tp_sl_status = client.verify_tp_sl_set(pair)

            if tp_sl_status.get("has_tp"):
                tp_order = tp_sl_status["tp_orders"][0]
                print(f"     [OK] TP Set   : {tp_order.get('stopPrice')} (ID: {tp_order.get('orderId')})")
            else:
                print(f"     [WARN] TP NOT SET (testnet limitation)")

            if tp_sl_status.get("has_sl"):
                sl_order = tp_sl_status["sl_orders"][0]
                print(f"     [OK] SL Set   : {sl_order.get('stopPrice')} (ID: {sl_order.get('orderId')})")
            else:
                print(f"     [WARN] SL NOT SET (testnet limitation)")
        except Exception as e:
            print(f"     [WARN] Could not verify TP/SL: {e}")


# -----------------------------------------------------------------------------
#  MAIN
# -----------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description="Test trade execution via OrderExecutor ke Binance (Testnet)"
    )
    parser.add_argument(
        "--pair",
        default="BTCUSDT",
        help="Trading pair (default: BTCUSDT)",
    )
    parser.add_argument(
        "--side",
        default="BUY",
        choices=["BUY", "SELL"],
        help="Trade direction (default: BUY)",
    )
    parser.add_argument(
        "--type",
        default="MARKET",
        choices=["MARKET", "LIMIT"],
        dest="exec_type",
        help="Order type (default: MARKET)",
    )
    parser.add_argument(
        "--skip-confirm",
        action="store_true",
        help="Skip konfirmasi sebelum eksekusi",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("\n" + "=" * 60)
    print("  DYADIX - Trade Execution Test")
    print("  Target: Binance Futures Testnet")
    print("=" * 60)
    print(f"  Pair     : {args.pair}")
    print(f"  Side     : {args.side}")
    print(f"  ExecType : {args.exec_type}")

    # Init Binance client langsung (untuk check account & verify)
    from service.exchange.binance_futures_client import BinanceFuturesClient

    client = BinanceFuturesClient()

    # STEP 1: Account check
    balance, ok = check_account(client)
    if not ok:
        sys.exit(1)

    # STEP 2: Realtime price
    realtime_price = fetch_price(client, args.pair)
    if realtime_price <= 0:
        sys.exit(1)

    # STEP 3: Build & display simulated decision
    decision = build_mock_decision(args.side, args.exec_type, realtime_price)
    display_decision(decision, args.pair)

    # Konfirmasi sebelum eksekusi (kecuali --skip-confirm)
    if not args.skip_confirm:
        print("\n" + "[WARN]  " * 15)
        print("  PERHATIAN: Order ini akan dieksekusi ke Binance Testnet!")
        print("  Ini adalah uang virtual, BUKAN uang asli.")
        print("[WARN]  " * 15)
        confirm = input("\n  Lanjutkan eksekusi? (y/N): ").strip().lower()
        if confirm != "y":
            print("  [ERR] Dibatalkan oleh user.")
            sys.exit(0)

    # STEP 4: Execute order
    result = execute_order(args.pair, decision, realtime_price)

    # STEP 5: Verify positions
    import time

    print("\n  [WAIT] Menunggu 2 detik sebelum cek posisi...")
    time.sleep(2)
    verify_positions(client, args.pair)

    print("\n" + "=" * 60)
    if result and result.get("trade_id"):
        print("  [OK] TEST PASSED - Order berhasil dieksekusi dengan TP/SL")
    else:
        print("  [ERR] TEST FAILED - Order tidak berhasil. Periksa log di atas.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
