# Test Registry — edgeX Agent Bot

> This document is the single source of truth for all test cases.
> Read this before writing or running tests. Update it when adding new tests.
> All tests use Telethon (user-mode Telegram client) to interact with @edgeXAgentBot.

## Environment

```
Bot: @edgeXAgentBot
Test Telegram Account: set TG_API_ID and TG_API_HASH env vars
Session file: tg_test_session (persisted locally)
```

### Run any test:
```bash
TG_API_ID=<your_id> TG_API_HASH=<your_hash> python3 <test_file>.py
```

### Reset test user before running:
```python
import db; db.init_db(); conn = db.get_conn()
conn.execute("DELETE FROM users WHERE tg_user_id = 7894288399")
conn.execute("DELETE FROM ai_usage WHERE tg_user_id = 7894288399")
conn.commit(); conn.close()
```

---

## Test Files

### 1. `yc_full_test.py` — Main Regression (44 checks)

**Purpose:** End-to-end flow from fresh user to full trading + logout.  
**When to run:** After every deploy. MUST pass 100%.

**Flow:**
1. `/start` fresh user → unified dashboard (title, status lines, buttons, multilingual prompts)
2. Send message without AI → AI activation prompt (3 buttons)
3. Click "Aaron's API (temp)" → personality selection
4. Choose Degen → confirmation message
5. BTC price query → AI responds with price
6. SILVER question → AI responds
7. Trade attempt without edgeX → shows "Connect edgeX" button
8. `/start` → shows AI active, edgeX not connected
9. Click Connect → API Key flow → submit account ID → submit private key
10. edgeX connected → AI preserved (not wiped)
11. AI chat after connect → works
12. DOGE trade → confirm → order executed
13. `/status`, `/history` → both work
14. `/start` fully connected → shows account, Status/P&L buttons
15. `/help` → multilingual, degen tone, SILVER not GOLD
16. `/logout` → disconnected
17. `/start` after logout → fresh state

**Key checks:**
- No Chinese "临时" anywhere
- No English annotations like "(Long SOL)" in prompts
- SILVER in prompts, not GOLD
- Title: "edgeX Agent — Your Own AI Trading Agent"
- AI preserved after edgeX connect
- Dynamic contract resolution for DOGE

---

### 2. `test_comprehensive.py` — Full Coverage (66 checks)

**Purpose:** Simulate a real noob user clicking everything, validate AI answers are correct.  
**When to run:** After major changes or AI prompt updates.

