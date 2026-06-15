import os
import sys
import time
import json
import logging
import threading
import asyncio
import collections
from typing import Dict, Any, List, Optional
import websockets

logger = logging.getLogger(__name__)

class HyperliquidMicrostructureCollector:
    """
    Background collector yang berlangganan WebSocket Hyperliquid (trades, L2 book, liquidations)
    dan menyediakan metrik microstructure (CVD, Imbalance, Whale activity, Liquidations)
    secara real-time melalui in-memory sliding windows.
    """
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Implementasi Singleton Pattern."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(HyperliquidMicrostructureCollector, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
            
        from config.settings import get_config
        config = get_config()
        
        # Load target pairs dari config
        trading_config = config.get("trading", {})
        self.pairs: List[str] = trading_config.get("pairs") or ["BTCUSDC"]
        
        # Ambil list valid coins dari universe Hyperliquid untuk mencegah disconnect websocket
        from hyperliquid.info import Info
        from hyperliquid.utils import constants
        testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"
        base_url = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL
        info = Info(base_url, skip_ws=True)
        valid_coins = set()
        try:
            meta = info.meta()
            valid_coins = {s["name"] for s in meta.get("universe", [])}
        except Exception as e:
            logger.error(f"Failed to fetch Hyperliquid universe for WebSocket subscription: {e}")

        # Konversi ke format koin Hyperliquid (e.g. BTCUSDC -> BTC)
        all_coins = [self._to_coin(p) for p in self.pairs]
        if valid_coins:
            self.coins = [c for c in all_coins if c in valid_coins]
            ignored = [c for c in all_coins if c not in valid_coins]
            if ignored:
                logger.warning(f"Ignoring coins for WebSocket subscription because they do not exist in the Hyperliquid universe: {ignored}")
        else:
            self.coins = all_coins
        
        # Buffers thread-safe (1 jam lookback maksimal)
        self.trades_buffers = {coin: collections.deque() for coin in self.coins}
        self.liquidation_buffers = {coin: collections.deque() for coin in self.coins}
        self.orderbooks = {coin: {"bids": [], "asks": [], "timestamp": 0.0} for coin in self.coins}
        
        self._running = False
        self._thread = None
        self._loop = None
        self._active_ws = None
        
        self._data_lock = threading.Lock()
        self._initialized = True
        logger.info(f"HyperliquidMicrostructureCollector initialized for coins: {self.coins}")

    def _to_coin(self, pair: str) -> str:
        """Helper untuk konversi BTCUSDC/BTCUSDT -> BTC."""
        return pair.replace("USDT", "").replace("USDC", "").replace("/", "").replace(":", "")

    # ─────────────────────────────────────────────────────────────────────
    #  THREAD CONTROL
    # ─────────────────────────────────────────────────────────────────────

    def start(self):
        """Mulai WebSocket listener thread jika belum berjalan."""
        with self._data_lock:
            if self._running:
                logger.info("Microstructure thread already running.")
                return
                
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="Dyadix-Microstructure")
            self._thread.start()
            logger.info("Microstructure collector thread started.")

    def stop(self):
        """Hentikan WebSocket connection dan stop event loop."""
        with self._data_lock:
            if not self._running:
                return
                
            logger.info("Stopping microstructure collector...")
            self._running = False
            
            # Close active websocket connection
            if self._active_ws and self._loop:
                asyncio.run_coroutine_threadsafe(self._active_ws.close(), self._loop)
                
            # Cancel all pending tasks and stop the loop safely
            if self._loop:
                def cancel_all():
                    try:
                        tasks = asyncio.all_tasks(self._loop)
                        for task in tasks:
                            task.cancel()
                    except Exception as ex:
                        logger.debug(f"Error cancelling tasks: {ex}")
                    self._loop.stop()
                self._loop.call_soon_threadsafe(cancel_all)
                
            if self._thread:
                self._thread.join(timeout=5)
                self._thread = None
                
            self._loop = None
            self._active_ws = None
            logger.info("Microstructure collector stopped successfully.")

    def _run_loop(self):
        """Entrypoint untuk background thread asyncio loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main_ws())
        except Exception as e:
            logger.error(f"Error in microstructure asyncio run loop: {e}")
        finally:
            self._loop.close()

    async def _main_ws(self):
        """Fungsi utama WebSocket listener dengan auto-reconnect."""
        testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"
        url = "wss://api.hyperliquid-testnet.xyz/ws" if testnet else "wss://api.hyperliquid.xyz/ws"
        
        backoff = 1.0
        while self._running:
            try:
                logger.info(f"Connecting to Hyperliquid WebSocket: {url} ...")
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as websocket:
                    self._active_ws = websocket
                    backoff = 1.0  # reset backoff on success
                    logger.info("Hyperliquid WebSocket connected successfully!")
                    
                    # 1. Subscribe to liquidations
                    await websocket.send(json.dumps({
                        "method": "subscribe",
                        "subscription": {"type": "liquidations"}
                    }))
                    
                    # 2. Subscribe to trades and l2Book for each coin
                    for coin in self.coins:
                        await websocket.send(json.dumps({
                            "method": "subscribe",
                            "subscription": {"type": "trades", "coin": coin}
                        }))
                        await websocket.send(json.dumps({
                            "method": "subscribe",
                            "subscription": {"type": "l2Book", "coin": coin}
                        }))
                        
                    logger.info(f"Subscribed to trades, l2Book, and liquidations for coins: {self.coins}")
                    
                    # Listen for incoming messages
                    async for message in websocket:
                        if not self._running:
                            break
                        self._process_message(message)
                        
            except websockets.exceptions.ConnectionClosed as ce:
                logger.warning(f"Hyperliquid WebSocket connection closed: {ce}. Reconnecting in {backoff:.1f}s...")
            except Exception as e:
                logger.error(f"Hyperliquid WebSocket connection error: {e}. Reconnecting in {backoff:.1f}s...")
                
            if self._running:
                await asyncio.sleep(backoff)
                backoff = min(60.0, backoff * 2.0)

    # ─────────────────────────────────────────────────────────────────────
    #  MESSAGE PROCESSOR
    # ─────────────────────────────────────────────────────────────────────

    def _process_message(self, message_str: str):
        """Parsing dan routing pesan websocket ke buffer koin masing-masing."""
        try:
            msg = json.loads(message_str)
            channel = msg.get("channel")
            if not channel:
                return

            data = msg.get("data")
            if not data:
                return

            if channel == "trades":
                # Format trades: [{"coin": "BTC", "side": "B", "px": "64000.0", "sz": "0.1", "time": 1690000000000}]
                if isinstance(data, list):
                    for t in data:
                        coin = t.get("coin")
                        if coin in self.trades_buffers:
                            with self._data_lock:
                                self.trades_buffers[coin].append({
                                    "time": float(t.get("time", 0)) / 1000.0,
                                    "price": float(t.get("px", 0)),
                                    "size": float(t.get("sz", 0)),
                                    "side": "buy" if t.get("side") == "B" else "sell"
                                })
                                # Purge data > 1 jam
                                cutoff = time.time() - 3600
                                while self.trades_buffers[coin] and self.trades_buffers[coin][0]["time"] < cutoff:
                                    self.trades_buffers[coin].popleft()

            elif channel == "l2Book":
                # Format l2Book: {"coin": "BTC", "levels": [[bids], [asks]]}
                coin = data.get("coin")
                if coin in self.orderbooks:
                    levels = data.get("levels", [])
                    if len(levels) >= 2:
                        bids = [{"px": float(x["px"]), "sz": float(x["sz"])} for x in levels[0]]
                        asks = [{"px": float(x["px"]), "sz": float(x["sz"])} for x in levels[1]]
                        with self._data_lock:
                            self.orderbooks[coin] = {
                                "bids": bids,
                                "asks": asks,
                                "timestamp": time.time()
                            }

            elif channel == "liquidations":
                # Format liquidations: {"liquidations": [{"coin": "BTC", "isBuy": true/false, "sz": "0.1", "px": "64000.0"}]}
                liq_list = []
                if isinstance(data, list):
                    liq_list = data
                elif isinstance(data, dict):
                    if "liquidations" in data:
                        liq_list = data.get("liquidations", [])
                    else:
                        liq_list = [data]
                        
                for liq in liq_list:
                    coin = liq.get("coin")
                    if coin in self.liquidation_buffers:
                        with self._data_lock:
                            self.liquidation_buffers[coin].append({
                                "time": time.time(),
                                "price": float(liq.get("px", 0)),
                                "size": float(liq.get("sz", 0)),
                                # isBuy = true berarti liquidator BUY (artinya Short position dilikuidasi)
                                "is_short_liq": bool(liq.get("isBuy", False))
                            })
                            # Purge data > 1 jam
                            cutoff = time.time() - 3600
                            while self.liquidation_buffers[coin] and self.liquidation_buffers[coin][0]["time"] < cutoff:
                                self.liquidation_buffers[coin].popleft()
        except Exception as e:
            logger.debug(f"Error processing microstructure websocket message: {e}")

    # ─────────────────────────────────────────────────────────────────────
    #  METRICS GETTERS (Thread-Safe)
    # ─────────────────────────────────────────────────────────────────────

    def get_metrics(self, pair: str) -> Dict[str, Any]:
        """
        Ambil seluruh metrik microstructure lengkap untuk satu pair.
        Mencakup CVD, Imbalance, Whale Activity, Liquidation, dan Aggressive Flow.
        """
        coin = self._to_coin(pair)
        
        # Default empty output jika koin tidak didukung
        if coin not in self.coins:
            return {
                "cvd_5m": 0.0, "cvd_15m": 0.0, "cvd_1h": 0.0,
                "orderbook_imbalance_top5": 0.0,
                "whale_buy_count_15m": 0, "whale_sell_count_15m": 0,
                "whale_buy_vol_usd_15m": 0.0, "whale_sell_vol_usd_15m": 0.0,
                "long_liquidations_usd_15m": 0.0, "short_liquidations_usd_15m": 0.0,
                "avg_trade_size_usd_5m": 0.0, "trades_per_minute_5m": 0.0,
                "timestamp": time.time()
            }
            
        now = time.time()
        
        with self._data_lock:
            # 1. Filter trades berdasarkan window
            trades_5m = [t for t in self.trades_buffers[coin] if now - t["time"] <= 300]
            trades_15m = [t for t in self.trades_buffers[coin] if now - t["time"] <= 900]
            trades_1h = list(self.trades_buffers[coin]) # buffer sudah terpotong max 1 jam
            
            # 2. Filter liquidations berdasarkan window
            liqs_15m = [l for l in self.liquidation_buffers[coin] if now - l["time"] <= 900]
            
            # 3. Hitung CVD (USD Volume Delta = Price * Size)
            cvd_5m = sum(t["price"] * t["size"] if t["side"] == "buy" else -t["price"] * t["size"] for t in trades_5m)
            cvd_15m = sum(t["price"] * t["size"] if t["side"] == "buy" else -t["price"] * t["size"] for t in trades_15m)
            cvd_1h = sum(t["price"] * t["size"] if t["side"] == "buy" else -t["price"] * t["size"] for t in trades_1h)
            
            # 4. Hitung Orderbook Imbalance (Top 5 Level)
            imbalance = 0.0
            ob = self.orderbooks[coin]
            bids = ob["bids"][:5]
            asks = ob["asks"][:5]
            
            if bids and asks:
                bids_sum = sum(b["sz"] for b in bids)
                asks_sum = sum(a["sz"] for a in asks)
                if (bids_sum + asks_sum) > 0:
                    imbalance = (bids_sum - asks_sum) / (bids_sum + asks_sum)
            
            # 5. Hitung Whale Activity (Threshold: >= $20,000 USD value per trade)
            whale_threshold = 20000.0  # Lebih sensitif untuk modal kecil, bisa mendeteksi whale kecil/medium
            whale_buys = [t for t in trades_15m if t["side"] == "buy" and (t["price"] * t["size"]) >= whale_threshold]
            whale_sells = [t for t in trades_15m if t["side"] == "sell" and (t["price"] * t["size"]) >= whale_threshold]
            
            whale_buy_count = len(whale_buys)
            whale_sell_count = len(whale_sells)
            whale_buy_vol = sum(t["price"] * t["size"] for t in whale_buys)
            whale_sell_vol = sum(t["price"] * t["size"] for t in whale_sells)
            
            # 6. Hitung Liquidations
            # is_short_liq = True berarti Short dilikuidasi (terjadi BUY di market)
            # is_short_liq = False berarti Long dilikuidasi (terjadi SELL di market)
            long_liqs = [l for l in liqs_15m if not l["is_short_liq"]]
            short_liqs = [l for l in liqs_15m if l["is_short_liq"]]
            
            long_liq_usd = sum(l["price"] * l["size"] for l in long_liqs)
            short_liq_usd = sum(l["price"] * l["size"] for l in short_liqs)
            
            # 7. Hitung Aggressive Flow (Kecepatan dan volume transaksi market)
            avg_trade_size = 0.0
            trades_count = len(trades_5m)
            if trades_count > 0:
                avg_trade_size = sum(t["price"] * t["size"] for t in trades_5m) / trades_count
            trades_per_min = trades_count / 5.0
            
            return {
                "cvd_5m_usd": round(cvd_5m, 2),
                "cvd_15m_usd": round(cvd_15m, 2),
                "cvd_1h_usd": round(cvd_1h, 2),
                "orderbook_imbalance_top5": round(imbalance, 4),
                "whale_buy_count_15m": whale_buy_count,
                "whale_sell_count_15m": whale_sell_count,
                "whale_buy_vol_usd_15m": round(whale_buy_vol, 2),
                "whale_sell_vol_usd_15m": round(whale_sell_vol, 2),
                "long_liquidations_usd_15m": round(long_liq_usd, 2),
                "short_liquidations_usd_15m": round(short_liq_usd, 2),
                "avg_trade_size_usd_5m": round(avg_trade_size, 2),
                "trades_per_minute_5m": round(trades_per_min, 1),
                "timestamp": now
            }
