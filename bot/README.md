# edgeX Agent — AI Trading Bot for Telegram

A fully-featured Telegram bot that lets users trade perpetual contracts on [edgeX Exchange](https://edgex.exchange) through natural language conversation, powered by AI.

Users connect their edgeX account, choose an AI personality, and start trading by typing messages like *"long 1 SOL"*, *"BTC多少钱"*, or *"short 0.001 BTC with 3x leverage"*. The bot handles everything: market data, trade execution, portfolio management, and multilingual conversation — all inside Telegram.

## Features

### AI Trading Agent
- **Natural language trading** — type in any language (English, Chinese, Japanese, Korean, Russian, etc.)
- **Live market data** — real-time prices, funding rates, 24h changes, open interest injected into every AI call
- **Trade execution** — AI generates trade plans with entry/TP/SL, user confirms with one tap
- **Pre-trade validation** — checks min order size + balance before placing orders
- **Portfolio-aware** — AI sees your real positions and equity, never hallucinates holdings
- **7 AI personalities** — Degen, Sensei, Cold Blood, Shitposter, Professor, Wolf, Moe (each with unique trading style)

### Per-User Memory System
- **3-tier architecture** inspired by [OpenClaw](https://github.com/AaronWong1999/OpenClaw):
  - **T0 Working Memory** — last 16 messages as multi-turn context
  - **T1 Short-term** — auto-summarization every 10 conversation turns
  - **T2 Long-term** — extracted user preferences (trading style, favorite assets, risk tolerance, language)
- Memory persists across sessions and persona changes (keyed by Telegram user ID)
- AI references past conversations naturally for personalized responses

### Exchange Integration
- **60+ perpetual contracts** — crypto (BTC, ETH, SOL, DOGE...), stocks (TSLA, AAPL, NVDA...), commodities (Gold, Silver)
- **Dynamic contract resolution** — works with any asset on edgeX, not limited to a static list
- **One-click demo login** or connect with your own API key
- **Full portfolio view** — /status, /pnl, /history, /close commands

### UX
- **Button-first interaction** — every screen has action buttons, no dead ends
- **8-button dashboard** — Status, P&L, History, Close Position, Memory, Personality, Settings, Disconnect
- **Inline navigation** — Main Menu button everywhere, settings accessible from any screen
- **Formatted output** — PnL as +$X.XX/-$X.XX, proper symbol names, adaptive price decimals

### Admin Dashboard
- **Feedback system** — /feedback command → stored in DB → web dashboard with reply-to-user via Telegram
- **User conversations viewer** — see every user's chat history, memory summaries, and preferences
- **Accessible at** `http://server:8901/?key=ADMIN_KEY`

### AI Provider Flexibility
- **Free tier** — uses Factory Droid API (rate-limited)
- **Bring your own key** — supports OpenAI, DeepSeek, Anthropic Claude, Google Gemini, Groq, or any OpenAI-compatible API
- **/setai command** — configure API key, base URL, model in-bot

## Quick Start

### Prerequisites
- Python 3.9+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- An edgeX exchange account (for live trading)

### Installation

```bash
git clone https://github.com/AaronWong1999/edgeXAgent.git
cd edgeXAgent/bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Configuration (.env)

```env
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
FACTORY_API_KEY=your-factory-api-key          # For free tier AI
DEEPSEEK_API_KEY=your-deepseek-api-key        # Optional: default AI provider
DEEPSEEK_BASE_URL=https://api.deepseek.com    # Or any OpenAI-compatible endpoint
EDGEX_BASE_URL=https://pro.edgex.exchange
EDGEX_WS_URL=wss://quote.edgex.exchange
DEMO_ACCOUNT_ID=                              # Optional: demo account for one-click login
DEMO_STARK_KEY=                               # Optional: demo account stark key
FEEDBACK_ADMIN_KEY=your-admin-key             # For feedback dashboard
```

### Run

```bash
# Start the bot
python3 main.py

# Start the admin dashboard (optional)
python3 feedback_web.py
```

### Deploy (systemd)

```ini
# /etc/systemd/system/edgex-agent.service
[Unit]
Description=edgeX Agent Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/edgex-agent-bot
ExecStart=/home/ubuntu/edgex-agent-bot/venv/bin/python3 main.py
Restart=always
EnvironmentFile=/home/ubuntu/edgex-agent-bot/.env

[Install]
WantedBy=multi-user.target
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Main dashboard with action buttons |
| `/status` | Account equity, balance, open positions |
| `/pnl` | P&L report with unrealized gains/losses |
| `/history` | Recent trade history |
| `/close` | Select and close open positions |
| `/setai` | Configure AI provider (own API key) |
| `/memory` | View memory stats, preferences, clear memory |
| `/feedback` | Send feedback to admin |
| `/help` | Command list with multilingual examples |
| `/logout` | Disconnect edgeX account |

## Project Structure

```
bot/
├── main.py              # Telegram bot handlers, UI, conversation flows (2100+ lines)
├── ai_trader.py         # AI engine: prompts, API calls, trade plan generation (900+ lines)
├── edgex_client.py      # edgeX SDK wrapper: orders, positions, market data
├── memory.py            # 3-tier per-user memory system
├── db.py                # SQLite: users, trades, conversations, summaries, preferences
├── config.py            # Environment config, contract mappings
├── feedback_web.py      # Admin web dashboard (feedback + user conversations)
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template
├── test_full_smart.py   # Comprehensive regression test (70+ checks)
├── test_memory.py       # Memory system unit tests (63 checks)
└── ARCHITECTURE.md      # Product vision + technical architecture
```

## Testing

```bash
# Memory unit tests (no network required)
python3 test_memory.py

# Full integration test (requires running bot + Telegram test account)
TG_API_ID=<id> TG_API_HASH=<hash> python3 test_full_smart.py
```

The full smart test covers: dashboard, connect flow, AI activation, 7 personas, price queries in 5 languages, trade flow with confirmation, complex AI analysis, all bot commands, /setai, /feedback, memory system, settings navigation, logout — **70+ automated checks**.

## Supported Assets

**Crypto:** BTC, ETH, SOL, BNB, LTC, LINK, AVAX, XRP, DOGE, PEPE, AAVE, TRX, SUI, WIF, TIA, TON, LDO, ARB, OP, ORDI, JTO, JUP, UNI, ATOM, NEAR, SATS, ONDO, APE, CRV, AEVO, ENS, DOT, FET, WLD, ENA, DYDX, APT, ADA, SEI, MEME, PNUT, MOVE, TRUMP, MELANIA, PENGU, VIRTUAL, KAITO, CRCL

**US Equities (Stock Perpetuals):** TSLA, AAPL, NVDA, GOOG, AMZN, META

**Commodities:** XAUT (Gold), SILVER

Plus any new asset added to edgeX — dynamic contract resolution handles it automatically.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the complete product vision, technical design, and implementation details.

## License

MIT
