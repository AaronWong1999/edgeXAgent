# edgeX Agent — Architecture & Product Vision

## 1. Product Vision

### What
A Telegram-based AI trading agent that lets anyone trade perpetual contracts on edgeX Exchange through natural conversation. No charts, no complex UI — just talk to your bot like a friend.

### Why
- **Barrier to entry** — most perp trading UIs are complex. A chat interface removes that barrier.
- **Multilingual access** — edgeX users span multiple countries. The bot handles English, Chinese, Japanese, Korean, Russian, etc. natively via AI.
- **Speed** — typing "long 1 SOL" is faster than navigating a trading UI.
- **Memory** — unlike traditional bots, this one remembers your preferences, past trades, and adjusts advice accordingly.
- **Personality** — traders want different vibes. A degen wants "ape in fam 🚀", a professor wants "the funding rate suggests...". Same data, different delivery.

### Target Users
1. **Existing edgeX traders** who want a faster mobile interface
2. **New crypto traders** who find trading UIs intimidating
3. **Multilingual users** who prefer their native language
4. **AI-curious traders** who want a smart assistant that learns their style

### Key Design Principles
- **Button-first** — every screen has inline buttons. Never leave the user at a dead end.
- **AI confirms, human decides** — AI generates trade plans, but always asks for confirmation before executing.
- **Memory is personal** — tied to Telegram ID, persists across sessions and persona changes.
- **No hallucinations** — real-time portfolio data is injected into every AI call to prevent fabricated position references.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Telegram User                         │
│         (types messages, taps inline buttons)            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              main.py — Telegram Bot Layer                │
│                                                         │
│  ConversationHandler (login flow)                       │
│  CallbackQueryHandler (inline buttons)                  │
│  MessageHandler (AI chat + commands)                    │
│                                                         │
│  /start /status /pnl /history /close /setai /memory     │
│  /feedback /help /logout                                │
│                                                         │
│  Dashboard → Connect → AI Activate → Persona → Chat     │
└───┬──────────┬──────────┬───────────┬──────────────────┘
    │          │          │           │
    ▼          ▼          ▼           ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────────┐
│ db.py  │ │edgex_  │ │  ai_   │ │ memory.py  │
│        │ │client  │ │trader  │ │            │
│SQLite: │ │.py     │ │.py     │ │ 3-tier     │
│users   │ │        │ │        │ │ per-user   │
│trades  │ │edgeX   │ │System  │ │ memory     │
│convos  │ │SDK     │ │prompt  │ │            │
│summs   │ │wrapper │ │builder │ │ T0: recent │
│prefs   │ │        │ │        │ │ T1: summs  │
│feedbk  │ │Prices  │ │Multi-  │ │ T2: prefs  │
│usage   │ │Orders  │ │provider│ │            │
│        │ │Posns   │ │AI calls│ │ Keyword    │
│        │ │Balance │ │        │ │ search     │
└────────┘ └────────┘ │Parse + │ └────────────┘
                      │validate│
                      │JSON    │
                      │response│
                      └────────┘
```

### Component Responsibilities

| File | Lines | Role |
|------|-------|------|
| `main.py` | ~2100 | All Telegram UI: handlers, buttons, conversation flows, command dispatch |
| `ai_trader.py` | ~940 | AI brain: system prompt, market context, trade plan generation, multi-provider API calls, JSON parsing |
| `edgex_client.py` | ~400 | edgeX SDK wrapper: create client, get prices, place orders, get positions, dynamic symbol resolution |
| `memory.py` | ~300 | Per-user memory: record conversations, build context for AI, trigger summarization |
| `db.py` | ~380 | SQLite CRUD: users, trades, conversations, summaries, preferences, feedback, AI usage tracking |
| `config.py` | ~50 | Environment config, static contract ID map |
| `feedback_web.py` | ~300 | Admin web dashboard: feedback management + user conversation viewer |

---

## 3. AI System Design

### System Prompt Architecture

Every AI call includes a carefully layered system prompt:

```
1. Core identity + capabilities
2. Available assets (live contract list)
3. edgeX trading rules (cross-margin, funding, stock perps, etc.)
4. edgex-cli commands (what the AI can reference)
5. Output schema reference (API response structures)
6. Live market data (BTC, ETH, SOL + mentioned assets — prices, changes, funding)
7. Safety rules (max position $500, max 5x leverage, confirm before execute)
8. Min order sizes (critical — orders below these get rejected by edgeX)
9. Response format (CHAT vs TRADE JSON schema)
10. Decision logic (when to CHAT vs when to TRADE)
11. Personality prompt (Degen/Sensei/Cold Blood/etc.)
12. REAL portfolio (live positions + equity from edgeX — prevents hallucination)
13. Memory context (user preferences + relevant summaries + recent history)
```

### Response Format

The AI must return JSON in one of two formats:

```json
// CHAT — conversation, analysis, price queries
{"action": "CHAT", "reply": "BTC is at $73,200, up 7.3%..."}

