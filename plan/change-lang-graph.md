Menurut saya jangan berpikir:

"setiap berapa menit jalankan seluruh pipeline?"

Karena itu akan boros sekali saat market yang dipilih tidak berubah.

Lebih tepat berpikir:

"setiap berapa menit setiap layer dievaluasi?"

Untuk Dyadix yang sekarang, saya akan pisahkan menjadi 4 frekuensi.

Layer 1 — Market Screening

Tugas:

180 pair
↓
Top 10 pair

Data:

Volume
OI
Funding
ATR
Relative Volume

Interval:

5 menit

Kenapa bukan 1 menit?

Karena:

Volume 24h tidak berubah signifikan
OI tidak berubah drastis dalam 1 menit
Funding lebih lambat lagi

Kalau screening setiap menit, hasil Top 10 biasanya hampir sama.

Layer 2 — Signal Detector

Tugas:

Top 10
↓
Signal Score

Karena kamu menggunakan:

EMA Cross
RSI Divergence
Volume Breakout
Rejection Zone

Saya asumsikan basis utama:

TF 5m

Maka trigger terbaik:

Setiap candle 5m close

Bukan setiap menit.

Misalnya:

09:00
09:05
09:10
09:15
Layer 3 — Full Dyadix Pipeline

Trigger:

Signal Score >= Threshold

Misalnya:

threshold = 70

Maka:

LINK = 85
ETH = 82
SOL = 40

Hanya:

LINK
ETH

yang masuk.

Jangan jalankan pipeline untuk semua Top 10.

Layer 4 — Final Decision

Menurut saya:

langsung setelah pipeline selesai

Tidak perlu scheduler sendiri.

Flow:

Signal Detector
↓
Lolos Threshold
↓
Technical
↓
Liquidity
↓
Derivatives
↓
Sentiment
↓
Risk
↓
Final Decision
Yang akan saya lakukan untuk MVP
Market Screening      : 5 menit

Signal Detector       : setiap close candle 5m

Dyadix Pipeline       : event-driven
                         (hanya jika signal score lolos)

Final Decision        : langsung setelah pipeline selesai
Contoh Timeline
09:00
Market Screening
Top 10 diperbarui

09:05
Signal Detector jalan

LINK = 88
ETH  = 81
SOL  = 45

LINK & ETH lolos

Lalu:

09:05:10
LINK → Full Pipeline

09:05:15
ETH → Full Pipeline

Output:

09:05:30
LINK = LONG

09:05:35
ETH = NO TRADE

Kalau saya melihat strategi Dyadix yang pernah kamu jelaskan (intraday, bukan scalping HFT), saya bahkan tidak akan menjalankan Market Screening lebih cepat dari 5 menit. Justru bottleneck terbesar nanti bukan screening, tetapi biaya analisis 10 pair yang lolos Signal Detector. Jadi optimasi utama adalah memastikan hanya pair dengan Signal Score tinggi yang masuk ke pipeline penuh.

oke saya sudah membuat screening market, maka jika ditamhakan ini di rencana awal penerapan langgraph seperti apa breakdownnya

Dengan adanya Market Screening, menurut saya arsitektur LangGraph Dyadix menjadi jauh lebih bersih daripada yang kita bahas sebelumnya.

Karena sekarang ada pemisahan jelas:

Market Discovery
↓
Trade Discovery
↓
Trade Validation
↓
Final Decision

Sebelumnya agent-agentmu harus menganalisis pair yang sudah di-hardcode.

Sekarang agent-agentmu hanya fokus pada pair yang sudah lolos screening.

Arsitektur LangGraph Dyadix v2
START
  │
  ▼
Market Screening Node
  │
  ▼
Top Candidate Pairs
  │
  ▼
Signal Detector Node
  │
  ▼
Qualified Pairs
  │
  ▼
Parallel Analysis
 ├─ Technical Analyst
 ├─ Liquidity Analyst
 ├─ Derivatives Analyst
 └─ Sentiment Analyst
  │
  ▼
