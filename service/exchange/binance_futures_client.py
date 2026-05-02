"""
service/exchange/binance_futures_client.py

Wrapper untuk Binance Futures API menggunakan python-binance.
Mendukung testnet via BINANCE_TESTNET=true di .env.
"""

import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class BinanceFuturesClient:
    """
    Client untuk Binance USDT-M Futures.
    Semua order menggunakan USDT sebagai margin.
    """

    def __init__(self):
        from binance.client import Client
        from binance.exceptions import BinanceAPIException

        self._BinanceAPIException = BinanceAPIException

        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_SECRET_KEY", "")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

        self.client = Client(api_key, api_secret, testnet=testnet)
        self.testnet = testnet
        mode = "TESTNET" if testnet else "PRODUCTION"
        logger.info(f"BinanceFuturesClient initialized [{mode}]")

        # Cache untuk informasi presisi pair
        self.symbols_info = {}
        self._load_symbols_info()

    def _load_symbols_info(self):
        """Ambil informasi presisi (tickSize, stepSize) dari bursa."""
        try:
            info = self.client.futures_exchange_info()
            for s in info['symbols']:
                symbol = s['symbol']
                filters = {f['filterType']: f for f in s['filters']}
                
                self.symbols_info[symbol] = {
                    'tickSize': float(filters.get('PRICE_FILTER', {}).get('tickSize', 0.01)),
                    'stepSize': float(filters.get('LOT_SIZE', {}).get('stepSize', 0.001)),
                    'pricePrecision': int(s.get('pricePrecision', 2)),
                    'quantityPrecision': int(s.get('quantityPrecision', 3))
                }
            logger.info(f"Loaded exchange info for {len(self.symbols_info)} symbols.")
        except Exception as e:
            logger.error(f"Failed to load exchange info: {e}")

    # ---------------------------------------------------------------------
    #  ACCOUNT
    # ---------------------------------------------------------------------

    def get_usdt_balance(self) -> float:
        """Ambil available USDT balance di Futures wallet."""
        try:
            account = self.client.futures_account()
            for asset in account.get("assets", []):
                if asset["asset"] == "USDT":
                    return float(asset["availableBalance"])
            return 0.0
        except Exception as e:
            logger.error(f"Error getting USDT balance: {e}")
            return 0.0

    def get_realtime_price(self, pair: str) -> float:
        """Ambil harga mark price terkini untuk pair futures."""
        try:
            ticker = self.client.futures_mark_price(symbol=pair)
            return float(ticker["markPrice"])
        except Exception as e:
            logger.error(f"Error getting price for {pair}: {e}")
            return 0.0

    # ---------------------------------------------------------------------
    #  LEVERAGE
    # ---------------------------------------------------------------------

    def set_leverage(self, pair: str, leverage: int) -> bool:
        """Set leverage untuk pair tertentu."""
        try:
            self.client.futures_change_leverage(symbol=pair, leverage=leverage)
            logger.info(f"Leverage set: {pair} -> {leverage}x")
            return True
        except Exception as e:
            logger.error(f"Error setting leverage for {pair}: {e}")
            return False

    # ---------------------------------------------------------------------
    #  ORDER PLACEMENT
    # ---------------------------------------------------------------------

    def place_market_order(self, pair: str, side: str, quantity: float) -> Optional[Dict[str, Any]]:
        """
        Place Futures Market Order.

        Args:
            pair    : Contoh "BTCUSDT"
            side    : "BUY" atau "SELL"
            quantity: Jumlah kontrak (dalam base asset, misal BTC)

        Returns:
            Dict response dari Binance, atau None jika gagal.
        """
        try:
            from binance.enums import ORDER_TYPE_MARKET, SIDE_BUY, SIDE_SELL
            binance_side = SIDE_BUY if side.upper() == "BUY" else SIDE_SELL

            order = self.client.futures_create_order(
                symbol=pair,
                side=binance_side,
                type=ORDER_TYPE_MARKET,
                quantity=self._round_quantity(pair, quantity),
            )
            logger.info(f"Market order placed: {pair} {side} {quantity} -> ID: {order['orderId']}")
            return order
        except Exception as e:
            logger.error(f"Error placing market order {pair} {side}: {e}")
            return None

    def place_limit_order(self, pair: str, side: str, quantity: float, price: float) -> Optional[Dict[str, Any]]:
        """
        Place Futures Limit Order.

        Args:
            pair    : Contoh "BTCUSDT"
            side    : "BUY" atau "SELL"
            quantity: Jumlah kontrak
            price   : Harga limit (midpoint dari entry_zone)

        Returns:
            Dict response dari Binance, atau None jika gagal.
        """
        try:
            from binance.enums import ORDER_TYPE_LIMIT, SIDE_BUY, SIDE_SELL, TIME_IN_FORCE_GTC
            binance_side = SIDE_BUY if side.upper() == "BUY" else SIDE_SELL

            order = self.client.futures_create_order(
                symbol=pair,
                side=binance_side,
                type=ORDER_TYPE_LIMIT,
                quantity=self._round_quantity(pair, quantity),
                price=self._round_price(pair, price),
                timeInForce=TIME_IN_FORCE_GTC,  # Good Till Canceled
            )
            logger.info(f"Limit order placed: {pair} {side} {quantity} @ {price} -> ID: {order['orderId']}")
            return order
        except Exception as e:
            logger.error(f"Error placing limit order {pair} {side} @ {price}: {e}")
            return None

    def place_stop_loss_order(self, pair: str, side: str, quantity: float, sl_price: float) -> Optional[Dict[str, Any]]:
        """
        Place Stop Loss (STOP_MARKET) order untuk menutup posisi.
        Supports both testnet and mainnet.
        """
        try:
            from binance.enums import SIDE_BUY, SIDE_SELL
            close_side = SIDE_SELL if side.upper() == "BUY" else SIDE_BUY

            # Method 1: Try standard futures_create_order
            try:
                order = self.client.futures_create_order(
                    symbol=pair,
                    side=close_side,
                    type="STOP_MARKET",
                    stopPrice=self._round_price(pair, sl_price),
                    quantity=self._round_quantity(pair, quantity),
                    reduceOnly=True,
                    workingType="MARK_PRICE"
                )
                logger.info(f"Stop Loss set: {pair} @ {sl_price} -> ID: {order.get('orderId')}")
                return order
            except Exception as e1:
                logger.debug(f"Method 1 failed: {e1}")

            # Method 2: Try with priceProtect disabled
            try:
                order = self.client.futures_create_order(
                    symbol=pair,
                    side=close_side,
                    type="STOP_MARKET",
                    stopPrice=self._round_price(pair, sl_price),
                    quantity=self._round_quantity(pair, quantity),
                    reduceOnly=True,
                    workingType="MARK_PRICE",
                    priceProtect=False
                )
                logger.info(f"Stop Loss set (method 2): {pair} @ {sl_price} -> ID: {order.get('orderId')}")
                return order
            except Exception as e2:
                logger.debug(f"Method 2 failed: {e2}")

            # Method 3: Try with STOP limit order
            try:
                order = self.client.futures_create_order(
                    symbol=pair,
                    side=close_side,
                    type="STOP",
                    stopPrice=self._round_price(pair, sl_price),
                    quantity=self._round_quantity(pair, quantity),
                    reduceOnly=True
                )
                logger.info(f"Stop Loss set (method 3): {pair} @ {sl_price} -> ID: {order.get('orderId')}")
                return order
            except Exception as e3:
                logger.debug(f"Method 3 failed: {e3}")

            logger.warning(f"Could not set SL for {pair}: All methods failed")
            return None

        except Exception as e:
            logger.error(f"Error placing SL for {pair}: {e}")
            return None

    def place_take_profit_order(self, pair: str, side: str, quantity: float, tp_price: float) -> Optional[Dict[str, Any]]:
        """
        Place Take Profit (TAKE_PROFIT_MARKET) order untuk menutup posisi.
        Supports both testnet and mainnet.
        """
        try:
            from binance.enums import SIDE_BUY, SIDE_SELL
            close_side = SIDE_SELL if side.upper() == "BUY" else SIDE_BUY

            # Method 1: Try standard futures_create_order
            try:
                order = self.client.futures_create_order(
                    symbol=pair,
                    side=close_side,
                    type="TAKE_PROFIT_MARKET",
                    stopPrice=self._round_price(pair, tp_price),
                    quantity=self._round_quantity(pair, quantity),
                    reduceOnly=True,
                    workingType="MARK_PRICE"
                )
                logger.info(f"Take Profit set: {pair} @ {tp_price} -> ID: {order.get('orderId')}")
                return order
            except Exception as e1:
                logger.debug(f"Method 1 failed: {e1}")

            # Method 2: Try with priceProtect disabled
            try:
                order = self.client.futures_create_order(
                    symbol=pair,
                    side=close_side,
                    type="TAKE_PROFIT_MARKET",
                    stopPrice=self._round_price(pair, tp_price),
                    quantity=self._round_quantity(pair, quantity),
                    reduceOnly=True,
                    workingType="MARK_PRICE",
                    priceProtect=False
                )
                logger.info(f"Take Profit set (method 2): {pair} @ {tp_price} -> ID: {order.get('orderId')}")
                return order
            except Exception as e2:
                logger.debug(f"Method 2 failed: {e2}")

            # Method 3: Try with TAKE_PROFIT limit order
            try:
                order = self.client.futures_create_order(
                    symbol=pair,
                    side=close_side,
                    type="TAKE_PROFIT",
                    stopPrice=self._round_price(pair, tp_price),
                    quantity=self._round_quantity(pair, quantity),
                    reduceOnly=True
                )
                logger.info(f"Take Profit set (method 3): {pair} @ {tp_price} -> ID: {order.get('orderId')}")
                return order
            except Exception as e3:
                logger.debug(f"Method 3 failed: {e3}")

            logger.warning(f"Could not set TP for {pair}: All methods failed")
            return None

        except Exception as e:
            logger.error(f"Error placing TP for {pair}: {e}")
            return None

    # ---------------------------------------------------------------------
    #  ORDER STATUS
    # ---------------------------------------------------------------------

    def get_order_status(self, pair: str, order_id: str) -> Optional[Dict[str, Any]]:
        """Cek status order. Returns dict dengan field 'status'."""
        try:
            return self.client.futures_get_order(symbol=pair, orderId=int(order_id))
        except Exception as e:
            logger.error(f"Error getting order status {pair} #{order_id}: {e}")
            return None

    def check_order_fill(self, pair: str, order_id: str) -> Optional[Dict[str, Any]]:
        """Cek apakah order sudah terisi dan ambil avgPrice."""
        try:
            order = self.client.futures_get_order(symbol=pair, orderId=int(order_id))
            if order and order.get("status") in ("FILLED", "PARTIALLY_FILLED"):
                return order
            return None
        except Exception as e:
            logger.error(f"Error checking order fill {pair} #{order_id}: {e}")
            return None

    def cancel_order(self, pair: str, order_id: str) -> bool:
        """Cancel order yang belum terisi."""
        try:
            self.client.futures_cancel_order(symbol=pair, orderId=int(order_id))
            logger.info(f"Order canceled: {pair} #{order_id}")
            return True
        except Exception as e:
            logger.error(f"Error canceling order {pair} #{order_id}: {e}")
            return False

    def get_position_pnl(self, pair: str) -> Optional[Dict[str, Any]]:
        """Ambil unrealized P/L untuk posisi tertentu."""
        try:
            positions = self.client.futures_position_information(symbol=pair)
            for p in positions:
                if float(p.get("positionAmt", 0)) != 0:
                    return p
            return None
        except Exception as e:
            logger.error(f"Error getting position PNL for {pair}: {e}")
            return None

    def get_open_positions(self, pair: Optional[str] = None) -> list:
        """Ambil semua posisi yang sedang terbuka."""
        try:
            positions = self.client.futures_position_information(symbol=pair)
            return [p for p in positions if float(p.get("positionAmt", 0)) != 0]
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    def get_open_orders(self, pair: Optional[str] = None) -> list:
        """Ambil semua open orders (termasuk TP/SL)."""
        try:
            return self.client.futures_get_open_orders(symbol=pair)
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
        """Round quantity berdasarkan stepSize bursa."""
        info = self.symbols_info.get(pair)
        if not info:
            return round(quantity, 3)  # Fallback
        
        step_size = info['stepSize']
        precision = info['quantityPrecision']
        
        # Kalkulasi berdasarkan stepSize (paling akurat untuk Futures)
        rounded = (quantity // step_size) * step_size
        return round(rounded, precision)

    def _round_price(self, pair: str, price: float) -> float:
        """Round price berdasarkan tickSize bursa."""
        info = self.symbols_info.get(pair)
        if not info:
            return round(price, 2)  # Fallback
            
        tick_size = info['tickSize']
        precision = info['pricePrecision']
        
        rounded = round(price / tick_size) * tick_size
        return round(rounded, precision)
