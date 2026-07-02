import logging
import json
from typing import Dict, Any
from workflows.state import DyadixState
from llm.factory import get_decision_llm
from llm.system_prompt import SystemPrompt

logger = logging.getLogger(__name__)

def final_decision_node(state: DyadixState) -> dict:
    """
    Final Decision Agent berbasis LLM.
    Menerima state lengkap (termasuk verdict dari 4 analyst agent & parameter dari risk manager),
    lalu memanggil Decision LLM untuk menghasilkan koordinat order terstruktur.
    """
    symbol = state.get("symbol", "UNKNOWN")
    risk_verdict = state.get("risk_verdict", {})
    print(f"[MONITORING] [Final Decision] Start node for {symbol}...")
    
    # Jika Risk Manager tidak meloloskan trade clearance, default ke WAIT
    if not risk_verdict.get("cleared", False):
        print(f"[MONITORING] [Final Decision] Risk Manager clearance failed for {symbol}. Defaulting to WAIT.")
        logger.info(f"[Final Decision] Risk Manager did not clear {symbol}. Defaulting to WAIT.")
        return {
            "final_decision": {
                "decision": "WAIT",
                "confidence": 0.3,
                "bias": "Neutral",
                "recommended_timeframe": "H1",
                "entry_zone": "Risk Manager clearance failed",
                "invalidated_if": "N/A",
                "target": "N/A",
                "stop_loss": "N/A",
                "risk_reward": "N/A",
                "execution_type": "LIMIT",
                "expected_move": "N/A",
                "reason": "Wait - Risk Manager did not clear trade setup",
                "key_risks": ["Risk limits exceeded"]
            }
        }
        
    print(f"[MONITORING] [Final Decision] Invoking Decision LLM for {symbol}...")
    logger.info(f"[Final Decision] Invoking Decision LLM for {symbol}...")
    
    system_prompt = SystemPrompt().get_system_prompt_decision()
    
    # Bungkus state penting untuk dikirim ke LLM
    context_to_send = {
        "symbol": symbol,
        "realtime_price": state.get("realtime_price"),
        "current_market_session": state.get("current_market_session"),
        "technical_analyst_verdict": state.get("technical_verdict"),
        "liquidity_analyst_verdict": state.get("liquidity_verdict"),
        "derivatives_analyst_verdict": state.get("derivatives_verdict"),
        "sentiment_analyst_verdict": state.get("sentiment_verdict"),
        "consensus_verdict": state.get("aggregated_verdict"),
        "risk_manager_parameters": risk_verdict,
        "raw_key_levels": state.get("market_data", {}).get("key_levels", {})
    }
    
    user_input = (
        f"Multi-Agent Consolidated Context:\n"
        f"{json.dumps(context_to_send, indent=2, ensure_ascii=False, default=str)}"
    )
    
    # JSON schema untuk structured output
    decision_schema = {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["BUY", "SELL", "HOLD", "WAIT"],
                "description": "Trading decision",
            },
            "rr_calculation": {
                "type": "string",
                "description": "Step-by-step mathematical calculation for SL and Target based on ATR to ensure minimum 1:3.0 Risk/Reward ratio.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Confidence level from 0.0 to 1.0",
            },
            "bias": {
                "type": "string",
                "enum": [
                    "Strong Bullish",
                    "Moderate Bullish",
                    "Neutral",
                    "Moderate Bearish",
                    "Strong Bearish",
                ],
            },
            "recommended_timeframe": {
                "type": "string",
                "enum": ["M5", "M15", "H1", "Swing"],
            },
            "entry_zone": {
                "type": "string",
                "maxLength": 80,
                "description": "Entry zone or condition",
            },
            "invalidated_if": {
                "type": "string",
                "maxLength": 100,
                "description": "Condition that invalidates the setup",
            },
            "target": {
                "type": "string",
                "maxLength": 80,
                "description": "Target price or zone",
            },
            "stop_loss": {
                "type": "string",
                "maxLength": 80,
                "description": "Stop loss level",
            },
            "risk_reward": {
                "type": "string",
                "maxLength": 20,
                "description": "Risk to reward ratio (example: 1:3.0)",
            },
            "execution_type": {
                "type": "string",
                "enum": ["MARKET", "LIMIT"],
                "description": "MARKET if realtime_price is inside entry_zone, LIMIT if entry_zone requires a pullback",
            },
            "expected_move": {
                "type": "string",
                "maxLength": 100,
                "description": "Expected price movement with timeframe (example: '+2.8% to +4.2% dalam 12 jam')",
            },
            "reason": {
                "type": "string",
                "maxLength": 75,
                "description": "Short, clear, and professional reasoning",
            },
            "key_risks": {
                "type": "array",
                "items": {"type": "string", "maxLength": 80},
                "minItems": 1,
                "maxItems": 3,
                "description": "List of key risks (maximum 3)",
            },
        },
        "required": [
            "decision",
            "rr_calculation",
            "confidence",
            "bias",
            "recommended_timeframe",
            "entry_zone",
            "invalidated_if",
            "target",
            "stop_loss",
            "risk_reward",
            "execution_type",
            "expected_move",
            "reason",
            "key_risks",
        ],
        "additionalProperties": False,
    }
    
    try:
        llm = get_decision_llm()
        
        # Coba structured_generate
        try:
            result = llm.structured_generate(
                system_prompt=system_prompt,
                user_input=user_input,
                json_schema=decision_schema,
            )
            if result and "error" not in result and "decision" in result:
                print(f"[MONITORING] [Final Decision] Structured decision: {result.get('decision')} | confidence: {result.get('confidence')} | reason: {result.get('reason')}")
                logger.info(f"[Final Decision] Structured output received successfully for {symbol}")
                return {"final_decision": result}
        except Exception as e:
            logger.warning(f"[Final Decision] structured_generate failed ({e}), falling back to standard generate...")
            
        # Fallback ke generate standar
        raw = llm.generate(system_prompt=system_prompt, user_input=user_input)
        content = raw.get("content", "").strip()
        
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
                
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            content = content[start : end + 1]
            
        parsed = json.loads(content.strip())
        print(f"[MONITORING] [Final Decision] Standard parsed decision: {parsed.get('decision')} | confidence: {parsed.get('confidence')} | reason: {parsed.get('reason')}")
        logger.info(f"[Final Decision] Generated standard output successfully parsed for {symbol}")
        return {"final_decision": parsed}
        
    except Exception as e:
        print(f"[MONITORING] [Final Decision] LLM call failed for {symbol}: {e}")
        logger.error(f"[Final Decision] Failed to call Decision LLM for {symbol}: {e}", exc_info=True)
        # Fallback decision
        fallback = {
            "decision": "WAIT",
            "confidence": 0.3,
            "bias": "Neutral",
            "recommended_timeframe": "H1",
            "entry_zone": "Wait for better setup",
            "invalidated_if": "N/A",
            "target": "N/A",
            "stop_loss": "N/A",
            "risk_reward": "N/A",
            "execution_type": "LIMIT",
            "expected_move": "N/A",
            "reason": f"Decision LLM call failed: {str(e)}",
            "key_risks": ["LLM failure"]
        }
        return {"final_decision": fallback}
