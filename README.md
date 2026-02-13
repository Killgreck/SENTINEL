<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/AWS-Bedrock-orange?style=for-the-badge&logo=amazonaws&logoColor=white" />
  <img src="https://img.shields.io/badge/Trading-Crypto-green?style=for-the-badge&logo=bitcoin&logoColor=white" />
  <img src="https://img.shields.io/badge/Status-Development-yellow?style=for-the-badge" />
</p>

<h1 align="center">🛡️ SENTINEL</h1>
<h3 align="center">Autonomous Crypto Trading System with LLM-Augmented Decision Making</h3>

<p align="center">
  <i>Dual-speed architecture: Statistical Fast Brain + LLM Slow Brain</i>
</p>

---

## What is SENTINEL?

**SENTINEL** is an autonomous cryptocurrency trading system that combines **traditional technical analysis** with **Large Language Model (LLM) intelligence** to make trading decisions.

It operates on a **dual-speed architecture**:

```
┌────────────────────────────────────────────────────────┐
│                    SENTINEL CORTEX                      │
│                                                         │
│   🧠 SLOW BRAIN (every ~1h)     ⚡ FAST BRAIN (every tick) │
│   ├─ AWS Bedrock (Claude)       ├─ SMA Crossover          │
│   ├─ Sentiment Analysis         ├─ RSI Oscillator          │
│   └─ Macro Signal               └─ Statistical Signals     │
│         │                              │                    │
│         └──────────┬───────────────────┘                    │
│                    ▼                                        │
│              DECISION ENGINE                                │
│         (BUY / SELL / HOLD)                                │
│                    │                                        │
│                    ▼                                        │
│           EXCHANGE MOCK (Binance)                          │
│        fees: 0.1% | slippage: 0.05%                       │
└────────────────────────────────────────────────────────┘
```

The system first backtests strategies against historical data using the **Cortex Gym** environment, then (in future phases) executes paper trading and eventually live trading via Binance.

---

## Key Features

- **📊 Gym Environment** — OpenAI Gym-like backtesting engine with realistic exchange simulation
- **🤖 5 Trading Agents** — From baseline Buy & Hold to LLM-powered analysis
- **🔄 "The Contrarian"** — Novel strategy detecting market manipulation and trading inversely
- **🧠 LLM Integration** — AWS Bedrock (Claude) for macro-level sentiment analysis
- **📈 Rich Metrics** — Sharpe Ratio, Max Drawdown, Win Rate, Profit Factor
- **☁️ AWS-Ready** — Deploy scripts for EC2, S3 data lake, Bedrock integration

---

## Project Structure

```
SENTINEL/
├── cortex/                          # 🧠 Core trading engine
│   ├── gym/
│   │   ├── config.yaml              # Simulation parameters ($100, BTC/ETH/SOL)
│   │   ├── data_loader.py           # Loads Parquet prices + CSV sentiment
│   │   ├── environment.py           # Gym API (step/reset) trading env
│   │   └── exchange_mock.py         # Binance simulator with fees & slippage
│   ├── agents/
│   │   ├── base_agent.py            # Abstract agent interface
│   │   ├── buy_hold_agent.py        # Baseline: buy day 1, hold forever
│   │   ├── statistical_agent.py     # SMA + RSI + Sentiment signals
│   │   └── llm_agent.py             # AWS Bedrock Claude integration
│   ├── strategies/
│   │   ├── swing.py                 # Swing trading with stop-loss/take-profit
│   │   └── contrarian.py            # Market manipulation detection & reversal
│   ├── backtester.py                # CLI runner for backtests
│   └── metrics.py                   # Performance calculations
│
├── data/
│   ├── market/raw/                  # Price data (Parquet: BTC/ETH/SOL × 1d/1h)
│   └── sentimental/raw/            # Sentiment data (CSV: 5 LLM models)
│
├── docs/                            # 📚 Detailed documentation
│   ├── ARQUITECTURA_GENERAL_CLAUDE.md
│   ├── ARQUITECTURA_HFT_CLAUDE.md
│   └── ARQUITECTURA_GYM.md
│
├── refresh_data.py                  # Update price data (incremental)
├── sync_to_s3.py                    # Upload data to AWS S3
├── setup_fase0.sh                   # One-click AWS environment setup
├── deploy_sentinel_cloud.py         # EC2 deployment script
└── requirements.txt
```

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Download / Update Data

```bash
python3 refresh_data.py
```

### 3. Run a Backtest

```bash
# Baseline (Buy & Hold)
python3 -m cortex.backtester --agent buy_hold --symbol BTCUSDT

# Statistical signals (SMA + RSI + Sentiment)
python3 -m cortex.backtester --agent statistical --symbol BTCUSDT

# Swing trading with stop-loss/take-profit
python3 -m cortex.backtester --agent swing --symbol ETHUSDT

# The Contrarian — market manipulation detection
python3 -m cortex.backtester --agent contrarian --symbol BTCUSDT

# LLM-powered (uses Bedrock if API key available, else offline)
python3 -m cortex.backtester --agent llm --symbol BTCUSDT
```

