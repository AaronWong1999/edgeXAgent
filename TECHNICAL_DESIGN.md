# edgeX Agent — Technical Design Document

> Version: 2.0 | Last Updated: 2026-03-06
> Server: `ubuntu@147.224.247.125:/home/ubuntu/edgex-agent-bot/`
> Bot: `@edgeXAgentBot` on Telegram

---

## 1. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         USER (Telegram)                              │
│  /start → Dashboard                                                  │
│  Text → AI Chat                                                      │
│  Buttons → Callback handlers                                         │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ Telegram Bot API (python-telegram-bot)
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      main.py (3500 lines)                            │
│                                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐                │
│  │ Login Flow   │  │ Trade Hub    │  │ AI Hub       │                │
│  │ (ConvHandler)│  │ (callbacks)  │  │ (callbacks)  │                │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘                │
│         │                │                  │                        │
│  ┌──────┴──────┐  ┌──────┴───────┐  ┌──────┴───────┐                │
│  │ Event Trade │  │ Trade Exec   │  │ News Push    │                │
│  │ Hub (cbs)   │  │ (confirm)    │  │ (scheduled)  │                │
│  └─────────────┘  └──────────────┘  └──────────────┘                │
└──────────┬───────────────┬───────────────┬───────────────────────────┘
           │               │               │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │  db.py      │ │ ai_trader   │ │ edgex_client│
    │  (SQLite)   │ │ (.py, 985L) │ │ (.py, 492L) │
    └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
           │               │               │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │ SQLite DB   │ │ AI APIs     │ │ edgeX       │
    │ 7 tables    │ │ (OpenAI,    │ │ Exchange    │
    │             │ │  Anthropic, │ │ (REST+CLI)  │
    │             │ │  Gemini)    │ │             │
    └─────────────┘ └─────────────┘ └─────────────┘

    ┌──────────────────────────────────────────────┐
    │           External: BWEnews MCP              │
    │  bwenews_mcp.py (Telethon polling, port 8788)│
    │  → Polls TG channel every 30s                │
    │  → Serves articles via MCP JSON-RPC          │
    └──────────────────────────────────────────────┘
```

## 2. File Map

| File | Lines | Purpose |
|------|-------|---------|
| `main.py` | ~3500 | Telegram bot: all handlers, callbacks, UI screens |
| `ai_trader.py` | ~985 | AI trade planning: multi-provider, prompt engineering, plan validation |
| `edgex_client.py` | ~492 | edgeX exchange: orders, positions, account, price data |
| `db.py` | ~603 | SQLite: 7 tables, all CRUD operations |
| `news_push.py` | ~511 | News: MCP polling, AI analysis, alert formatting, push delivery |
| `config.py` | ~55 | Constants: contracts, limits, CLI path |
| `memory.py` | ~200 | Conversation memory: 3-tier (T0 working, T1 summaries, T2 preferences) |
| `bwenews_mcp.py` | ~220 | BWEnews MCP server: Telethon polling, HTTP JSON-RPC endpoint |
| `auth_bwenews.py` | ~50 | One-time Telethon session authentication |
| `tg_prototype.html` | ~220 | Interactive prototype: 68 screens, all flows |

## 3. Database Schema (SQLite)

```sql
-- Core user account
users (
    tg_user_id INTEGER PRIMARY KEY,
    account_id TEXT,           -- edgeX account ID
    stark_private_key TEXT,    -- L2 private key (encrypted at rest)
    created_at REAL
)

-- Trade history
trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_user_id INTEGER,
    order_id TEXT,
    contract_id TEXT,
    side TEXT,                 -- BUY/SELL
    size TEXT,
    price TEXT,
    thesis TEXT,               -- AI reasoning
    created_at REAL
)

-- AI configuration per user
ai_config (
    tg_user_id INTEGER PRIMARY KEY,
    provider TEXT,             -- "openai" | "anthropic" | "gemini" | "free"
    api_key TEXT,              -- encrypted
    base_url TEXT,
    model TEXT,
    persona TEXT DEFAULT 'degen',  -- 7 options
    created_at REAL
)

-- Conversation memory (T0 working memory)
conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_user_id INTEGER,
    role TEXT,                 -- "user" | "assistant"
    content TEXT,
    created_at REAL
)

