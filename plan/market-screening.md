Dyadix Market Screening Module
Overview

Market Screening adalah modul tambahan yang ditempatkan sebelum pipeline analisis Dyadix.

Saat ini Dyadix bekerja dengan pair yang ditentukan secara hardcode:

BTC
ETH
SOL

Flow saat ini:

Hardcoded Pair
      │
      ▼
Raw Data Collector
      ▼
Technical Analysis
      ▼
Liquidity Analysis
      ▼
Derivatives Analysis
      ▼
Risk Manager
      ▼
Final Decision

Kelemahan pendekatan ini:

Opportunity terbaik bisa muncul di pair lain
Sistem tidak adaptif terhadap kondisi market
AI menganalisis pair yang mungkin tidak menarik
Tidak scalable jika ingin memonitor seluruh market Hyperliquid
Objective

Mencari pair terbaik dari seluruh market Hyperliquid sebelum masuk ke pipeline Dyadix.

Flow baru:

Hyperliquid Market
      │
      ▼
Market Screening
      │
      ▼
Top Candidate Pairs
      │
      ▼
Dyadix Analysis Pipeline
      │
      ▼
Final Decision

Contoh:

180 Pair
      │
      ▼
Market Screening
      │
      ▼
Top 10 Pair
      │
      ▼
Dyadix Analysis
      │
      ▼
Top 3 Pair
      │
      ▼
Final Decision
Scope MVP

Market Screening hanya bertugas:

Mengambil daftar market Hyperliquid
Mengumpulkan data market dasar
Menghitung skor peluang
Menghasilkan ranking pair

Market Screening tidak:

Membuat sinyal entry
Menentukan SL/TP
Menjalankan AI Agent
Membuka posisi
Position in Dyadix Architecture
Existing
BTC
ETH
SOL
    │
    ▼
Technical Agent
    ▼
Liquidity Agent
    ▼
Derivatives Agent
    ▼
Risk Manager
    ▼
Final Decision
New Architecture
All Hyperliquid Markets
          │
          ▼
Market Screening
          │
          ▼
Top Candidate Pairs
          │
          ▼
Technical Agent
          ▼
Liquidity Agent
          ▼
Derivatives Agent
          ▼
Risk Manager
          ▼
Final Decision
Screening Workflow
Step 1

Load seluruh market Hyperliquid.

Contoh:

[
    "BTC",
    "ETH",
    "SOL",
    "DOGE",
    "SUI",
    "AVAX",
    "LINK",
    ...
]

Refresh:

Startup
+
6 Jam Sekali
Step 2

Kumpulkan market metrics.

Data minimum:

{
    "symbol": "ETH",
    "volume_24h": 1200000000,
    "funding_rate": 0.012,
    "open_interest": 850000000,
    "price": 5200
}
Step 3

Universe Filter

Tujuan:

Menghapus market yang tidak layak dianalisis.

Contoh:

volume_24h >= 1_000_000
Sebelum Filter
180 Pair
Setelah Filter
60 Pair
Screening Metrics
Volume

Tujuan:

Mencari market yang aktif.

Contoh:

volume_score
Open Interest

Tujuan:

Mencari market dengan partisipasi tinggi.

Contoh:

oi_score
Funding Rate

Tujuan:

Mencari kondisi market yang menarik.

Contoh:

funding_score
Volatility

Tujuan:

Mencari market yang bergerak.

Contoh:

atr_score
Scoring Formula

Versi MVP:

score = (
    volume_score * 0.30 +
    atr_score * 0.30 +
    oi_score * 0.25 +
    funding_score * 0.15
)

Output:

{
    "symbol": "LINK",
    "score": 84.5
}
Ranking

Setelah semua pair dihitung:

[
    {
        "symbol": "LINK",
        "score": 89
    },
    {
        "symbol": "ETH",
        "score": 85
    },
    {
        "symbol": "SOL",
        "score": 82
    }
]

Urutkan:

highest_score_first
Candidate Selection

Konfigurasi:

TOP_CANDIDATES = 10

Output:

[
    "LINK",
    "ETH",
    "SOL",
    "SUI",
    "AVAX",
    "DOGE",
    "XRP",
    "ARB",
    "APT",
    "INJ"
]
Integration With Existing Dyadix
Current
pairs = [
    "BTC",
    "ETH",
    "SOL"
]
New
pairs = market_screening.get_top_pairs()

Output:

[
    "LINK",
    "ETH",
    "SOL"
]

Kemudian pipeline Dyadix tetap berjalan tanpa perubahan:

Top Pair
    │
    ▼
Raw Data Collection
    ▼
Technical Agent
    ▼
Liquidity Agent
    ▼
Derivatives Agent
    ▼
Risk Manager
    ▼
Final Decision
Configuration
SCREENING_CONFIG = {
    "top_candidates": 10,
    "min_volume_24h": 1_000_000,
    "scan_interval": 60,
    "volume_weight": 0.30,
    "atr_weight": 0.30,
    "oi_weight": 0.25,
    "funding_weight": 0.15
}
Future Enhancements

Setelah MVP stabil:

Phase 2

Tambahkan:

Relative Volume
Volume Spike Detection
OI Delta
Phase 3

Tambahkan:

Liquidity Sweep Detection
PDH / PDL Distance
Orderbook Imbalance
Phase 4

Tambahkan:

CVD
Aggressive Buy/Sell Ratio
Liquidation Clusters
Phase 5

Tambahkan AI Screening Agent

Flow:

180 Pair
      │
      ▼
Rule-Based Screening
      │
      ▼
Top 20
      │
      ▼
AI Screening Agent
      │
      ▼
Top 5
      │
      ▼
Full Dyadix Analysis
Success Criteria

Market Screening dianggap berhasil jika:

Dapat memonitor seluruh market Hyperliquid
Tidak terkena rate limit
Menghasilkan ranking pair secara otomatis
Menggantikan hardcoded pair
Mengurangi jumlah pair yang masuk ke pipeline Dyadix
Pipeline Dyadix tetap dapat berjalan tanpa perubahan besar