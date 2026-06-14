"""
service/exchange/hyperliquid_client.py

Wrapper untuk Hyperliquid API menggunakan hyperliquid-python-sdk.
Menggantikan BinanceFuturesClient dengan interface yang sama.
Mendukung testnet via HYPERLIQUID_TESTNET=true di .env.
"""

import os
import math
import logging
from typing import Dict, Any, Optional, List
from eth_account import Account
from dotenv import load_dotenv
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

load_dotenv()

logger = logging.getLogger(__name__)


class HyperliquidClient:
    """
    Client untuk Hyperliquid Perpetuals DEX.
    Semua margin menggunakan USDC.
    """

    def __init__(self):
        private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
        main_address = os.getenv("HYPERLIQUID_MAIN_ADDRESS", "")
        testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"

        base_url = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL
        self.testnet = testnet

        if not private_key:
            logger.warning("HYPERLIQUID_PRIVATE_KEY is missing in .env")
            self.wallet = None
            self.exchange = None
            self.account_address = ""
        else:
            # Pastikan private key diawali '0x' jika belum ada
            if not private_key.startswith("0x"):
                private_key = "0x" + private_key
            self.wallet = Account.from_key(private_key)
            
            # Jika user mendelegasikan Agent Wallet, kita butuh address wallet utama
            # untuk inisialisasi Exchange.
            if main_address:
                self.account_address = main_address
                self.exchange = Exchange(self.wallet, base_url, account_address=main_address)
            else:
                self.account_address = self.wallet.address
                self.exchange = Exchange(self.wallet, base_url)

        self.info = Info(base_url, skip_ws=True)
        mode = "TESTNET" if testnet else "PRODUCTION"
        logger.info(f"HyperliquidClient initialized [{mode}] for user {self.account_address}")

        # Cache untuk informasi presisi coin (szDecimals)
        self.symbols_info = {}
        self._load_symbols_info()

    def _load_symbols_info(self):
        """Ambil metadata koin (szDecimals) dari bursa Hyperliquid."""
        try:
            meta = self.info.meta()
            for s in meta.get("universe", []):
                name = s["name"]
                self.symbols_info[name] = {
                    'szDecimals': int(s.get('szDecimals', 3))
                }
            logger.info(f"Loaded Hyperliquid exchange info for {len(self.symbols_info)} symbols.")
        except Exception as e:
            logger.error(f"Failed to load Hyperliquid exchange info: {e}")

    def _to_coin(self, pair: str) -> str:
        """Konversi 'BTCUSDT' atau 'BTC/USDT' -> 'BTC' (format Hyperliquid)."""
        return pair.replace("USDT", "").replace("USDC", "").replace("/", "").replace(":", "")

    # ---------------------------------------------------------------------
    #  ACCOUNT
    # ---------------------------------------------------------------------

    def get_usdt_balance(self) -> float:
        """Ambil total USDC balance di Hyperliquid wallet (Withdrawable Perps + Spot USDC)."""
        if not self.account_address:
            return 0.0
        try:
            state = self.info.user_state(self.account_address)
            perp_withdrawable = float(state.get("withdrawable", 0.0))
            
            # Jika menggunakan Unified Account, dana utama mungkin berada di Spot USDC
            spot_usdc = 0.0
            try:
                spot_state = self.info.spot_user_state(self.account_address)
                for bal in spot_state.get("balances", []):
                    if bal.get("coin") == "USDC":
                        spot_usdc = float(bal.get("total", 0.0))
                        break
            except Exception as spot_err:
                logger.debug(f"Could not fetch spot balance: {spot_err}")

            return perp_withdrawable + spot_usdc
        except Exception as e:
            logger.error(f"Error getting Hyperliquid balance: {e}")
            return 0.0

    def get_realtime_price(self, pair: str) -> float:
        """Ambil mark/mid price terkini untuk coin perpetual."""
        coin = self._to_coin(pair)
        try:
            mids = self.info.all_mids()
            return float(mids.get(coin, 0.0))
        except Exception as e:
            logger.error(f"Error getting price for {pair}: {e}")
            return 0.0

    # ---------------------------------------------------------------------
    #  LEVERAGE
    # ---------------------------------------------------------------------

    def set_leverage(self, pair: str, leverage: int) -> bool:
        """Set leverage untuk pair tertentu (cross-margin secara default)."""
        coin = self._to_coin(pair)
        if not self.exchange:
            logger.error("Exchange client not initialized. Cannot set leverage.")
            return False
        try:
            # Set leverage menggunakan cross-margin (is_cross=True)
            self.exchange.update_leverage(leverage=leverage, name=coin, is_cross=True)
            logger.info(f"Hyperliquid leverage set: {coin} -> {leverage}x (Cross)")
            return True
        except Exception as e:
            logger.error(f"Error setting leverage for {coin}: {e}")
            return False

    # ---------------------------------------------------------------------
    #  ORDER PLACEMENT
    # ---------------------------------------------------------------------

    def place_market_order(self, pair: str, side: str, quantity: float) -> Optional[Dict[str, Any]]:
        """Place Market Order (menggunakan market_open / market_close)."""
        coin = self._to_coin(pair)
        is_buy = side.upper() == "BUY"
        qty = self._round_quantity(pair, quantity)

        if not self.exchange:
            logger.error("Exchange client not initialized.")
            return None

        try:
            logger.info(f"Placing Market order: {coin} {side} {qty}...")
            # market_open secara default menggunakan limit order IOC agresif (slippage 1%)
            order_result = self.exchange.market_open(coin, is_buy, qty, None, 0.01)
            
            if order_result.get("status") == "ok":
                statuses = order_result.get("response", {}).get("data", {}).get("statuses", [])
                if statuses:
                    status = statuses[0]
                    oid = None
                    if "resting" in status:
                        oid = status["resting"]["oid"]
                    elif "filled" in status:
                        oid = status["filled"]["oid"]
                    
                    if oid is not None:
                        logger.info(f"Market order placed: {coin} {side} {qty} -> ID: {oid}")
                        return {"orderId": str(oid), "raw": order_result}
            
            logger.error(f"Market order rejected or failed: {order_result}")
            return None
        except Exception as e:
            logger.error(f"Error placing market order {coin} {side}: {e}")
            return None

    def place_limit_order(self, pair: str, side: str, quantity: float, price: float) -> Optional[Dict[str, Any]]:
        """Place Limit Order."""
        coin = self._to_coin(pair)
        is_buy = side.upper() == "BUY"
        qty = self._round_quantity(pair, quantity)
        px = self._round_price(pair, price)

        if not self.exchange:
            logger.error("Exchange client not initialized.")
            return None

        try:
            logger.info(f"Placing Limit order: {coin} {side} {qty} @ {px}...")
            order_result = self.exchange.order(
                name=coin,
                is_buy=is_buy,
                sz=qty,
                limit_px=px,
                order_type={"limit": {"tif": "Gtc"}},
                reduce_only=False
            )
            
            if order_result.get("status") == "ok":
                statuses = order_result.get("response", {}).get("data", {}).get("statuses", [])
                if statuses:
                    status = statuses[0]
                    oid = None
                    if "resting" in status:
                        oid = status["resting"]["oid"]
                    elif "filled" in status:
                        oid = status["filled"]["oid"]
                    
                    if oid is not None:
                        logger.info(f"Limit order placed: {coin} {side} {qty} @ {px} -> ID: {oid}")
                        return {"orderId": str(oid), "raw": order_result}
            
            logger.error(f"Limit order rejected or failed: {order_result}")
            return None
        except Exception as e:
            logger.error(f"Error placing limit order {coin} {side} @ {px}: {e}")
            return None

    def place_stop_loss_order(self, pair: str, side: str, quantity: float, sl_price: float) -> Optional[Dict[str, Any]]:
        """Place Stop Loss trigger order (STOP_MARKET) untuk menutup posisi."""
        coin = self._to_coin(pair)
        # Stop Loss memiliki arah berlawanan dari posisi utama
        is_buy = not (side.upper() == "BUY")
        qty = self._round_quantity(pair, quantity)
        px = self._round_price(pair, sl_price)

        if not self.exchange:
            return None

        try:
            logger.info(f"Setting Stop Loss: {coin} @ {px}...")
            order_result = self.exchange.order(
                name=coin,
                is_buy=is_buy,
                sz=qty,
                limit_px=px,  # Digunakan sebagai trigger price / worst execution price
                order_type={
                    "trigger": {
                        "triggerPx": px,
                        "isMarket": True,
                        "tpsl": "sl"
                    }
                },
                reduce_only=True
            )
            
            if order_result.get("status") == "ok":
                statuses = order_result.get("response", {}).get("data", {}).get("statuses", [])
                if statuses:
                    status = statuses[0]
                    oid = None
                    if "resting" in status:
                        oid = status["resting"]["oid"]
                    elif "filled" in status:
                        oid = status["filled"]["oid"]
                    
                    if oid is not None:
                        logger.info(f"Stop Loss set: {coin} @ {px} -> ID: {oid}")
                        return {"orderId": str(oid), "raw": order_result}
            
            logger.error(f"Stop Loss setting failed: {order_result}")
            return None
        except Exception as e:
            logger.error(f"Error setting Stop Loss for {coin} @ {px}: {e}")
            return None

    def place_take_profit_order(self, pair: str, side: str, quantity: float, tp_price: float) -> Optional[Dict[str, Any]]:
        """Place Take Profit trigger order (TAKE_PROFIT_MARKET) untuk menutup posisi."""
        coin = self._to_coin(pair)
        is_buy = not (side.upper() == "BUY")
        qty = self._round_quantity(pair, quantity)
        px = self._round_price(pair, tp_price)

        if not self.exchange:
            return None

        try:
            logger.info(f"Setting Take Profit: {coin} @ {px}...")
            order_result = self.exchange.order(
                name=coin,
                is_buy=is_buy,
                sz=qty,
                limit_px=px,
                order_type={
                    "trigger": {
                        "triggerPx": px,
                        "isMarket": True,
                        "tpsl": "tp"
                    }
                },
                reduce_only=True
            )
            
            if order_result.get("status") == "ok":
                statuses = order_result.get("response", {}).get("data", {}).get("statuses", [])
                if statuses:
                    status = statuses[0]
                    oid = None
                    if "resting" in status:
                        oid = status["resting"]["oid"]
                    elif "filled" in status:
                        oid = status["filled"]["oid"]
                    
                    if oid is not None:
                        logger.info(f"Take Profit set: {coin} @ {px} -> ID: {oid}")
                        return {"orderId": str(oid), "raw": order_result}
            
            logger.error(f"Take Profit setting failed: {order_result}")
            return None
        except Exception as e:
            logger.error(f"Error setting Take Profit for {coin} @ {px}: {e}")
            return None

    # ---------------------------------------------------------------------
    #  ORDER STATUS
    # ---------------------------------------------------------------------

    def get_order_status(self, pair: str, order_id: str, is_algo: bool = False) -> Optional[Dict[str, Any]]:
        """Cek status order."""
        try:
            res = self.info.query_order_by_oid(self.account_address, int(order_id))
            if isinstance(res, dict) and res.get("status") == "order":
                order_info = res.get("order", {})
                raw_status = order_info.get("status", "").lower()
                
                # Normalisasi status agar kompatibel dengan state-machine bot
                mapped_status = "NEW"
                if raw_status == "filled":
                    mapped_status = "FILLED"
                elif raw_status in ("canceled", "marginCanceled", "selfTradeCanceled"):
                    mapped_status = "CANCELED"
                elif raw_status == "rejected":
                    mapped_status = "REJECTED"
                
                inner_order = order_info.get("order", {})
                return {
                    "status": mapped_status,
                    "avgPrice": float(inner_order.get("avgPx") or 0.0),
                    "raw": res
                }
            return None
        except Exception as e:
            logger.error(f"Error getting order status {pair} #{order_id}: {e}")
            return None

    def check_order_fill(self, pair: str, order_id: str) -> Optional[Dict[str, Any]]:
        """Cek apakah order sudah terisi dan ambil avgPrice."""
        status_dict = self.get_order_status(pair, order_id)
        if status_dict and status_dict.get("status") == "FILLED":
            return status_dict
        return None

    def cancel_order(self, pair: str, order_id: str, is_algo: bool = False) -> bool:
        """Cancel order yang belum terisi."""
        coin = self._to_coin(pair)
        if not self.exchange:
            return False
        try:
            cancel_result = self.exchange.cancel(coin, int(order_id))
            if cancel_result.get("status") == "ok":
                logger.info(f"Order canceled: {coin} #{order_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error canceling order {pair} #{order_id}: {e}")
            return False

    def get_position_pnl(self, pair: str) -> Optional[Dict[str, Any]]:
        """Ambil unrealized P/L untuk posisi tertentu."""
        positions = self.get_open_positions(pair)
        if positions:
            return positions[0]
        return None

    def get_open_positions(self, pair: Optional[str] = None) -> list:
        """Ambil semua posisi yang sedang terbuka."""
        if not self.account_address:
            return []
        try:
            state = self.info.user_state(self.account_address)
            open_positions = []
            
            for item in state.get("assetPositions", []):
                pos = item.get("position", {})
                size = float(pos.get("szi", 0.0))
                
                if size != 0.0:
                    coin = pos.get("coin")
                    mapped_pair = f"{coin}USDT"  # Kembalikan ke format pair internal DB
                    
                    if pair and mapped_pair != pair:
                        continue

                    # Ambil leverage. Di Hyperliquid, leverage disematkan di level metadata
                    leverage_val = 1
                    lev_info = pos.get("leverage")
                    if isinstance(lev_info, dict):
                        leverage_val = int(lev_info.get("value", 1))
                    elif lev_info:
                        leverage_val = int(lev_info)

                    open_positions.append({
                        "symbol": mapped_pair,
                        "positionAmt": size,
                        "entryPrice": float(pos.get("entryPx", 0.0)),
                        "markPrice": float(pos.get("markPx") or self.get_realtime_price(mapped_pair)),
                        "unRealizedProfit": float(pos.get("unrealizedPnl") or 0.0),
                        "leverage": leverage_val,
                        "entryPriceRaw": pos.get("entryPx"),
                    })
            return open_positions
        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return []

    def get_open_orders(self, pair: Optional[str] = None) -> list:
        """Ambil semua open orders (termasuk TP/SL)."""
        if not self.account_address:
            return []
        try:
            orders = self.info.open_orders(self.account_address)
            normalized_orders = []
            for o in orders:
                coin = o.get("coin")
                mapped_pair = f"{coin}USDT"
                
                if pair and mapped_pair != pair:
                    continue

                # Normalisasi agar properti sesuai dengan standard Binance order
                trigger_cond = o.get("triggerCondition", "").lower()
                is_trigger = o.get("isTrigger", False) or o.get("triggerPx", "0.0") != "0.0"
                
                mapped_type = "LIMIT"
                if is_trigger:
                    if "tp" in trigger_cond or "take profit" in trigger_cond or "take_profit" in trigger_cond:
                        mapped_type = "TAKE_PROFIT_MARKET"
                    elif "sl" in trigger_cond or "stop" in trigger_cond:
                        mapped_type = "STOP_MARKET"
                    else:
                        mapped_type = "STOP_MARKET"

                normalized_orders.append({
                    "orderId": str(o.get("oid")),
                    "symbol": mapped_pair,
                    "type": mapped_type,
                    "side": "BUY" if o.get("side") == "B" else "SELL",
                    "price": float(o.get("limitPx") or 0.0),
                    "stopPrice": float(o.get("triggerPx") or 0.0),
                    "origQty": float(o.get("sz") or 0.0),
                })
            return normalized_orders
        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return []

    def verify_tp_sl_set(self, pair: str) -> dict:
        """Verify bahwa TP dan SL sudah ter-set untuk pair ini."""
        try:
            open_orders = self.get_open_orders(pair)
            tp_orders = [o for o in open_orders if o.get("type") == "TAKE_PROFIT_MARKET"]
            sl_orders = [o for o in open_orders if o.get("type") == "STOP_MARKET"]

            return {
                "has_tp": len(tp_orders) > 0,
                "has_sl": len(sl_orders) > 0,
                "tp_orders": tp_orders,
                "sl_orders": sl_orders,
            }
        except Exception as e:
            logger.error(f"Error verifying TP/SL for {pair}: {e}")
            return {"has_tp": False, "has_sl": False, "tp_orders": [], "sl_orders": []}

    # ---------------------------------------------------------------------
    #  HELPER
    # ---------------------------------------------------------------------

    def _round_quantity(self, pair: str, quantity: float) -> float:
        """Round quantity berdasarkan szDecimals koin di Hyperliquid."""
        coin = self._to_coin(pair)
        info = self.symbols_info.get(coin)
        if not info:
            return round(quantity, 3)  # Fallback
        
        sz_decimals = info['szDecimals']
        
        # Hyperliquid menggunakan decimals untuk lot size
        factor = 10 ** sz_decimals
        rounded = math.floor(quantity * factor) / factor
        return round(rounded, sz_decimals)

    def _round_price(self, pair: str, price: float) -> float:
        """Round price berdasarkan aturan 5 significant figures dan szDecimals."""
        coin = self._to_coin(pair)
        info = self.symbols_info.get(coin)
        sz_decimals = info['szDecimals'] if info else 3
        
        # Aturan Hyperliquid: decimal places maksimal 6 - szDecimals
        max_decimals = max(0, 6 - sz_decimals)
        rounded = round(price, max_decimals)
        
        if rounded == 0.0:
            return 0.0

        # Batasi ke 5 significant figures
        magnitude = math.floor(math.log10(abs(rounded)))
        decimals_for_sig_figs = 5 - 1 - magnitude
        decimals_to_use = min(max_decimals, max(0, decimals_for_sig_figs))
        
        return round(rounded, decimals_to_use)
