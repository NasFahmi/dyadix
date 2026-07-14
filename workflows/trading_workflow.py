import logging
from langgraph.graph import StateGraph, START, END
from workflows.state import DyadixState
from workflows.nodes.technical_analyst import technical_analyst_node
from workflows.nodes.liquidity_analyst import liquidity_analyst_node
from workflows.nodes.derivatives_analyst import derivatives_analyst_node
from workflows.nodes.sentiment_analyst import sentiment_analyst_node
from workflows.nodes.agent_aggregator import aggregator_node
from workflows.nodes.structure_mapper import structure_mapper_node
from workflows.nodes.risk_manager import risk_manager_node
from workflows.nodes.trade_verdict import trade_verdict_node

logger = logging.getLogger(__name__)

def create_trading_workflow():
    """
    Membuat dan mengompilasi LangGraph workflow untuk DSS trading Dyadix.
    Alur:
      1. Jalankan 4 Analyst secara PARALEL dari START
      2. Kumpulkan hasilnya di Aggregator
      3. [NEW] Structure Mapper — mapping level struktural (OB, Pool, PDH/PDL) untuk SL/TP
      4. Evaluasi dan validasi parameter di Risk Manager
      5. Buat keputusan verdict trading di Trade Verdict LLM Agent
    """
    workflow = StateGraph(DyadixState)

    # 1. Daftarkan semua Nodes
    workflow.add_node("technical_analyst", technical_analyst_node)
    workflow.add_node("liquidity_analyst", liquidity_analyst_node)
    workflow.add_node("derivatives_analyst", derivatives_analyst_node)
    workflow.add_node("sentiment_analyst", sentiment_analyst_node)
    workflow.add_node("aggregator", aggregator_node)
    workflow.add_node("structure_mapper", structure_mapper_node)   # [NEW]
    workflow.add_node("risk_manager", risk_manager_node)
    workflow.add_node("trade_verdict", trade_verdict_node)

    # 2. Definisikan Edges (START ke 4 Analyst paralel)
    workflow.add_edge(START, "technical_analyst")
    workflow.add_edge(START, "liquidity_analyst")
    workflow.add_edge(START, "derivatives_analyst")
    workflow.add_edge(START, "sentiment_analyst")

    # 3. Hubungkan paralel nodes ke join node (Aggregator)
    workflow.add_edge("technical_analyst", "aggregator")
    workflow.add_edge("liquidity_analyst", "aggregator")
    workflow.add_edge("derivatives_analyst", "aggregator")
    workflow.add_edge("sentiment_analyst", "aggregator")

    # 4. Alur linear: Aggregator → Structure Mapper → Risk Manager → Trade Verdict → END
    workflow.add_edge("aggregator", "structure_mapper")        # [NEW]
    workflow.add_edge("structure_mapper", "risk_manager")      # [CHANGED dari aggregator]
    workflow.add_edge("risk_manager", "trade_verdict")
    workflow.add_edge("trade_verdict", END)

    # Kompilasi Graph
    return workflow.compile()