### 4. Compare All Strategies

```bash
python3 -m cortex.backtester --compare buy_hold statistical swing contrarian llm
```

This produces a comparison table:

```
══════════════════════════════════════════════════════════════════════
  📊 COMPARACIÓN DE ESTRATEGIAS | BTCUSDT
══════════════════════════════════════════════════════════════════════
 strategy_name  total_return_pct  sharpe_ratio  max_drawdown_pct  ...
      BuyHold             120.5         1.234             -25.3
   Statistical              85.2         1.891             -12.1
        Swing              102.3         2.105              -8.7
   Contrarian               43.1         1.502             -15.0
          LLM               95.8         1.750             -11.3
══════════════════════════════════════════════════════════════════════
```

---

## Available Agents

| Agent | Speed | Description | LLM Required |
|---|---|---|---|
| `buy_hold` | — | Baseline benchmark. Buys day 1, holds | No |
| `statistical` | ⚡ <1ms | SMA crossover + RSI + Sentiment score | No |
| `swing` | ⚡ <1ms | Trend-following with stop-loss & take-profit | No |
| `contrarian` | ⚡ <1ms | Detects manipulation spikes, trades inversely | No |
| `llm` | 🐢 200ms+ | AWS Bedrock Claude for macro analysis | Optional* |

*\*The LLM agent works in **offline mode** by default using pre-computed sentiment data. With a Bedrock API key in `.env`, it activates online mode for real-time LLM inference.*

---

## The Contrarian Strategy

SENTINEL's signature strategy — inspired by "Market Judo":

1. **Detect** — Price spike (>3%) + abnormal volume (>3× average)
2. **Verify** — Cross-reference with extreme sentiment scores
3. **Classify** — Is this manipulation or organic movement?
4. **Execute** — Trade INVERSE to the crowd (buy the dump, avoid the pump)
5. **Protect** — Strict stop-loss (3%), time-based exit (max 5 periods)

> *"When everyone is buying on hype, the Contrarian waits. When everyone is panic-selling, the Contrarian buys."*

---

## AWS Setup

SENTINEL is designed to run on AWS infrastructure:

```bash
# One-command setup: checks CLI, configures credentials, audits resources
bash setup_fase0.sh

# Upload local data to S3
python3 sync_to_s3.py --dry-run   # Preview
python3 sync_to_s3.py             # Upload

# Deploy EC2 instance
python3 deploy_sentinel_cloud.py
```

---

## Documentation

For detailed technical documentation, see the [`docs/`](docs/) directory:

| Document | Contents |
|---|---|
| [ARQUITECTURA_GYM.md](docs/ARQUITECTURA_GYM.md) | Gym environment, agents, metrics, and backtester architecture |
| [ARQUITECTURA_GENERAL_CLAUDE.md](docs/ARQUITECTURA_GENERAL_CLAUDE.md) | Overall system architecture for swing trading with LLMs |
| [ARQUITECTURA_HFT_CLAUDE.md](docs/ARQUITECTURA_HFT_CLAUDE.md) | Ultra-low latency trading architecture on AWS |

---

## Roadmap

| Phase | Status | Description |
|---|---|---|
| **Fase 0** | ✅ Done | AWS diagnostics, path fixes, setup automation |
| **Fase 1** | ✅ Done | Data pipeline, S3 sync, incremental refresh |
| **Fase 2** | ✅ Done | Cortex Gym engine, backtesting, 5 agents |
| **Fase 3** | ✅ Done | LLM integration, Swing & Contrarian strategies |
| **Fase 4** | 🔲 Planned | Experimentation framework (DynamoDB) |
| **Fase 5** | 🔲 Planned | Results dashboard |
| **Fase 6** | 🔲 Planned | 24/7 Paper trading via Binance WebSocket |

---

## Environment Variables

Create a `.env` file in the project root:

```env
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET_KEY=your_binance_secret_key
HF_TOKEN=your_huggingface_token
KAGGLE_USERNAME=your_kaggle_username
KAGGLE_KEY=your_kaggle_key
BEDROCK_API_KEY=your_bedrock_api_key    # Optional: enables LLM online mode
AWS_DEFAULT_REGION=us-east-1
```

> ⚠️ **Security**: Never commit `.env` or `*.pem` files to git. See [`.gitignore`](.gitignore).

---

## Tech Stack

- **Languages**: Python 3.10+
- **Data**: Pandas, PyArrow, yfinance
- **LLM**: AWS Bedrock (Claude 3 Haiku / Sonnet)
- **Cloud**: AWS (EC2, S3, Bedrock, DynamoDB)
- **Exchange**: Binance API (paper trading → live)

---

## License

Private — All rights reserved.

---

<p align="center">
  <b>Built by <a href="https://github.com/apolo">Apolo</a> · Onyx Logic Project</b>
</p>