Risk Manager
  │
  ▼
Final Decision
  │
  ▼
END
Layer 0 — Market Discovery
Market Screening Node

Input:

{
  "market_universe": "all_hyperliquid_pairs"
}

Tugas:

Volume Ranking
OI Ranking
Funding Ranking
ATR Ranking

Output:

{
  "top_candidates": [
    "LINK",
    "ETH",
    "SOL",
    "AVAX",
    "SUI",
    "DOGE",
    "XRP",
    "ARB",
    "APT",
    "INJ"
  ]
}

Ini bukan AI.

Ini deterministic node.

Layer 1 — Trade Discovery
Signal Detector Node

Input:

{
  "pairs": [...]
}

Tugas:

EMA Cross
RSI Divergence
Volume Breakout
Rejection Zone

Output:

[
  {
    "symbol": "LINK",
    "signal_score": 91
  },
  {
    "symbol": "ETH",
    "signal_score": 85
  }
]

Filter:

signal_score >= threshold

Misal:

[
  "LINK",
  "ETH",
  "AVAX",
  "SUI"
]

Node ini juga tidak perlu AI.

Layer 2 — Trade Validation

Baru di sini LangGraph mulai berguna.

Untuk setiap pair:

LINK
 ↓
Parallel Agent Analysis
Technical Analyst

Input:

{
  "symbol": "LINK",
  "candles": ...
}

Output:

{
  "bias": "bullish",
  "confidence": 82,
  "reasoning": [...]
}
Liquidity Analyst

Input:

{
  "symbol": "LINK",
  "liquidity_data": ...
}

Output:

{
  "bias": "bullish",
  "confidence": 91
}
Derivatives Analyst

Input:

{
  "symbol": "LINK",
  "oi": ...,
  "funding": ...
}

Output:

{
  "bias": "bullish",
  "confidence": 87
}
Sentiment Analyst

Input:

{
  "symbol": "LINK",
  "news": ...,
  "social": ...
}

Output:

{
  "bias": "neutral",
  "confidence": 65
}
Layer 3 — Risk Manager

Menggabungkan seluruh verdict.

Input:

{
  "technical": {...},
  "liquidity": {...},
  "derivatives": {...},
  "sentiment": {...}
}

Output:

{
  "risk_level": "medium",
  "risk_score": 74,
  "max_position_size": 0.02
}
Layer 4 — Final Decision

Input:

{
  "technical": {...},
  "liquidity": {...},
  "derivatives": {...},
  "sentiment": {...},
  "risk": {...}
}

Output:

{
  "action": "LONG",
  "confidence": 88,
  "entry": ...,
  "sl": ...,
  "tp": ...
}
LangGraph Breakdown yang Saya Sarankan
Jangan buat agent untuk screening

Banyak orang melakukan:

Market Screening Agent
Signal Agent
Technical Agent
...

Ini memboroskan token.

Karena:

Market Screening
Signal Detector

sudah deterministic.

Lebih cepat dan lebih murah dengan Python biasa.

Struktur Node
MarketScreeningNode
        │
        ▼
SignalDetectorNode
        │
        ▼
PairRouterNode
        │
        ├─ LINK
        │   ├─ Technical
        │   ├─ Liquidity
        │   ├─ Derivatives
        │   └─ Sentiment
        │
        ├─ ETH
        │   ├─ Technical
        │   ├─ Liquidity
        │   ├─ Derivatives
        │   └─ Sentiment
        │
        ▼
RiskManagerNode
        │
        ▼
FinalDecisionNode

Kalau mengikuti filosofi yang pernah kamu simpan untuk Dyadix (domain-based agents, bukan indicator-based agents), maka Market Screening dan Signal Detector berada di luar LangGraph sebagai pre-processing layer, sedangkan LangGraph baru dimulai saat pair sudah lolos Signal Detector. Ini biasanya mengurangi 70–90% biaya inferensi karena agent hanya bekerja pada pair yang benar-benar memiliki setup.

