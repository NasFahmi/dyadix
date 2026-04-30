"""
service/trade/order_executor.py

Mengeksekusi order di Binance Futures berdasarkan output Decision LLM.
Menghitung quantity berdasarkan risk management settings,
parse entry_zone menjadi midpoint, lalu place order.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    Eksekutor order Binance Futures.
    Dipanggil oleh LoopScheduler setelah Decision LLM menghasilkan BUY/SELL.
    """

    def __init__(self):
        from config.settings import get_config
        from service.exchange.binance_futures_client import BinanceFuturesClient

        config = get_config()
        rm = config.get("risk_management", {})

        self.risk_pct = rm.get("risk_per_trade_pct", 1.0)
        self.leverage = rm.get("leverage", 10)

        self.exchange = BinanceFuturesClient()

    def execute(
        self,
        pair: str,
        decision: Dict[str, Any],
        realtime_price: float,
        decision_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Eksekusi order berdasarkan decision LLM.

        Args:
            pair          : Contoh "BTCUSDT"
            decision      : Output dict dari Decision LLM
            realtime_price: Harga terkini untuk kalkulasi quantity
            decision_id   : UUID record di tabel decisions (untuk FK)

        Returns:
            trade_id (UUID string) jika berhasil, None jika gagal.
        """
        action = decision.get("decision", "WAIT")
        if action not in ("BUY", "SELL"):
            logger.info(f"  ↳ {pair}: Action={action}, tidak ada order yang dieksekusi.")
            return None

        execution_type = decision.get("execution_type", "LIMIT")

        # ── Parse entry, SL, TP ──────────────────────────────────────
        from utils.entry_calculator import parse_entry_midpoint, parse_price

        entry_zone_str = decision.get("entry_zone", "")
        sl_str = decision.get("stop_loss", "")
        tp_str = decision.get("target", "")

        entry_price_planned = parse_entry_midpoint(entry_zone_str, realtime_price)
        sl_price = parse_price(sl_str, fallback=0.0)
        tp_price = parse_price(tp_str, fallback=0.0)

        if sl_price == 0.0 or tp_price == 0.0:
            logger.error(f"  ✘ {pair}: SL atau TP tidak valid — {sl_str} / {tp_str}. Order dibatalkan.")
            return None

        # ── Hitung quantity berdasarkan risk management ───────────────
        balance = self.exchange.get_usdt_balance()
        if balance <= 0:
            logger.error(f"  ✘ {pair}: Balance USDT = 0. Order dibatalkan.")
            return None

        risk_usd = balance * (self.risk_pct / 100.0)
        nominal = risk_usd * self.leverage
        quantity = nominal / realtime_price

        logger.info(
            f"  💰 {pair} Risk Calc: Balance=${balance:.2f}, Risk={self.risk_pct}% "
            f"→ ${risk_usd:.2f} x {self.leverage}x = ${nominal:.2f} "
            f"→ Qty={quantity:.5f}"
        )

        # ── Set leverage ─────────────────────────────────────────────
        self.exchange.set_leverage(pair, self.leverage)

        # ── Place order ──────────────────────────────────────────────
        order_response = None

        if execution_type == "MARKET":
            logger.info(f"  ⚡ {pair}: Placing MARKET {action} order...")
            order_response = self.exchange.place_market_order(pair, action, quantity)
        else:
            logger.info(f"  📋 {pair}: Placing LIMIT {action} order @ {entry_price_planned}...")
            order_response = self.exchange.place_limit_order(pair, action, quantity, entry_price_planned)

        if not order_response:
            logger.error(f"  ✘ {pair}: Order gagal ditempatkan.")
            return None

        exchange_order_id = str(order_response.get("orderId", ""))
        actual_entry = float(order_response.get("avgPrice", 0) or entry_price_planned)

        # ── Set SL & TP ──────────────────────────────────────────────
        self.exchange.place_stop_loss_order(pair, action, quantity, sl_price)
        self.exchange.place_take_profit_order(pair, action, quantity, tp_price)

        # ── Simpan ke database ────────────────────────────────────────
        trade_id = self._save_trade(
            pair=pair,
            decision_id=decision_id,
            exchange_order_id=exchange_order_id,
            side=action,
            entry_price=actual_entry,
            entry_price_planned=entry_price_planned,
            sl_price=sl_price,
            tp_price=tp_price,
            quantity=quantity,
        )

        logger.info(f"  ✅ {pair}: Order placed → trade_id={trade_id}, exchange_id={exchange_order_id}")
        return trade_id

    def _save_trade(
        self,
        pair: str,
        decision_id: Optional[str],
        exchange_order_id: str,
        side: str,
        entry_price: float,
        entry_price_planned: float,
        sl_price: float,
        tp_price: float,
        quantity: float,
    ) -> str:
        """Simpan record trade baru ke PostgreSQL."""
        from data.database import SessionFactory
        from data.models import TradeRecord

        trade = TradeRecord(
            pair=pair,
            decision_id=decision_id,
            exchange_order_id=exchange_order_id,
            side=side,
            status="RUNNING",
            entry_price=entry_price,
            entry_price_planned=entry_price_planned,
            stop_loss_price=sl_price,
            target_price=tp_price,
            quantity=quantity,
            leverage=self.leverage,
            opened_at=datetime.utcnow(),
        )

        with SessionFactory() as session:
            session.add(trade)
            session.commit()
            session.refresh(trade)
            return str(trade.id)