// TRADE — executable trade plan (shown to user with Confirm/Cancel)
{"action": "TRADE", "asset": "BTC", "side": "BUY", "size": "0.001",
 "leverage": "3", "entry_price": "73200", "take_profit": "76000",
 "stop_loss": "71500", "confidence": "HIGH", "reasoning": "..."}
```

### JSON Parse Safety

AI models sometimes return malformed or double-wrapped JSON. `_parse_content()` handles:
1. Direct JSON parse
2. Strip markdown code fences
3. Find JSON object in surrounding text
4. Regex extraction of known keys
5. Fallback: treat as natural language reply
6. `_strip_json_wrapper()`: catches cases where raw `{"action":"CHAT","reply":"..."}` leaks through

### Multi-Provider Support

```
User's own key → OpenAI-compatible / Anthropic / Gemini
                 ↓ (fallback)
Free tier      → Factory Droid API (rate-limited, 50/day)
```

Provider auto-detection from base URL:
- `anthropic` in URL → Anthropic Claude API format
- `gemini`/`googleapis` in URL → Gemini API format
- Everything else → OpenAI-compatible (works with DeepSeek, Groq, etc.)

---

## 4. Memory System

### Inspired by OpenClaw

Simplified from [OpenClaw's 5-tier system](https://github.com/AaronWong1999/OpenClaw) to 3 tiers appropriate for a chat bot:

### T0 — Working Memory
- **What:** Last 16 raw messages (user + assistant)
- **Injected as:** Multi-turn conversation history in AI messages array
- **Purpose:** Immediate context for follow-up questions

### T1 — Short-term Memory
- **What:** AI-compressed summaries of every ~10 conversation turns
- **Trigger:** After 10+ unsummarized messages, background task calls AI to summarize
- **Content:** Key topics, trading decisions, questions asked, preferences expressed
- **Search:** Keyword-based LIKE queries on summary text and extracted keywords
- **Injected as:** "Relevant Past Context" section in system prompt (matched by keywords from current message)

### T2 — Long-term Memory
- **What:** Extracted user preferences (JSON)
- **Fields:** trading_style, favorite_assets, risk_tolerance, language, notes
- **Extraction:** AI analyzes conversation summaries and extracts preferences
- **Injected as:** "User Profile" section at the top of memory context
- **Purpose:** Personalized advice — "you prefer conservative trades" or "your favorites are BTC and SOL"

### Memory Isolation
- All memory keyed by `tg_user_id` (Telegram user ID)
- Never tied to edgeX account — account can change, memory stays
- Persona changes don't affect memory — only the AI's tone changes
- Each user has independent memory (no cross-user leakage)

### Anti-Hallucination
The AI was hallucinating positions from memory summaries (e.g., "you have 2 SOL long" from a past trade that was already closed). Fixed by:

1. **Real-time portfolio injection** — `_fetch_user_positions()` queries edgeX for actual positions and equity at every AI call. Injected as `## User's REAL Portfolio` with explicit instruction: "TRUST THIS, not memory."
2. **Memory disclaimer** — Memory section labeled as "HISTORICAL, not current positions. NEVER assume positions from memory."

---

## 5. Trade Execution Flow

```
User: "long 1 SOL"
  │
  ▼
AI generates TRADE plan:
  asset=SOL, side=BUY, size=1, entry=$91.50, TP=$95, SL=$89
  │
  ▼
Pre-trade validation:
  ✓ Min order size: SOL min 1 — OK
  ✓ Balance check: max buy size > 1 — OK
  │
  ▼
Show confirmation to user:
  "🟢 Long 1 SOL @ $91.50 | TP: $95 | SL: $89"
  [✅ Confirm] [❌ Cancel]
  │
  ├── User taps Cancel → "Order cancelled"
  │
  └── User taps Confirm
      │
      ▼
      Place limit order via edgeX SDK
      │
      ▼
      "✅ Order placed! ID: 123456"
      Save to trades table for tracking
```

### Validation Rules
- Min order sizes enforced (BTC: 0.001, ETH: 0.01, SOL: 1, DOGE: 300, etc.)
- Max position value: $500
- Max leverage: 5x
- Stock perpetuals: only limit orders during US market closure
- Balance check via `get_max_order_size()`

---

## 6. UX Design

### PepeBoost-Inspired Button Layout