bautkan readme implement change to langgraph
Dyadix LangGraph Migration Plan
From Linear Pipeline to Domain-Based Multi-Agent Architecture
Overview

Dokumen ini menjelaskan perubahan arsitektur Dyadix dari pipeline linear saat ini menjadi arsitektur berbasis LangGraph dengan domain-based agents.

Tujuan utama migrasi:

Memisahkan tanggung jawab analisis berdasarkan domain
Mengurangi biaya LLM dengan Market Screening
Meningkatkan scalability
Memungkinkan parallel analysis
Mempermudah penambahan agent baru
Current Architecture

Saat ini Dyadix bekerja menggunakan pipeline linear.

Pair
 │
 ▼
Raw Data Collection
 │
 ▼
Signal Detector
 │
 ▼
Technical Analysis
 │
 ▼
Liquidity Analysis
 │
 ▼
Derivatives Analysis
 │
 ▼
Sentiment Analysis
 │
 ▼
Risk Manager
 │
 ▼
Final Decision

Input:

{
  "symbol": "BTC"
}

Output:

{
  "action": "LONG",
  "confidence": 87
}
Problem Statement

Beberapa keterbatasan arsitektur saat ini:

Hardcoded Pair

Saat ini pair ditentukan secara manual.

PAIRS = [
    "BTC",
    "ETH",
    "SOL"
]
Tidak Ada Market Discovery

Dyadix tidak mengetahui market mana yang sedang aktif.

Contoh:

LINK breakout besar

Tetapi Dyadix hanya menganalisis:

BTC
ETH
SOL

Opportunity hilang.

Analisis Berjalan Secara Serial
Technical
↓
Liquidity
↓
Derivatives
↓
Sentiment

Padahal seluruh domain dapat berjalan paralel.

LLM Cost Tidak Efisien

Semua pair langsung masuk ke pipeline analisis penuh.

Target Architecture
High Level Flow
All Hyperliquid Markets
          │
          ▼
Market Screening
          │
          ▼
Top Candidate Pairs
          │
          ▼
Signal Detector
          │
          ▼
Qualified Pairs
          │
          ▼
LangGraph Analysis
          │
          ▼
Risk Manager
          │
          ▼
Final Decision
New Architecture
┌─────────────────────┐
│ Market Screening    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Signal Detector     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Pair Router         │
└──────────┬──────────┘
           │
           ▼
    Parallel Agents

 ┌─────────┬─────────┬─────────┬─────────┐
 │Technical│Liquidity│Derivative│Sentiment│
 └────┬────┴────┬────┴────┬────┴────┬────┘
      │         │         │         │
      ▼         ▼         ▼         ▼

      Agent Verdict Aggregator

                │
                ▼

         Risk Manager

                │
                ▼

         Final Decision
Layer 0 — Market Screening
Purpose

Mencari market yang layak dianalisis.

Input
{
  "market_universe": "all_hyperliquid_pairs"
}
Data Used
Volume
Open Interest
Funding Rate
ATR
Relative Volume
Output
{
  "top_candidates": [
    "LINK",
    "ETH",
    "AVAX",
    "SOL",
    "SUI",
    "DOGE",
    "XRP",
    "APT",
    "ARB",
    "INJ"
  ]
}
Execution
Every 5 Minutes
Implementation

Rule Based

No LLM

No LangGraph

Layer 1 — Signal Detector
Purpose

Menyaring pair yang memiliki setup teknikal awal.

Indicators
EMA Cross
RSI Divergence
Volume Breakout
Rejection Zone
Input
{
  "symbol": "LINK"
}
Output
{
  "symbol": "LINK",
  "signal_score": 88
}
Filter Rule
signal_score >= SIGNAL_THRESHOLD

Misal:

SIGNAL_THRESHOLD = 70
Example

Input:

10 Pair

Output:

4 Pair
Execution
Every 5m Candle Close
Implementation

Rule Based

No LLM

No LangGraph

Layer 2 — LangGraph Analysis