-- Memory summaries (T1 compressed memory)
memory_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_user_id INTEGER,
    summary TEXT,
    created_at REAL
)

-- User preferences (T2 persistent, JSON blob)
user_preferences (
    tg_user_id INTEGER PRIMARY KEY,
    preferences TEXT DEFAULT '{}',  -- JSON: {"news_trade": {"leverage": 3, ...}}
    updated_at REAL
)

-- News source registry
news_sources (
    id TEXT PRIMARY KEY,       -- e.g. "bwenews", "aggr_news"
    name TEXT,
    mcp_url TEXT,
    mcp_tool TEXT,
    poll_interval_sec INTEGER DEFAULT 120,
    is_default BOOLEAN DEFAULT 0,
    enabled BOOLEAN DEFAULT 1,
    created_at REAL
)

-- User ↔ source subscriptions
news_subscriptions (
    tg_user_id INTEGER,
    source_id TEXT,
    subscribed BOOLEAN DEFAULT 1,
    max_per_hour INTEGER DEFAULT 2,
    PRIMARY KEY (tg_user_id, source_id)
)

-- News delivery dedup
news_delivered (
    news_hash TEXT,
    tg_user_id INTEGER,
    title TEXT,
    source_id TEXT,
    analysis_json TEXT,
    delivered_at REAL,
    PRIMARY KEY (news_hash, tg_user_id)
)

-- AI usage tracking
ai_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_user_id INTEGER,
    provider TEXT,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    created_at REAL
)
```

## 4. AI System Design

### 4.1 Multi-Provider Architecture

```
User message
    │
    ▼
ai_trader.generate_trade_plan(prompt, market_prices, tg_user_id)
    │
    ├── 1. Load user AI config (provider/key/model)
    ├── 2. Build system prompt (persona + rules + market context)
    ├── 3. Inject real-time portfolio data (anti-hallucination)
    ├── 4. Send to AI provider:
    │       ├── _call_openai_compatible()  → OpenAI, DeepSeek, Groq, etc.
    │       ├── _call_anthropic()          → Claude
    │       └── _call_gemini()             → Gemini
    ├── 5. Parse response (JSON extraction chain)
    └── 6. Return plan: {action: "TRADE"|"CHAT", ...}
```

### 4.2 System Prompt Layers

1. **Base role**: "You are a crypto/stock perpetual contract trading agent on edgeX"
2. **Persona overlay**: One of 7 personalities (degen, sensei, cold blood, shitposter, professor, wolf, moe)
3. **Exchange rules**: Available assets, min order sizes, stock market hours
4. **Safety rules**: Max position $500, max leverage 5x, circuit breaker 20%
5. **CRITICAL RULES** (never violate):
   - Never change user's requested asset
   - All TRADE responses must have ALL fields filled
   - **TP/SL are MANDATORY** — calculated from market volatility
   - Keep responses SHORT (3-5 sentences)

### 4.3 AI Response JSON Schema

```json
{
  "action": "TRADE",
  "asset": "BTC",
  "side": "BUY",
  "size": "0.014",
  "leverage": "5",
  "entry_price": "71890.0",
  "take_profit": "75000.0",
  "stop_loss": "70000.0",
  "confidence": "HIGH",
  "reasoning": "Brief explanation",
  "position_value_usd": "100.0"
}
```

If not a trade: `{"action": "CHAT", "reply": "text response"}`

### 4.4 Plan Validation (`validate_plan`)

Before showing Trade Plan to user:
- Side must be BUY or SELL (else convert to CHAT)
- Position value ≤ $500
- Leverage ≤ 5x
- **TP and SL must both exist and be non-empty** (rejects if missing)

### 4.5 Symbol Resolution

Hardcoded mapping in system prompt:
- "btc", "bitcoin", "比特币" → BTC
- "eth", "ethereum", "以太坊" → ETH
- "tsla", "tesla", "特斯拉" → TSLA
- "gold", "黄金" → XAUT
- etc. (30+ assets in CONTRACTS)

## 5. Trade Execution Flow

```
1. User clicks trade button (AI chat or news alert)
   │
2. AI generates Trade Plan with mandatory TP/SL
   │  └── validate_plan() checks all fields present
   │