Researched [PepeBoost](https://pepeboost.gitbook.io/en) (leading Solana TG trading bot) for UX patterns. Key takeaways applied:

- **Main dashboard** — 8 action buttons in 4 rows (2 per row)
- **Every screen has navigation** — Main Menu button, Back button, or action buttons
- **No dead ends** — after persona selection, login, AI activation, settings — always show next-step buttons
- **Confirm before trade** — AI proposes, user confirms with one tap

### Navigation Flow

```
/start (Dashboard)
  ├── Status → account summary
  ├── P&L → equity + open positions with PnL
  ├── History → recent fills with formatted prices
  ├── Close Position → select position → confirm close
  ├── Memory → stats + clear option
  ├── Personality → 7 personas + Main Menu back
  ├── Settings
  │   ├── Change Personality
  │   ├── Change AI Provider
  │   ├── Memory
  │   ├── Disconnect
  │   └── Main Menu (back to dashboard)
  └── Disconnect → confirm → reconnect button
```

### Personality System

7 personalities — same data, different delivery:

| Persona | Style |
|---------|-------|
| 🔥 Degen | Aggressive, slang-heavy, "ape in", "LFG" |
| 🎯 Sensei | Balanced, educational, explains reasoning |
| 🤖 Cold Blood | Pure data, no emotion, clinical precision |
| 👀 Shitposter | Meme-heavy, irreverent, chaotic |
| 📚 Professor | Academic, thorough, cites patterns and history |
| 🐺 Wolf | Aggressive but strategic, "hunt the market" |
| 🌸 Moe | Cute, encouraging, anime-style (主人～!) |

---

## 7. Database Schema

SQLite with 7 tables:

```sql
-- User accounts (edgeX credentials)
users (tg_user_id PK, account_id, stark_private_key, ai_api_key, ai_base_url, ai_model, personality, created_at)

-- Trade history (local tracking)
trades (id PK, tg_user_id, order_id, contract_id, side, size, price, status, thesis, created_at, updated_at)

-- AI usage tracking (rate limiting)
ai_usage (tg_user_id, date, count) PK(tg_user_id, date)

-- User feedback
feedback (id PK, tg_user_id, tg_username, tg_first_name, message, status, admin_reply, created_at)

-- Conversation history (memory T0)
conversations (id PK, tg_user_id, role, content, metadata, created_at)
  INDEX idx_conv_user_time ON (tg_user_id, created_at DESC)

-- Memory summaries (memory T1)
memory_summaries (id PK, tg_user_id, summary, keywords, turn_count, period_start, period_end, created_at)
  INDEX idx_memsumm_user ON (tg_user_id, created_at DESC)

-- User preferences (memory T2)
user_preferences (tg_user_id PK, preferences JSON, updated_at)
```

---

## 8. Testing Strategy

### Unit Tests — `test_memory.py`
- 63 checks covering: conversation recording, memory isolation, context building, preferences, keyword extraction, summarization trigger, summary storage, search, clearing, multi-turn, stats, singleton cache
- Runs locally with temp SQLite DB, no network needed

### Integration Tests — `test_full_smart.py`
- 70+ checks against the live running bot via Telethon (Telegram client library)
- Randomized: picks random persona, random languages, random assets each run
- Covers all 12 phases:
  1. Dashboard load + button checks
  2. Connect flow (handles both fresh and returning users)
  3. Persona selection + button layout verification
  4. Price queries in 5 languages (EN, CN, JP, KR, RU)
  5. Trade flow with confirm/cancel
  6. Complex AI analysis
  7. All bot commands with output quality checks (no raw JSON, no ??, no raw big numbers)
  8. /setai source menu
  9. /feedback recording
  10. Memory system (/memory command + recall test)
  11. Settings navigation
  12. Logout + fresh state verification

### Quality Checks (built into smart test)
- No raw JSON in AI responses (`no_raw_json()`)
- No `??` in history output
- No `(?)` in P&L output
- No unformatted large numbers in equity/PnL
- No brain emoji (replaced with memo emoji)
- 8+ buttons for connected user dashboard
- Main Menu button in settings

---

## 9. Deployment

### Production Setup
- **Server:** Ubuntu on 147.224.247.125
- **Bot:** systemd service (`edgex-agent.service`)
- **Dashboard:** background process on port 8901
- **Database:** SQLite file (`edgex_agent.db`) — single-server deployment
- **Dependencies:** edgex-python-sdk, python-telegram-bot, httpx, python-dotenv

### Environment Variables
All secrets in `.env` file (never committed):
- `TELEGRAM_BOT_TOKEN` — from BotFather
- `FACTORY_API_KEY` — for free-tier AI calls via Factory Droid
- `DEEPSEEK_API_KEY` — default AI provider
- `DEMO_ACCOUNT_ID` / `DEMO_STARK_KEY` — optional demo account
- `FEEDBACK_ADMIN_KEY` — admin dashboard access

---

## 10. Future Directions

Potential next steps (not yet implemented):

- **Webhook mode** — switch from polling to webhook for lower latency
- **Multi-server** — PostgreSQL instead of SQLite for horizontal scaling
- **Embedding-based memory search** — replace keyword LIKE queries with vector similarity
- **Automated trading** — scheduled strategies, DCA, grid bots
- **Portfolio alerts** — notify on price targets, liquidation risk, large PnL changes
- **Social features** — share trade ideas, copy trading between users
- **On-chain analytics** — whale tracking, funding rate arbitrage alerts
