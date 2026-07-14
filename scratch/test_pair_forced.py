"""
scratch/test_pair_forced.py

Test pipeline untuk pair SPESIFIK, BYPASS signal detector, langsung ke LangGraph workflow.
Usage: python scratch/test_pair_forced.py [PAIR]
       python scratch/test_pair_forced.py BTCUSDC
"""

import sys
import logging

# Reconfigure stdout untuk Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from utils.logger import setup_global_logger
setup_global_logger()
logger = logging.getLogger(__name__)

PAIR = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDC"

print(f"\n{'='*60}")
print(f"  FORCED TEST — {PAIR}")
print(f"  Bypassing signal detector, running full LangGraph workflow")
print(f"{'='*60}\n")


# ── Step 1: Fetch market data untuk pair ini ────────────────────────
print(f"[1/6] Fetching market data for {PAIR}...")
from service.market.market_service import MarketService

market_svc = MarketService()
market_svc.pairs = [PAIR]
if "1d" not in market_svc.timeframes:
    market_svc.timeframes.append("1d")

market_data = market_svc.fetch_ohlcv_all(limit=250)
pair_tf_data = market_data.get(PAIR, {})
if not pair_tf_data:
    print(f"[ERROR] No market data returned for {PAIR}. Exiting.")
    sys.exit(1)
print(f"  -> Got timeframes: {list(pair_tf_data.keys())}")


# ── Step 2: Sentiment ────────────────────────────────────────────────
print(f"\n[2/6] Building sentiment context...")
from features.sentiment.sentiment_context_builder import build_sentiment_context
from features.sentiment.news_social_analysis import analyze_news_social_with_llm
from features.sentiment.sentiment_engine import SentimentEngine

sentiment_ctx = build_sentiment_context(news_limit=5, reddit_limit_per_sub=3,
                                        twitter_limit_per_user=3, eco_days_ahead=7, eco_days_back=1)
llm_sent = analyze_news_social_with_llm(
    news_list=sentiment_ctx.get("news", []),
    twitter_data=sentiment_ctx.get("social", {}).get("twitter", {}),
    reddit_data=sentiment_ctx.get("social", {}).get("reddit", {}),
    fear_greed=sentiment_ctx.get("fear_and_greed"),
)
sentiment_result = SentimentEngine.aggregate(
    llm_result=llm_sent,
    fear_greed_data=sentiment_ctx.get("fear_and_greed"),
    economic_data=sentiment_ctx.get("economic_calendar"),
)
print(f"  -> Sentiment: {sentiment_result.get('overall_sentiment')} (score={sentiment_result.get('sentiment_score')})")


# ── Step 3: Correlation ──────────────────────────────────────────────
print(f"\n[3/6] Calculating correlation (single-pair, will be empty matrix)...")
correlation_data = {}


# ── Step 4: Derivatives ──────────────────────────────────────────────
print(f"\n[4/6] Building derivatives data...")
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

tf_mock = "5m"
df_mock = pair_tf_data.get(tf_mock, {}).get("aggregated", pd.DataFrame())
derivatives_data = {}
if not df_mock.empty:
    tail = df_mock.tail(24).copy().reset_index(drop=True)
    if "timestamp" in tail.columns:
        ts_base = pd.to_datetime(tail["timestamp"])
    else:
        now_ts = datetime.utcnow()
        ts_base = pd.Series([now_ts - timedelta(hours=(23 - i)) for i in range(24)])
    funding_rates = np.linspace(0.00005, 0.00015, 24)
    df_funding = pd.DataFrame({"timestamp": ts_base, "funding_rate": funding_rates})
    closes = tail["close"].values if "close" in tail.columns else np.linspace(60000, 65000, 24)
    oi = np.linspace(closes.min() * 0.8, closes.max() * 0.9, 24)
    df_oi = pd.DataFrame({"timestamp": ts_base, "open_interest": oi,
                          "oi_change": np.random.normal(0, 1, 24), "close": closes})
    derivatives_data = {PAIR: {"funding_rate": df_funding, "open_interest": df_oi}}
    print(f"  -> Derivatives built for {PAIR}")
else:
    print(f"  -> No 5m data for derivatives (will be empty)")


# ── Step 5: Build full context ───────────────────────────────────────
print(f"\n[5/6] Building full context for {PAIR}...")
from features.context_builder import build_full_context

