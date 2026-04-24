import json
import logging
import pandas as pd
from typing import Dict, Any

from llm.factory import get_candle_summary_llm
from llm.system_prompt import SystemPrompt

logger = logging.getLogger(__name__)

class CandleSummaryEngine:
    """
    Engine to summarize raw candlestick arrays (OHLCV) into text narratives
    using a dedicated LLM.
    """

    @staticmethod
    def summarize(tf_data: Dict[str, Any], n: int = 10) -> Dict[str, Any]:
        """
        Extract the last `n` candles for 3m, 5m, 15m, 1h and use an LLM
        to convert them into brief narrative summaries.
        
        Returns:
            Dict containing the "summaries" key with timeframes as sub-keys.
        """
        # 1. Prepare raw data for the LLM
        raw_candles: Dict[str, Any] = {}
        target_tfs = ["3m", "5m", "15m", "1h"]
        
        has_data = False
        for tf in target_tfs:
            df = tf_data.get(tf, {}).get("aggregated", pd.DataFrame())
            if df.empty:
                continue
            
            tail = df.tail(n).copy()
            # Convert timestamp to string if exists to avoid JSON serialization errors
            for col in ["timestamp"]:
                if col in tail.columns:
                    tail[col] = tail[col].astype(str)
            
            cols = [c for c in ["timestamp", "open", "high", "low", "close", "volume"] if c in tail.columns]
            raw_candles[tf] = tail[cols].to_dict(orient="records")
            has_data = True

        if not has_data:
            return {"summaries": {}}

        # 2. Build LLM prompt and schema
        system_prompt = SystemPrompt().get_system_prompt_candle_summary()
        user_input = json.dumps(raw_candles, indent=2, ensure_ascii=False)
        
        # Schema matching the user's requirement: arrays of strings per timeframe
        schema = {
            "type": "object",
            "properties": {
                "summaries": {
                    "type": "object",
                    "properties": {
                        tf: {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "maxLength": 200
                            }
                        } for tf in target_tfs
                    },
                    "additionalProperties": False
                }
            },
            "required": ["summaries"],
            "additionalProperties": False
        }

        # 3. Call the Candle Summary LLM
        try:
            llm = get_candle_summary_llm()
            logger.info("  🤖 Calling Candle Summary LLM...")
            
            result = llm.structured_generate(
                system_prompt=system_prompt,
                user_input=f"Candlestick Data:\n{user_input}",
                json_schema=schema
            )
            
            if result and "error" not in result and "summaries" in result:
                return result
            else:
                logger.warning(f"Candle Summary LLM returned invalid structure: {result}")
                
        except Exception as e:
            logger.error(f"Failed to call Candle Summary LLM: {e}")

        # Fallback if LLM fails
        return {
            "summaries": {
                tf: ["Summary unavailable due to LLM error."] for tf in target_tfs
            }
        }