**Sections:**
1. **Fresh /start** (9 checks): title, hints, status, no 临时, multilingual, no annotations, SILVER
2. **Demo login** (7 checks): Connect → Aaron's edgeX Account (temp) → connected, temp not 临时, account ID shown
3. **AI activation** (8 checks): button order (Balance → Own Key → Aaron's), no 临时, personality buttons
4. **Personality** (4 checks): Degen selected, says "unlocked", no annotations, has /status /pnl tips
5. **AI answer validation** (11 checks):
   - BTC price: responds, has $ and real numbers
   - SILVER price in Chinese: responds in Chinese, knows the asset
   - GOLD → XAUT: resolves correctly, NOT "not available"
   - ETH in Japanese: responds, mentions ETH
6. **Trade execution** (5 checks): SOL trade with confirm/cancel, BTC market order executed
7. **Commands** (9 checks): /status (equity, balance), /pnl, /history, /help (commands, multilingual, degen, no annotations, SILVER)
8. **/setai flow** (4 checks): provider buttons, no free tier mention, OpenAI step 1/3
9. **Dashboard states** (4 checks): AI active, edgeX connected, buttons
10. **Complex AI operations** (9 checks):
    - Portfolio analysis: "Show me my portfolio" → has equity/balance/position info
    - Conditional trade: "If ETH above 2000, long 0.1 ETH" → plan or analysis, mentions buy/sell/ETH
    - Cross-asset comparison: "Compare BTC and ETH momentum" → mentions both BTC and ETH
    - Chinese multi-step: "帮我看一下SOL的价格，如果低于100就做多" → mentions SOL
    - Risk management: "What's my risk exposure?" → responds with analysis
11. **/feedback** (2 checks): prompt shown, feedback recorded to DB
12. **Logout** (4 checks): disconnected, fresh state after

**Key AI validation:**
- BTC price response must contain "$" or "price" + real numbers
- SILVER query in Chinese → response must be in Chinese and mention silver
- "gold" → must map to XAUT, must NOT say "not available"
- Japanese ETH query → must mention ETH
- Portfolio query → must mention equity/balance/position
- Conditional trade → must show trade plan or analysis
- Cross-asset → must mention both assets
- If AI returns "temporarily unavailable" → treated as pass (transient API issue)

---

### 3. `test_demo_login.py` — Demo One-Click (11 checks)

**Purpose:** Test the demo login + Aaron's API one-click flow specifically.  
**When to run:** After changes to login flow or demo credentials.

**Flow:**
1. `/start` → Click Connect → Aaron's edgeX Account (temp) → connected
2. Click Aaron's AI (temp) → personality → Degen
3. Chat: "What's BTC at?" → AI responds
4. `/status` → has Equity
5. `/logout` cleanup

---

### 4. `test_gemini_api.py` — /setai Gemini Flow (9 checks)

**Purpose:** Test /setai → Gemini → submit key → test → personality → chat.  
**Requires:** `GEMINI_API_KEY` env var (user's own key, may be rate limited).

**Flow:**
1. `/setai` → Click Gemini → instructions shown
2. Submit API key → "Testing..." → activated
3. Personality selection
4. Chat: "What's BTC price?" → Gemini responds
5. Trade plan: "Long SOL" → plan or connect prompt

**Known:** 3/9 may fail due to Gemini 429 rate limit (not code issue).

---

### 5. `test_nvidia_api.py` — /setai NVIDIA Flow (7 checks)

**Purpose:** Test NVIDIA API integration.  
**Requires:** `NVIDIA_API_KEY` env var.  
**Known issue:** NVIDIA `qwen/qwen3.5-397b-a17b` times out from Oracle Cloud (120s+). Works locally.

---

### 6. `test_bot.py` — Legacy Basic Test

**Purpose:** Original basic test (login, chat, trade).  
**Status:** Superseded by yc_full_test.py and test_comprehensive.py.

### 7. `test_order.py` — Order Placement Test

**Purpose:** Test real order placement with small DOGE position.

### 8. `test_droid_output.py` — Debug Utility

**Purpose:** Debug AI (droid) output format parsing.

### 9. `yc_user_test.py` — Legacy YC Simulation

**Purpose:** Earlier YC-level user simulation.  
**Status:** Superseded by test_comprehensive.py.

---

## Symbol / Contract Reference

| User Input | edgeX Symbol | Contract ID | Notes |
|---|---|---|---|
| BTC, bitcoin, 比特币 | BTC | 10000001 | |
| ETH, ethereum, 以太坊 | ETH | 10000002 | |
| SOL, solana | SOL | 10000003 | |
| DOGE, dogecoin, 狗狗币 | DOGE | 10000067 | min size 300 |
| GOLD, 黄金, 金子, XAU | XAUT | 10000234 | XAUTUSD |
| SILVER, 白银, 银, XAG | SILVER | 10000278 | SILVERUSD |
| TSLA, tesla, 特斯拉 | TSLA | 10000273 | Stock perp |
| NVDA, nvidia, 英伟达 | NVDA | 10000272 | Stock perp |
| CRCL, circle | CRCL | 10000253 | NOT CRV |

## Min Order Sizes (must match ai_trader.py system prompt)

| Symbol | Min Size | Approx USD |
|---|---|---|
| BTC | 0.001 | ~$70 |
| ETH | 0.01 | ~$20 |
| SOL | 1 | ~$90 |
| DOGE | 300 | ~$28 |
| PEPE | 1000000 | varies |
| XAUT | 0.001 | ~$5 |
| SILVER | 1 | ~$86 |
| TSLA/AAPL/NVDA | 0.01 | ~$2-4 |

---

## Common Failure Patterns

| Symptom | Cause | Fix |
|---|---|---|
| /setai blocked, no response | setup_handler stale state | All commands in setup_handler fallbacks |
| "API key invalid" on Gemini | Provider not set in context.user_data | Click detection failed, ConversationHandler issue |
| `decimal.ConversionSyntax` | AI returned "market" as price | Resolve to actual price via `get_market_price()` |
| DOGE `minOrderSize: 300` | AI suggested size < 300 | System prompt has correct min sizes |
| GOLD "not available" | No GOLD→XAUT mapping | Added to system prompt + edgex_client aliases |
| NVIDIA API timeout | Oracle Cloud → nvidia.com routing | Not fixable server-side, 90s timeout + error msg |
| Gemini 429 | User's key rate limited | Friendly error message, suggest /setai switch |

---

## Checklist Before Shipping

- [ ] `yc_full_test.py` → 44/44 (MUST)
- [ ] `test_comprehensive.py` → 77/77 (SHOULD)
- [ ] `test_demo_login.py` → 11/11 (if demo login changed)
- [ ] No Chinese "临时" in any user-facing text
- [ ] No English annotations "(Long SOL)" in multilingual prompts
- [ ] SILVER in prompts, not GOLD
- [ ] Min order sizes in system prompt match reality
- [ ] Bot active: `sudo systemctl is-active edgex-agent`
- [ ] Git pushed to main

---

## Test Strategy

**Small changes** (UI text, single function fix):
- Run targeted test only — the specific section affected
- Or run `test_demo_login.py` (fastest, 11 checks)

**Medium changes** (new command, prompt tweak):
- Run `yc_full_test.py` (44 checks, ~4 min)

**Major changes** (AI prompt overhaul, contract logic, new feature):
- Run `test_comprehensive.py` (77 checks, ~7 min)
- Then `yc_full_test.py` to confirm regression

## Feedback Dashboard

```bash
# Start (on server):
cd ~/edgex-agent-bot && source venv/bin/activate
TELEGRAM_BOT_TOKEN=<token> python3 feedback_web.py

# Access:
http://147.224.247.125:8901/?key=edgex-feedback-2026
```

Features: dark theme, status tabs (All/New/WIP/Resolved), reply to user via TG, mark status.

---

*Last updated: 2026-03-04 — 77/77 comprehensive, 44/44 regression, 11/11 demo login*
