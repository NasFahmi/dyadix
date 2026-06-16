# Dyadix 🤖

<div align="center">

**An Advanced Autonomous AI-Driven Crypto Trading System with Multi-Layer Market Intelligence**

![Python](https://img.shields.io/badge/python-3.13+-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)
![Status](https://img.shields.io/badge/status-active-green.svg)

</div>

---

## 📌 Overview

**Dyadix** is a high-frequency (intraday) autonomous cryptocurrency trading system that combines multi-layered market analysis with Large Language Models (LLM) to make and execute professional-grade trading decisions. 

Unlike traditional rule-based bots, Dyadix acts as an **AI-driven hedge fund manager**, analyzing everything from technical indicators and derivative flows to global news sentiment and social media narratives before executing trades on **Hyperliquid (Perpetuals DEX)** using USDC collateral.

### Core Philosophy

> *"Capital preservation is priority number one. Only trade when probability is clearly in your favor, and learn from every loss through deep analysis."*

Dyadix specializes in intraday trading, leveraging market microstructure volatility and decentralized liquidity on the Hyperliquid L1 appchain to capture high-probability moves.

---

## 🏗️ Architecture & Lifecycle

Dyadix operates in a continuous loop (Loop Mode) or a diagnostic single-run mode (One-shot).

```mermaid
graph TD
    A[DataManager: Fetch & Refresh Data] --> B[OHLCV Aggregator: Hyperliquid API]
    B --> C[Context Builder: Technical + Sentiment + Derivatives + Microstructure]
    C --> D[Signal Detector: Fast Pre-Filter Confluence]
    D -- "No Signal" --> A
    D -- "Signal Detected" --> E[Gatekeeper: Cooldown & Session Check]
    E --> F[Decision LLM: Structured Strategy Generation]
    F -- "WAIT/HOLD" --> A
    F -- "BUY/SELL" --> G[Order Executor: Hyperliquid L1 API]
    G --> H[Trade Monitor: Active Position Management]
    H -- "Profit Taken" --> I[Telegram Notification]
    H -- "Stop Loss Hit" --> J[Autopsy Engine: AI Failure Analysis]
    J --> K[Lesson Extraction & DB Logging]
    K --> A
```

---

## 🎯 Key Features

### 1. Robust DEX Integration
- **Hyperliquid L1 Client**: Direct connection to the Hyperliquid L1 appchain using `hyperliquid-python-sdk` for spot and perpetual markets.
- **USDC Collateral**: Full margin and execution settlement in USDC.
- **Agent Wallet Delegation**: Supports delegating trading authority to an Agent Wallet (using `HYPERLIQUID_PRIVATE_KEY` for execution and `HYPERLIQUID_MAIN_ADDRESS` for balance and position checks).

### 2. Market Microstructure & Orderbook Tracking
- **Real-Time Websocket Collector**: Streams real-time orderbook bids/asks, order flows, and trade spreads.
- **Derivative Flow Engine**: Pulls and analyzes Funding Rates and Open Interest (OI) changes directly from the Hyperliquid appchain.

### 3. Multi-Layer Sentiment Engine
- **News Aggregator**: Scrapes RSS feeds from Yahoo Finance, Cointelegraph, Decrypt, etc.
- **Social Pulse**: Analyzes Twitter/X influencers and Reddit (r/cryptocurrency) sentiment.
- **Economic Overlay**: Real-time economic calendar tracking (FED meetings, CPI data, etc.).
- **Fear & Greed**: Real-time crowd psychology tracking.

### 4. Advanced Feature Engineering
- **Technical Analysis**: Trend regimes (H1), RSI/Momentum, ATR-based Volatility, and Daily Bias detection.
- **Liquidity Detection**: Swing pool identification and Sweep/Fakeout detection logic.
- **Correlation Engine**: Return-based inter-asset correlation to prevent over-exposure across pairs.

### 5. AI-Powered "Brain" (Multi-LLM & Provider Agnostic)
- **Flexible Providers**: Supports Gemini, Groq, DeepSeek, and Ninerouter combo routing.
- **News Specialist**: Compresses thousands of headlines into high-impact narratives.
- **Candle Narrator**: Translates raw OHLCV arrays into human-readable price action summaries to save tokens.
- **Master Decision LLM**: Combines all contexts to produce structured JSON plans (Entry, SL, TP, RR).

### 6. Automated Execution & Autopsy
- **Execution**: Automated market/limit orders with SL and TP triggers directly on the exchange.
- **Trade Guard**: Prevents "over-trading" or opening multiple positions for the same pair.
- **Autopsy Engine**: Post-trade failure analysis. If a trade hits Stop Loss, an LLM analyzes the market context at the time of failure to extract **Lessons Learned** and improve future accuracy.

### 7. Interactive Telegram Control
- **Full Remote Control**: Start, stop, or pause the bot via Telegram commands.
- **Real-time Status**: Request 24h performance summaries, current cycle status, or running trade details.
- **Detailed Alerts**: Rich-text notifications for signal detections, order placements, and trade exits.

---

## 📁 Project Structure

```
dyadix/
├── bot/                  # Telegram bot controller & notifications
├── config/               # settings.yml and YAML loader
├── data/                 # PostgreSQL Models & Database init
├── features/             # Core engines: technical, sentiment, liquidity, etc.
├── llm/                  # Multi-provider client factory (Gemini, Groq, DeepSeek, Ninerouter)
├── pipelines/            # Loop Scheduler & Main Pipeline orchestrator
├── service/              
│   ├── exchange/         # Hyperliquid L1 client wrapper (USDC Account, Order placement)
│   ├── market/           # Microstructure WS collector and Hyperliquid market services
│   └── trade/            # Order Executor, Trade Monitor, Autopsy Engine
├── utils/                # OHLCV Aggregator & Session Checkers
└── main.py               # Entry Point
```

---

## 🚀 Quick Start

### Docker (Recommended)
The easiest way to run Dyadix is using Docker Compose.

1. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Fill in your LLM API keys and Telegram credentials
   # Configure your Hyperliquid EVM wallet details:
   # HYPERLIQUID_PRIVATE_KEY=your_agent_private_key
   # HYPERLIQUID_MAIN_ADDRESS=your_main_wallet_address (optional)
   # HYPERLIQUID_TESTNET=true
   ```
2. **Start the Bot**:
   ```bash
   docker-compose up --build -d
   ```

### Manual Installation (using `uv` or `pip`)
1. **Setup**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Run**:
   - **Continuous Mode**: `python main.py`
   - **One-Shot Analysis**: `python main.py --once`

---

## 🤖 Telegram Commands

- `/start` : Force start the bot (ignores active session hours).
- `/stop`  : Pause all trading activity.
- `/auto`  : Resume automatic mode (follows session hours).
- `/status`: Get current cycle, uptime, and daily PnL summary.
- `/trades`: Show all currently open positions.

---

## ⚠️ Risk Disclosure

> **DYADIX IS FOR RESEARCH PURPOSES ONLY.**
> Cryptocurrency trading involves significant risk. LLMs can hallucinate. This system is designed for experienced users who understand algorithmic trading. Never trade with capital you cannot afford to lose.

---

<div align="center">

**Made with ❤️ by the Dyadix Team**

*Last Updated: May 2026*

</div>