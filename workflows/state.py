from typing import TypedDict, Dict, Any, List, Optional

class DyadixState(TypedDict):
    """
    State untuk LangGraph orchestrator Dyadix.
    Menyimpan data input pasar, verdict dari masing-masing analyst,
    hasil agregasi, analisis risiko, dan keputusan final.
    """
    # Core Metadata
    symbol: str
    realtime_price: float
    current_market_session: str
    
    # Input Context Data
    market_data: Dict[str, Any]
    sentiment_data: Dict[str, Any]
    derivatives_data: Dict[str, Any]
    liquidity_data: Dict[str, Any]
    correlation_data: Dict[str, Any]
    microstructure_data: Dict[str, Any]
    signal_detector_result: Dict[str, Any]
    
    # Analyst Agent Verdicts (Opsi B: Rule-based calculations)
    technical_verdict: Dict[str, Any]
    liquidity_verdict: Dict[str, Any]
    derivatives_verdict: Dict[str, Any]
    sentiment_verdict: Dict[str, Any]
    
    # Consolidations & Risk
    aggregated_verdict: Dict[str, Any]
    risk_verdict: Dict[str, Any]
    
    # Trade Verdict Output (LLM-based)
    trade_verdict: Dict[str, Any]
    
    # Error tracking
    errors: List[str]