3. Show Trade Plan to user:
   │  ├── Entry, Size, Value, TP, SL, Confidence, Reasoning
   │  └── [✅ Confirm Execute] [❌ Cancel]
   │
4. User confirms → confirm_trade callback:
   │  ├── Resolve contract_id (CONTRACTS dict or edgex-cli)
   │  ├── Sanitize size/price
   │  ├── Pre-trade check (min size + balance)
   │  └── Place order via edgex-cli:
   │       edgex order create {sym} {side} limit {size} --price {price} --tp {tp} --sl {sl} -y
   │
5. Result:
   ├── SUCCESS → show order details + TP/SL + order ID
   ├── MARGIN_BLOCKED_BY_ORDERS → offer cancel orders + retry
   └── ERROR → friendly error message + recovery buttons
```

### 5.1 Order Placement (edgex-cli)

```bash
edgex --json order create BTC buy limit 0.014 \
  --price 71890 \
  --tp 75000 \
  --sl 70000 \
  -y
```

- TP/SL are attached to the order as market conditional orders
- `--tp`/`--sl` are passed from `plan["take_profit"]` and `plan["stop_loss"]`
- All AI-suggested trades MUST have TP/SL — enforced at validation and execution

## 6. News Push System

### 6.1 Architecture

```
BWEnews MCP Server (port 8788)          News Push System (main bot)
┌──────────────────────────┐            ┌──────────────────────────┐
│ Telethon polling (30s)   │            │ APScheduler (120s)       │
│ → _poll_channel()        │   HTTP     │ → poll_and_push()        │
│ → deque(maxlen=100)      │◄──────────►│ → fetch_mcp_news()       │
│ → _seen_ids dedup        │  JSON-RPC  │ → analyze_news_with_ai() │
│                          │            │ → format_news_alert()    │
│ Session: bwenews_session │            │ → bot.send_message()     │
│ NEVER touch while running│            │                          │
└──────────────────────────┘            └──────────────────────────┘
```

### 6.2 News Analysis (AI)

```
NEWS_ANALYSIS_PROMPT:
  Input: title, body, categories
  Output: {asset, sentiment, confidence, action}

Asset Resolution Rules:
  1. Macro economic (Fed, CPI, tariff, inflation) → QQQ
  2. Generic crypto (regulation, adoption, exchange) → BTC
  3. Specific asset mentioned → that exact asset
  4. Both macro + specific crypto → prioritize specific
```

### 6.3 News Alert Format

```
*{title}*

{🟢|🔴} {AI reason — one sentence analysis}
[Source](url)

[⬆️ LONG {lev}x {asset} 💰${amt1} | TP {tp} SL {sl}]  ← 3 tiers
[⬆️ LONG {lev}x {asset} 💰${amt2} | TP {tp} SL {sl}]
[⬆️ LONG {lev}x {asset} 💰${amt3} | TP {tp} SL {sl}]
[🇨🇳] [🇯🇵] [🇰🇷] [🇷🇺]           ← translation flags
```

- Real-time price via `_get_price_fast()` (edgex-cli, no auth)
- TP = price × (1 + tp_pct/100), SL = price × (1 - sl_pct/100) for LONG
- TP = price × (1 - tp_pct/100), SL = price × (1 + sl_pct/100) for SHORT

### 6.3.1 Direct Trade Execution (from news/chat button click)

```
Button click (nt_{asset}_{side}_{lev}_{amt})
    │
    ├── 1. Get market price (edgex-cli)
    ├── 2. size = floor((notional * leverage / price) / stepSize) * stepSize
    ├── 3. TP/SL = round(price * (1 ± pct) / tickSize) * tickSize
    ├── 4. pre_trade_check (balance + min order validation)
    └── 5. place_order → success/fail
