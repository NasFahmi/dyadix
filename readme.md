# Dyadix 🤖

<div align="center">

**An AI-Driven Crypto Trading Bot with Multi-Layer Market Intelligence**

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)
![Status](https://img.shields.io/badge/status-active-green.svg)

</div>

---

## 📌 Overview

**Dyadix** is an intelligent cryptocurrency trading bot that combines multi-layered market analysis with Large Language Models (LLM) to generate structured trading decisions. Unlike traditional rule-based bots, Dyadix leverages the power of AI to analyze complex market dynamics.

### Core Philosophy

> *"Capital preservation is priority number one. Only trade when probability is clearly in your favor."*

Dyadix acts as a disciplined algorithmic trader with 9+ years of market experience, specializing in intraday and short-term trading during the London-NY session overlap.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      MAIN PIPELINE                               │
├─────────────────────────────────────────────────────────────────────┤
│  1. FETCH MARKET DATA                                           │
│     └─► Binance Futures + Bybit Futures (CCXT)               │
│     └─► OHLCV Aggregation (Volume-Weighted)                  │
├─────────────────────────────────────────────────────────────────────┤
│  2. BUILD SENTIMENT CONTEXT                                     │
│     └─► News (RSS Feeds)                                       │
│     └─► Social Media (Twitter/X, Reddit)                      │
│     └─► Fear & Greed Index                                     │
│     └─► Economic Calendar                                     │
│     └─► LLM Analysis (News + Social)                          │
├─────────────────────────────────────────────────────────────────────┤
│  3. FEATURE ENGINEERING                                        │
│     ├─► Technical Analysis                                     │
│     │   ├─ Daily Bias                                          │
│     │   ├─ Trend (H1)                                          │
│     │   ├─ Momentum (M15/M5)                                   │
│     │   ├─ Volatility (M5)                                     │
│     │   └─ Price Action (M5)                                    │
│     ├─► Derivatives                                            │
│     │   ├─ Funding Rate                                        │
│     │   └─ Open Interest                                       │
│     ├─► Liquidity                                              │
│     │   ├─ Swing Pools                                         │
│     │   └─ Sweep Detection                                      │
│     └─► Correlation                                           │
│         └─ Return-based inter-asset correlation               │
├─────────────────────────────────────────────────────────────────────┤
│  4. CONTEXT AGGREGATION                                         │
│     ├─► Weighted Final Bias Calculation                        │
│     │   ├─ Technical: 40%                                     │
│     │   ├─ Sentiment: 30%                                      │
│     │   ├─ Derivatives: 20%                                   │
│     │   └─ Liquidity: 10%                                      │
│     └─► Market Snapshot (M3/M5/M15/H1 precision)              │
├─────────────────────────────────────────────────────────────────────┤
│  5. DECISION LLM                                                │
│     └─► Structured JSON Output                                │
│         { BUY | SELL | HOLD | WAIT }                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Key Features

### 1. Multi-Exchange Data Aggregation
- **Binance Futures** + **Bybit Futures** integrated via CCXT
- Volume-weighted OHLCV aggregation for enhanced accuracy
- Multiple timeframes: 3m, 5m, 15m, 1h, 1d

### 2. Comprehensive Sentiment Analysis
| Source | Description |
|--------|-------------|
| **News** | Coindesk, Cointelegraph, Decrypt, CryptoSlate, Blockworks, Bitcoin Magazine |
| **Twitter/X** | Key influencers tracking (aantonop, VitalikButerin, etc.) |
| **Reddit** | Subreddit sentiment (r/cryptocurrency, r/Bitcoin) |
| **Fear & Greed** | Alternative.me Crypto Fear & Greed Index |
| **Economic** | High-impact economic events calendar |

### 3. Technical Analysis Engine
- **Daily Bias**: Previous day high/low/close analysis
- **Trend Detection**: H1 timeframe trend regime identification
- **Momentum**: RSI, MACD, Stochastic indicators
- **Volatility**: ATR-based volatility regime
- **Price Action**: Swing high/low detection, candle patterns

### 4. Derivatives & Liquidity
- **Funding Rate**: Perpetual swap funding analysis
- **Open Interest**: OI change tracking
- **Liquidity Pools**: Swing pool identification
- **Sweep Detection**: Liquidity sweep/fakeout detection

### 5. AI-Powered Decision Engine
- **Multi-Provider LLM Support**: Groq, Gemini, Local (Ollama)
- **Structured JSON Output**: Type-safe decision parsing
- **Confluence-Based Signals**: 3+ aligned factors required for BUY/SELL

---

## 📁 Project Structure

```
dyadix/
├── config/
│   ├── settings.yml          # Trading pairs, timeframes, LLM config
│   └── settings.py         # Settings loader
├── service/
│   ├── market/
│   │   ├── market_service.py     # Main orchestrator
│   │   ├── binance/
│   │   │   └── binance_service.py
│   │   └── bybit/
│   │       └── bybit_service.py
│   ├── sentiment/
│   │   ├── news/
│   │   │   ├── news_scraper.py
│   │   │   ├── social_scrapper.py
│   │   │   └── influencer_scraper.py
│   │   └── feer_greed/
│   │       └── feer_greed_service.py
│   └── economic/
│       └── economic_calendar_service.py
├── features/
│   ├── technical/
│   │   ├── daily_bias.py
│   │   ├── trend.py
│   │   ├── momentum.py
│   │   ├── volatility.py
│   │   └── price_action.py
│   ├── derivatives/
│   │   └── derivatives.py
│   ├── liquidity/
│   │   └── liquidity.py
│   ├── sentiment/
│   │   ├── sentiment_engine.py
│   │   ├── news_social_analysis.py
│   │   ├── fear_greed_analysis.py
│   │   └── economic_analysis.py
│   ├── correlation/
│   │   └── correlation.py
│   ├── snapshot/
│   │   └── market_snapshot.py
│   └── context_builder.py
├── llm/
│   ├── factory.py           # LLM provider factory
│   ├── base.py              # Base client interface
│   ├── groq_client.py       # Groq provider
│   ├── gemini_client.py     # Google Gemini
│   └── local_client.py      # Local/Ollama
├── pipelines/
│   └── main_pipeline.py   # Main execution pipeline
├── utils/
│   ├── ohlcv_aggregator.py
│   └── ...
├── test/
│   └── ...
├── main.py                  # Entry point
├── requirements.txt
└── .env.example
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- API keys (see below)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/dyadix.git
cd dyadix

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

### Configuration

Edit `.env` with your API keys:

```bash
# Binance API (for market data - public works)
BINANCE_API_KEY=your_api_key
BINANCE_SECRET_KEY=your_secret

# Bybit API
BYBIT_API_KEY=your_api_key
BYBIT_SECRET_KEY=your_secret

# LLM Configuration (choose one)
LLM_PROVIDER=groq  # groq, gemini, or local
GROQ_API_KEY=your_groq_key
# GEMINI_API_KEY=your_gemini_key
# LOCAL_BASE_URL_LLM=http://localhost:1234
```

Edit `config/settings.yml` to configure trading pairs:

```yaml
trading:
  pairs:
    - BTCUSDT
    - ETHUSDT
    - SOLUSDT
    - XRPUSDT
  timeframes:
    - "3m"
    - "5m"
    - "15m"
    - "1h"

llm:
  provider: "groq"
  temperature: 0.25
  max_tokens: 1100
```

### Running Dyadix

```bash
python main.py
```

### Sample Output

```
============================================================
  DYADIX — Trading Decision Summary
============================================================

────────────────────────────────------------------
  Pair    : BTCUSDT
  Decision: BUY
  Bias    : Moderate Bullish
  Confidence : 0.75
  Final Bias (engine): Moderate Bullish
  Timeframe  : M15
  Entry Zone : 67800-68200
  Target     : 69500
  Stop Loss  : 67200
  RR Ratio   : 1:2.5
  Expected   : Bullish continuation targeting 69500
  Reason     : Technical bullish + momentum + liquidity sweep aligned
  Key Risks  : Fakeout at liquidity sweep | Economic event upcoming
  Invalid if : Price breaks 67200 with volume
  Summary    : BTCUSDT technically Moderate Bullish with trend H1 Up...

============================================================
  Pipeline completed.
============================================================
```

---

## 📊 Decision Output Format

Dyadix returns structured JSON for each trading pair:

```json
{
  "decision": "BUY",
  "confidence": 0.75,
  "bias": "Moderate Bullish",
  "recommended_timeframe": "M15",
  "entry_zone": "67800-68200",
  "target": "69500",
  "stop_loss": "67200",
  "risk_reward": "1:2.5",
  "expected_move": "Bullish continuation targeting 69500",
  "reason": "Technical bullish + momentum + liquidity sweep aligned",
  "key_risks": [
    "Fakeout at liquidity sweep",
    "Economic event upcoming"
  ],
  "invalidated_if": "Price breaks 67200 with volume"
}
```

---

## 🔧 Supported LLM Providers

| Provider | Model | Use Case |
|----------|-------|---------|
| **Groq** | llama-4-scout-17b-16e-instruct | Fast inference, recommended |
| **Gemini** | gemini-pro | Google's model |
| **Local** | llama-open-finance-8b | Privacy-first, offline |

---

## ⚠️ Important Notes

### Risk Disclosure

> **DYADIX IS FOR EDUCATIONAL AND RESEARCH PURPOSES ONLY.**
>
> This software does not constitute financial advice. Always:
> - Use proper risk management (never risk more than 2% per trade)
> - Backtest extensively before live trading
> - Monitor the bot in paper trading mode first
> - Understand that LLMs can produce hallucinations

### Current Limitations (April 2026)

1. **Sentiment Analysis**: News analysis limited to RSS feed titles/summaries
2. **AI Confidence**: May show overconfidence in some conditions
3. **Timeframe Selection**: Not all pairs suit H1/M15/M5 — some need adjustment
4. **Signal Stability**: May flip signals within short time windows (needs filtering)
5. **Token Limits**: Non-local LLMs hit token limits with comprehensive context

---

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [CCXT](https://github.com/ccxt/ccxt) - Crypto exchange library
- [Pandas TA](https://github.com/twopirllc/pandas-ta) - Technical analysis indicators
- [Groq](https://groq.com) - Fast AI inference
- All the crypto news providers for RSS feeds

---

## 🔗 Links

- **Documentation**: [docs.dyadix.ai](https://docs.dyadix.ai) (coming soon)
- **Discord**: [Join our community](https://discord.gg/dyadix) (coming soon)
- **Twitter**: [@DyadixAI](https://twitter.com/DyadixAI)

---

<div align="center">

**Made with ❤️ for the crypto trading community**

*Last Updated: April 2026*

</div>