full_contexts = build_full_context(
    market_data=market_data,
    sentiment_result=sentiment_result,
    derivatives_data=derivatives_data,
    correlation_data=correlation_data,
    target_pairs=[PAIR],
)

ctx = full_contexts.get(PAIR, {})
if "error" in ctx and "technical" not in ctx:
    print(f"[ERROR] Context build error: {ctx.get('error')}")
    sys.exit(1)

print(f"  -> Final bias: {ctx.get('final_bias')}")
print(f"  -> Current price: {ctx.get('current_price')}")

# Force-run signal detector (untuk info saja, tidak memblokir)
from pipelines.signal_detector import SignalDetector
signal_detector = SignalDetector(min_confidence=0.0, divergence_threshold=0.0)
signal_result = signal_detector.detect(ctx)
print(f"\n  [Signal Detector] (min_confidence=0.0, force pass)")
print(f"  -> has_signal: {signal_result['has_potential_signal']} | confidence: {signal_result['confidence']}")
print(f"  -> suggested_bias: {signal_result.get('suggested_bias')} | type: {signal_result.get('signal_type')}")
print(f"  -> reasons: {signal_result.get('reasons')}")


# Inject candle summary & market snapshot
from features.candle.candles_summary import CandleSummaryEngine
try:
    summary_result = CandleSummaryEngine.summarize(pair_tf_data, n=10)
    ctx["candle_summary"] = summary_result.get("summaries", {})
    print(f"\n  [Candle Summary] Built successfully")
except Exception as e:
    ctx["candle_summary"] = {}
    print(f"\n  [Candle Summary] Failed: {e}")

try:
    from features.snapshot.market_snapshot import build_market_snapshot
    ctx["market_snapshot"] = build_market_snapshot(pair_tf_data)
    print(f"  [Market Snapshot] Built successfully")
except Exception as e:
    ctx["market_snapshot"] = {}
    print(f"  [Market Snapshot] Failed: {e}")

# Inject signal detector result
ctx["signal_detector_result"] = {
    "suggested_bias": signal_result.get("suggested_bias"),
    "signal_type": signal_result.get("signal_type"),
    "confidence": signal_result.get("confidence"),
    "reasons": signal_result.get("reasons", []),
}


# ── Step 6: Run LangGraph Workflow ───────────────────────────────────
print(f"\n[6/6] Running LangGraph Trading Workflow for {PAIR} (FORCED)...")
print(f"{'─'*60}")

initial_state = {
    "symbol": PAIR,
    "realtime_price": ctx.get("current_price", 0.0),
    "current_market_session": ctx.get("current_market_session", "Unknown"),
    "market_data": ctx.get("technical", {}),
    "sentiment_data": ctx.get("sentiment", {}),
    "derivatives_data": ctx.get("derivatives", {}),
    "liquidity_data": ctx.get("liquidity", {}),
    "correlation_data": ctx.get("correlation", {}),
    "microstructure_data": ctx.get("microstructure", {}),
    "signal_detector_result": ctx.get("signal_detector_result", {}),
    "errors": [],
}
if "current_price" not in initial_state["market_data"] and "current_price" in ctx:
    initial_state["market_data"]["current_price"] = ctx["current_price"]

from workflows.trading_workflow import create_trading_workflow
workflow = create_trading_workflow()
workflow_result = workflow.invoke(initial_state)
decision = workflow_result.get("trade_verdict", {})


# ── Final Summary ─────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  FINAL DECISION — {PAIR}")
print(f"{'='*60}")
print(f"  Decision    : {decision.get('decision')}")
print(f"  Bias        : {decision.get('bias')}")
print(f"  Confidence  : {decision.get('confidence')}")
print(f"  Entry Zone  : {decision.get('entry_zone')}")
print(f"  Stop Loss   : {decision.get('stop_loss')}")
print(f"  Target      : {decision.get('target')}")
print(f"  Risk/Reward : {decision.get('risk_reward')}")
print(f"  Timeframe   : {decision.get('recommended_timeframe')}")
print(f"  Exec Type   : {decision.get('execution_type')}")
print(f"  Expected    : {decision.get('expected_move')}")
print(f"  Reason      : {decision.get('reason')}")
risks = decision.get("key_risks", [])
if risks:
    print(f"  Key Risks   : {' | '.join(risks)}")
print(f"  Invalidated : {decision.get('invalidated_if')}")
print(f"{'='*60}\n")