```

- **No AI plan generation** — direct execution, ~2-3s response time
- stepSize/tickSize from `get_contract_specs()` (cached 1hr)
- Balance errors show Close Position + Deposit buttons

### 6.4 User Trade Defaults

Stored in `user_preferences.news_trade` (JSON):

| Setting | Default | Options |
|---------|---------|---------|
| leverage | 3 | 2, 3, 5 |
| amounts | [50, 100, 200] | [25,50,100], [50,100,200], [100,200,500] |
| tp_pct | 8.0 | 5, 8, 10, 15 |
| sl_pct | 4.0 | 3, 4, 5, 8 |

## 7. UI Navigation Architecture

### 7.1 Navigation Rules

1. **`safe_edit`** = always edit in place (never sends new message for navigation)
2. **Modals** = `send_message` (new message, for destructive confirms only)
3. **Results** = edit the modal/executing msg, show only `🏠 Main Menu`
4. **Back** = always edit in place to parent screen
5. **All titles**: "Screen Name — Parent Module Name"

### 7.2 Screen Hierarchy (68 screens total)

```
Dashboard (L1) — 3 states
├── 📈 Trade on edgeX (L2)
│   ├── 🔗 Connect edgeX (L2, shared)
│   │   ├── ⚡ OAuth (L3)
│   │   ├── 🔑 API Key (L3) → Step 1 → Step 2 → ✅ Connected
│   │   └── 👤 Demo (L3)
│   ├── 📈 Trade Hub (L2, shared with quick_status)
│   │   ├── 📤 Share PnL (L3) → PnL Card
│   │   ├── 💰 Position (L3)
│   │   │   ├── Close Single (Modal) → ✅/❌
│   │   │   ├── Close Blocked → Cancel Orders / Retry / View Orders
│   │   │   └── Close All (Modal) → ✅/❌
│   │   ├── 📋 Orders (L3)
│   │   │   ├── Cancel Single (Modal) → ✅/❌
│   │   │   └── Cancel All (Modal) → ✅/❌
│   │   ├── 📋 View Orders per symbol (L3)
│   │   ├── 📜 History (L3)
│   │   └── 🚪 Disconnect (Modal) → ✅/❌
│
├── 🤖 AI Agent (L2)
│   ├── ✨ Activate AI (L2, shared)
│   │   ├── 💳 edgeX Balance (L3, coming soon)
│   │   ├── 🔑 Own Key (L3, shared)
│   │   │   ├── OpenAI input → ✅/❌
│   │   │   ├── Anthropic input → ✅/❌
│   │   │   └── Gemini input → ✅/❌
│   │   └── ⚡ Aaron's API (L3)
│   ├── 🎭 Personality (L3, shared) → Set result
│   ├── 📝 Memory (L3) → Clear Confirm (Modal) → ✅/❌
│   └── 💬 Chat → Trade Plan (shared) → Execute → ✅/❌/Cancelled
│
├── 📰 Event Trading (L2)
│   ├── ⏱ Frequency (L3)
│   ├── 🔴/🟢 Toggle (L3, in-place)
│   ├── ➕ Add Source (L3) → ✅ Added / ❌ Failed
│   ├── 🗑 Delete (L3, in-place)
│   ├── ⚙️ Trade Defaults (L3)
│   │   ├── Leverage Picker (L3)
│   │   ├── Amounts Picker (L3)
│   │   ├── TP Picker (L3)
│   │   └── SL Picker (L3)
│   └── 📰 News Alert (Push) → Translation / Trade tier → Unified Trade Flow
```

### 7.3 Callback Data Registry

79 distinct callback handler branches across 3 handler functions:
- `handle_login_choice()`: 10 handlers (ConversationHandler for /start)
- `handle_setai_provider()`: 3 handlers (ConversationHandler for /setai)
- `handle_trade_callback()`: 66 handlers (global catch-all)

Full registry: see `bot/CALLBACK_REGISTRY.md`

## 8. Memory System (3-tier)

```
T0: Working Memory (conversations table)
    │  Last N messages (default 20)
    │  Injected into every AI prompt
    │
    ▼ (auto-summarize when >20 messages)
T1: Summary Memory (memory_summaries table)
    │  Compressed summaries of past conversations
    │  Injected as context prefix
    │
    ▼ (persistent across sessions)
T2: Preferences (user_preferences table)
    │  JSON blob: persona, trade defaults, etc.
    │  Read on demand, never injected into prompts
    └──────────────────────────────
