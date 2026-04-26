import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
import pandas as pd

from llm.factory import get_decision_llm # Using decision LLM factory or creating a specific one
from llm.system_prompt import SystemPrompt
from db.repository.trade_repository import TradeRepository
from service.market.market_service import MarketService

logger = logging.getLogger(__name__)

class AutopsyEngine:
    """
    Forensic analysis engine for failed trades.
    """

    def __init__(self):
        self.market_service = MarketService()
        self.repo = TradeRepository()

    def run_autopsy(self, trade):
        """
        Execute full autopsy for a closed loss trade.
        :param trade: Trade model instance
        """
        try:
            logger.info(f"🔎 Starting Forensic Autopsy for {trade.pair} (ID: {trade.id})")
            
            # 1. Collect Data
            payload = self._collect_data(trade)
            
            # 2. Call LLM
            analysis = self._call_llm(payload)
            
            # 3. Save to DB
            if analysis:
                self.repo.update_autopsy(trade.id, analysis)
                logger.info(f"✅ Autopsy completed and saved for {trade.pair}")
                return analysis
            
            return None
        except Exception as e:
            logger.error(f"Failed to run autopsy for trade {trade.id}: {e}", exc_info=True)
            return None

    def _collect_data(self, trade) -> Dict:
        """Aggregate all necessary data for the autopsy prompt."""
        decision = trade.decision
        rationale = decision.llm_context if decision else {}
        
        # Calculate duration
        duration = trade.closed_at - trade.opened_at
        duration_str = str(duration).split('.')[0] # HH:MM:SS
        
        # Collect Price Action (Candles)
        # We take M5 and M15
        price_action = self._fetch_price_action(trade)
        
        # Collect External Events (News)
        external_events = self._fetch_external_events(trade)
        
        # BTC Correlation (Mock for now, can be improved)
        btc_corr = self._fetch_btc_correlation(trade)

        payload = {
            "trade_info": {
                "pair": trade.pair,
                "side": "LONG" if decision.action.value == "BUY" else "SHORT",
                "entry_price": trade.entry_price,
                "sl_price": decision.stop_loss,
                "exit_price": trade.realized_pnl, # Actually exit price should be added to model
                "duration": duration_str,
                "original_plan": decision.entry_reason,
                "original_decision_rationale": rationale
            },
            "market_behavior": {
                "price_action_during_trade": price_action,
                "btc_correlation": btc_corr,
                "volatility_index": rationale.get("market_snapshot", {}).get("volatility", "Normal")
            },
            "external_events": external_events
        }
        
        return payload

    def _fetch_price_action(self, trade) -> Dict:
        """Fetch and summarize candles during the trade."""
        # Get candles from 1 hour before entry to exit
        start_time = trade.opened_at - timedelta(hours=1)
        end_time = trade.closed_at
        
        limit = 500
        
        # Fetch M5
        df_m5 = self.market_service.binance.fetch_ohlcv(trade.pair, "5m", limit=limit)
        # Filter range
        df_m5 = df_m5[(df_m5.index >= start_time) & (df_m5.index <= end_time)]
        
        # Summarize candles to reduce tokens
        # We can just send a compact list of OHLC for the LLM
        summary_m5 = []
        for ts, row in df_m5.tail(30).iterrows(): # Last 30 candles is enough for M5 context
            summary_m5.append({
                "time": ts.strftime("%H:%M"),
                "o": row['open'],
                "h": row['high'],
                "l": row['low'],
                "c": row['close'],
                "v": row['volume']
            })
            
        return {
            "m5_candles": summary_m5,
            "observation": f"Trade lasted {len(df_m5)} M5 candles."
        }

    def _fetch_external_events(self, trade) -> Dict:
        """Fetch news that happened during the trade."""
        # For now, we search in local logs or mock it
        # Real implementation would query the sentiments table
        try:
            from db.database import SessionLocal
            from db.models import Sentiment
            
            db = SessionLocal()
            news = db.query(Sentiment).filter(
                Sentiment.timestamp >= trade.opened_at,
                Sentiment.timestamp <= trade.closed_at
            ).all()
            
            summary = []
            for n in news:
                summary.append({
                    "time": n.timestamp.strftime("%H:%M"),
                    "title": n.summary,
                    "score": n.sentiment_score
                })
            db.close()
            return {"relevant_news": summary}
        except Exception:
            return {"relevant_news": []}

    def _fetch_btc_correlation(self, trade) -> str:
        """Calculate how BTC moved during the trade."""
        try:
            df_btc = self.market_service.binance.fetch_ohlcv("BTCUSDT", "5m", limit=100)
            df_btc = df_btc[(df_btc.index >= trade.opened_at) & (df_btc.index <= trade.closed_at)]
            
            if df_btc.empty:
                return "Unknown"
                
            start_price = df_btc.iloc[0]['open']
            end_price = df_btc.iloc[-1]['close']
            pct_change = (end_price - start_price) / start_price * 100
            
            return f"BTC moved {pct_change:.2f}% during the trade lifecycle."
        except Exception:
            return "Data unavailable"

    def _call_llm(self, payload: Dict) -> str:
        """Call LLM with autopsy prompt."""
        import os
        from llm.factory import get_llm_by_name # Need to ensure factory can handle model names
        
        system_prompt = SystemPrompt().get_system_prompt_autopsy()
        user_input = json.dumps(payload, indent=2, default=str)
        
        # Get specific model for autopsy from .env
        autopsy_model = os.getenv("LLM_AUTOPSY_MODEL", os.getenv("LLM_MODEL"))
        
        try:
            # We reuse the factory logic
            from llm.factory import get_decision_llm # For now, use the same factory
            llm = get_decision_llm() # This uses DECISION_LLM_MODEL, we might need a more flexible factory
            
            # Temporary override or dedicated call
            logger.info(f"Calling Autopsy LLM...")
            result = llm.generate(system_prompt=system_prompt, user_input=user_input)
            
            content = result.get("content", "").strip()
            return content
        except Exception as e:
            logger.error(f"LLM call failed for autopsy: {e}")
            return None