LangGraph dimulai setelah pair lolos Signal Detector.

State Schema
class DyadixState(TypedDict):

    symbol: str

    market_data: dict

    technical_verdict: dict

    liquidity_verdict: dict

    derivatives_verdict: dict

    sentiment_verdict: dict

    risk_verdict: dict

    final_decision: dict
Technical Analyst
Purpose

Menganalisis struktur teknikal market.

Input
OHLCV
EMA
ATR
Market Structure
Output
{
  "bias": "bullish",
  "confidence": 82,
  "risks": []
}
Liquidity Analyst
Purpose

Menganalisis liquidity map market.

Input
PDH
PDL
Liquidity Sweep
Key Levels
Output
{
  "bias": "bullish",
  "confidence": 90
}
Derivatives Analyst
Purpose

Menganalisis positioning futures market.

Input
Open Interest
Funding Rate
OI Delta
Output
{
  "bias": "bullish",
  "confidence": 87
}
Sentiment Analyst
Purpose

Menganalisis faktor eksternal market.

Input
News
Economic Calendar
Social Sentiment
Output
{
  "bias": "neutral",
  "confidence": 60
}
Agent Aggregator
Purpose

Menggabungkan seluruh verdict.

Input
{
  "technical": {},
  "liquidity": {},
  "derivatives": {},
  "sentiment": {}
}
Output
{
  "combined_bias": "bullish",
  "combined_confidence": 84
}
Risk Manager
Purpose

Memvalidasi trade sebelum dieksekusi.

Responsibilities
Risk Validation
RR Validation
Position Sizing
Conflict Detection
Output
{
  "risk_level": "medium",
  "risk_score": 78,
  "position_size": 0.02
}
Final Decision Agent
Purpose

Menghasilkan keputusan trading final.

Input
Aggregated Verdict
Risk Verdict
Output
{
  "action": "LONG",
  "confidence": 89,
  "entry": 2525.4,
  "stop_loss": 2488.2,
  "take_profit": 2610.8,
  "reasoning": [
    "Liquidity sweep confirmed",
    "OI expansion bullish",
    "Funding healthy"
  ]
}
LangGraph Flow
START

 │

 ▼

Technical Analyst
Liquidity Analyst
Derivatives Analyst
Sentiment Analyst

 (Parallel)

 │

 ▼

Agent Aggregator

 │

 ▼

Risk Manager

 │

 ▼

Final Decision

 │

 ▼

END
Execution Schedule
Layer	Trigger
Market Screening	Every 5 Minutes
Signal Detector	Every 5m Candle Close
LangGraph Analysis	Event Driven
Risk Manager	Event Driven
Final Decision	Event Driven
Migration Roadmap
Phase 1

Implement:

Market Screening
Signal Detector Integration

Output:

180 Pair
↓
Top 10
↓
Signal Detector
↓
Qualified Pair
Phase 2

Replace current Technical Analysis with Technical Agent.

Phase 3

Replace Liquidity Analysis with Liquidity Agent.

Phase 4

Replace Derivatives Analysis with Derivatives Agent.

Phase 5

Replace Sentiment Analysis with Sentiment Agent.

Phase 6

Implement Agent Aggregator.

Phase 7

Implement LangGraph Orchestration.

Phase 8

Implement Risk Manager Agent.

Phase 9

Implement Final Decision Agent.

Final Architecture
180 Hyperliquid Markets
          │
          ▼
Market Screening
          │
          ▼
Top 10 Markets
          │
          ▼
Signal Detector
          │
          ▼
Qualified Markets
          │
          ▼
LangGraph Multi-Agent Analysis
          │
          ▼
Risk Manager
          │
          ▼
Final Decision
          │
          ▼
Trade Recommendation

Prinsip utama migrasi ini adalah: Market Screening dan Signal Detector tetap deterministic (Python biasa), sedangkan LangGraph hanya digunakan untuk domain-level reasoning setelah pair benar-benar memiliki setup yang layak dianalisis lebih dalam.