```

## 9. Anti-Hallucination: Real-Time Portfolio Injection

Before every AI call, the system injects the user's ACTUAL portfolio data:

```python
# ai_trader.py: _build_portfolio_context()
portfolio_context = f"""
CURRENT PORTFOLIO (real-time, do NOT hallucinate):
- Balance: ${equity} (Available: ${available})
- Open positions: {positions_list}
- Open orders: {orders_list}
"""
```

This prevents the AI from:
- Suggesting trades the user can't afford
- Claiming positions exist that don't
- Ignoring existing positions when advising

## 10. Deployment

### 10.1 Infrastructure

- **Server**: Oracle Cloud VPS, Ubuntu 22.04
- **IP**: 147.224.247.125
- **Process**: systemd service `edgex-agent`
- **Python**: 3.11 (venv at `/home/ubuntu/edgex-agent-bot/venv/`)
- **Database**: SQLite at `/home/ubuntu/edgex-agent-bot/bot.db`

### 10.2 Service Configuration

```ini
[Unit]
Description=edgeX Agent Telegram Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/edgex-agent-bot
ExecStart=/home/ubuntu/edgex-agent-bot/venv/bin/python3 main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 10.3 Deploy Process

```bash
# From local machine:
scp -i key.pem bot/*.py ubuntu@147.224.247.125:~/edgex-agent-bot/
ssh -i key.pem ubuntu@147.224.247.125 "sudo systemctl restart edgex-agent"

# Verify:
ssh -i key.pem ubuntu@147.224.247.125 "sudo journalctl -u edgex-agent -n 5"
```

### 10.4 BWEnews MCP Service

```ini
# Separate systemd service: bwenews-mcp
ExecStart=/home/ubuntu/bwenews-mcp/venv/bin/python3 bwenews_mcp.py
# Port 8788, polls Telegram channel every 30 seconds
```

**CRITICAL**: Never access the Telethon session file while the service is running. Telegram permanently revokes sessions on dual-access (`AuthKeyDuplicatedError`). Test only via MCP HTTP: `curl http://127.0.0.1:8788/mcp`

## 11. Testing

### 11.1 Test Files

| File | Checks | Purpose |
|------|--------|---------|
| `yc_full_test.py` | 44 | Main regression: all critical flows |
| `test_comprehensive.py` | 66 | Full coverage: every function |
| `test_ai_trader.py` | — | AI prompt + parsing |
| `test_pnl_share.py` | — | PnL card formatting |
| `test_news_push.py` | — | News analysis + delivery |
| `test_close_orders.py` | — | Position close + order cancel |
| `test_memory.py` | — | Memory tiers + summarization |
| `test_send.py` | — | Manual TG message sending |

### 11.2 Testing Rules

1. **Never touch BWEnews session** — test via MCP HTTP only
2. **Never run tests that import main.py** without mocking Telegram
3. **Always test on server** — edgex-cli not available locally
4. **Deploy → journalctl → verify** — check for import errors first

## 12. Key Design Decisions

| Decision | Why |
|----------|-----|
| Telegram (not web app) | Target audience lives in TG. Zero friction. |
| edgex-cli (not SDK) | CLI handles auth, signing, nonce. SDK is broken for some operations. |
| Factory Droid for AI analysis | Free tier for news analysis. User's API key for chat only. |
| SQLite (not Postgres) | Single server, <1000 users. No need for distributed DB. |
| Polling (not webhooks) | Behind NAT. Polling is simpler and self-healing. |
| Telethon polling (not events) | Event listener silently broke. Polling is reliable. |
| TP/SL mandatory | Safety. No unprotected positions. edgex-cli `--tp`/`--sl` flags. |
| 3-tier memory | Balance between context quality and token cost. |
| safe_edit everywhere | Prevents message flood. Every nav action edits in place. |
| Modals for destructive actions | Logout, close position, clear memory — confirm first. |

## 13. Security

- **Stark private keys**: stored in SQLite, should be encrypted at rest (TODO)
- **API keys**: auto-deleted from Telegram chat after reading
- **No secrets in logs**: logger never logs keys or tokens
- **Rate limiting**: per-user AI call limits, news push frequency limits
- **Input validation**: all user inputs sanitized before DB/API calls
- **Session management**: single Telethon session, never dual-accessed

---

*Generated: 2026-03-06 | edgeX Agent v2.0*
