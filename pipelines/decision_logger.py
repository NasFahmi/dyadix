"""
pipelines/decision_logger.py

Menyimpan log decision dan signal ke file JSON harian.
Format: data/logs/decisions/decisions_YYYYMMDD.json

Juga melacak cooldown per pair agar tidak spam LLM call.
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class DecisionLogger:
    """
    Logger untuk semua decision dan signal detection.
    Satu file per hari, append-style (list of entries).
    """

    LOG_DIR = "data/logs/decisions"

    def __init__(self, cooldown_seconds: int = 900):
        """
        Parameters:
            cooldown_seconds: Berapa detik setelah LLM call sebelum pair
                              bisa dievaluasi ulang. Default 900 (15 menit).
        """
        self.cooldown_seconds = cooldown_seconds
        self._last_llm_call: Dict[str, datetime] = {}  # {pair: datetime}
        os.makedirs(self.LOG_DIR, exist_ok=True)

    def log_decision(
        self, pair: str, signal_result: Dict, decision: Dict, full_context: Optional[Dict] = None
    ) -> None:
        """Log ketika LLM dipanggil dan memberikan decision."""
        now = datetime.utcnow()
        self._last_llm_call[pair] = now

        entry = {
            "type": "DECISION",
            "timestamp": now.isoformat(),
            "pair": pair,
            "signal": {
                "confidence": signal_result.get("confidence"),
                "reasons": signal_result.get("reasons"),
                "suggested_bias": signal_result.get("suggested_bias"),
                "signal_type": signal_result.get("signal_type"),
            },
            "decision": {
                "action": decision.get("decision"),
                "confidence": decision.get("confidence"),
                "bias": decision.get("bias"),
                "entry_zone": decision.get("entry_zone"),
                "target": decision.get("target"),
                "stop_loss": decision.get("stop_loss"),
                "risk_reward": decision.get("risk_reward"),
                "reason": decision.get("reason"),
            },
        }

        self._append_entry(entry)

        # ── Save to Database ──────────────────────────────────────
        try:
            from db.database import SessionLocal
            from db.models import Decision, Trade, ActionType, TradeStatus
            
            db = SessionLocal()
            try:
                # Prepare rich context for autopsy
                autopsy_context = {
                    "signal_detector_result": entry.get("signal"),
                    "technical": full_context.get("technical") if full_context else None,
                    "sentiment": full_context.get("sentiment") if full_context else None,
                    "market_snapshot": full_context.get("market_snapshot") if full_context else None,
                    "candle_summary": full_context.get("candle_summary") if full_context else None,
                    "derivatives": full_context.get("derivatives") if full_context else None,
                    "liquidity": full_context.get("liquidity") if full_context else None,
                    "rr_calculation": decision.get("rr_calculation")
                }

                # 1. Save Decision
                new_decision = Decision(
                    pair=pair,
                    action=ActionType(decision.get("decision", "HOLD")),
                    confidence=float(decision.get("confidence", 0)),
                    stop_loss=float(decision.get("stop_loss")) if decision.get("stop_loss") and str(decision.get("stop_loss")).replace('.','',1).isdigit() else None,
                    take_profit=float(decision.get("target")) if decision.get("target") and str(decision.get("target")).replace('.','',1).isdigit() else None,
                    entry_reason=decision.get("reason"),
                    llm_context=autopsy_context # Log rich context for autopsy
                )
                db.add(new_decision)
                db.flush() # Get ID for FK
                
                # 2. If Decision is BUY/SELL, create a RUNNING Trade
                if new_decision.action in [ActionType.BUY, ActionType.SELL]:
                    new_trade = Trade(
                        decision_id=new_decision.id,
                        pair=pair,
                        status=TradeStatus.RUNNING,
                        entry_price=0.0, # Will be updated by execution service later
                        opened_at=now
                    )
                    db.add(new_trade)
                    logger.info(f"🚀 New RUNNING trade created for {pair}")

                db.commit()
                logger.info("✅ Decision with rich context saved to PostgreSQL")
            except Exception as db_err:
                logger.error(f"Failed to save decision to DB: {db_err}")
                db.rollback()
            finally:
                db.close()
        except ImportError:
            logger.warning("Database module not found, skipping DB save")

        logger.info(
            f"📝 Decision logged: {pair} → {decision.get('decision')} "
            f"(confidence {decision.get('confidence')})"
        )

    def log_telegram_sent(self, pair: str, signal_result: Dict, decision: Dict, realtime_price: float = 0.0) -> None:
        """Log decision yang berhasil dikirim ke Telegram (file terpisah) dengan format sedetail Telegram."""
        now = datetime.utcnow()
        entry = {
            "type": "TELEGRAM_SENT",
            "timestamp": now.isoformat(),
            "pair": pair,
            "signal": {
                "type": signal_result.get("signal_type", "N/A"),
                "bias": signal_result.get("suggested_bias", "N/A"),
                "confidence": signal_result.get("confidence", 0),
                "bull_score": signal_result.get("scores", {}).get("bullish", 0),
                "bear_score": signal_result.get("scores", {}).get("bearish", 0),
                "reasons": signal_result.get("reasons", [])
            },
            "decision": {
                "action": decision.get("decision", "N/A"),
                "confidence": decision.get("confidence", "N/A"),
                "bias": decision.get("bias", "N/A"),
                "timeframe": decision.get("recommended_timeframe", "N/A"),
                "execution_type": decision.get("execution_type", "N/A"),
                "realtime_price": realtime_price,
                "entry_zone": decision.get("entry_zone", "N/A"),
                "target": decision.get("target", "N/A"),
                "stop_loss": decision.get("stop_loss", "N/A"),
                "risk_reward": decision.get("risk_reward", "N/A"),
                "expected_move": decision.get("expected_move", "N/A"),
                "reason": decision.get("reason", "N/A"),
                "invalidated_if": decision.get("invalidated_if", "N/A"),
                "key_risks": decision.get("key_risks", [])
            }
        }

        date_str = now.strftime("%Y%m%d")
        filepath = os.path.join(self.LOG_DIR, f"telegram_sent_{date_str}.json")

        entries = []
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    entries = json.load(f)
            except Exception:
                pass

        entries.append(entry)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"Failed to write telegram sent log: {e}")

    def log_skip(self, pair: str, signal_result: Dict) -> None:
        """Log ketika pair di-skip karena signal terlalu lemah."""
        logger.debug(
            f"⏭️ Skipped {pair} - Confidence: {signal_result.get('confidence')} "
            f"(Reason: {signal_result.get('reasons')})"
        )

    def log_cooldown_skip(self, pair: str) -> None:
        """Log ketika pair di-skip karena masih dalam cooldown."""
        logger.debug(f"⏳ Skipped {pair} - Still in cooldown")

    def is_in_cooldown(self, pair: str) -> bool:
        """Cek apakah pair masih dalam cooldown period setelah LLM call terakhir."""
        last_call = self._last_llm_call.get(pair)
        if last_call is None:
            return False

        elapsed = (datetime.utcnow() - last_call).total_seconds()
        return elapsed < self.cooldown_seconds

    def get_cooldown_remaining(self, pair: str) -> float:
        """Return sisa waktu cooldown dalam detik. 0 jika tidak ada cooldown."""
        last_call = self._last_llm_call.get(pair)
        if last_call is None:
            return 0.0

        elapsed = (datetime.utcnow() - last_call).total_seconds()
        remaining = self.cooldown_seconds - elapsed
        return max(0.0, remaining)

    def get_today_summary(self) -> Dict:
        """Baca log hari ini dan return ringkasan."""
        entries = self._read_today_entries()

        decisions = [e for e in entries if e.get("type") == "DECISION"]
        skips = [e for e in entries if e.get("type") == "SKIP"]
        cooldowns = [e for e in entries if e.get("type") == "COOLDOWN_SKIP"]

        return {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "total_entries": len(entries),
            "decisions": len(decisions),
            "skips": len(skips),
            "cooldown_skips": len(cooldowns),
            "llm_calls": len(decisions),
            "pairs_with_decisions": list(
                set(e.get("pair") for e in decisions)
            ),
        }

    # ─────────────────────────────────────────────────────────────────────
    #  PRIVATE HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def _get_today_filepath(self) -> str:
        """Return path file log hari ini."""
        date_str = datetime.utcnow().strftime("%Y%m%d")
        return os.path.join(self.LOG_DIR, f"decisions_{date_str}.json")

    def _append_entry(self, entry: Dict) -> None:
        """Append satu entry ke file log hari ini."""
        filepath = self._get_today_filepath()

        entries = self._read_today_entries()
        entries.append(entry)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"Failed to write decision log: {e}")

    def _read_today_entries(self) -> list:
        """Baca semua entry dari file log hari ini."""
        filepath = self._get_today_filepath()

        if not os.path.exists(filepath):
            return []

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return []
