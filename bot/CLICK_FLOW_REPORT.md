# edgeX Agent Telegram Bot — Complete Click Flow Report

## Table of Contents
- [A. Complete Flow Maps](#a-complete-flow-maps)
  - [1. Dashboard (Root)](#1-dashboard-root)
  - [2. Trade on edgeX Module](#2-trade-on-edgex-module)
  - [3. AI Agent Module](#3-ai-agent-module)
  - [4. Event Trading (News) Module](#4-event-trading-news-module)
  - [5. Login/Connect Flow](#5-loginconnect-flow)
  - [6. Trade Execution Flow](#6-trade-execution-flow)
  - [7. Misc/Utility Screens](#7-miscutility-screens)
- [B. Shared Screens](#b-shared-screens)
- [C. Bugs & Inconsistencies](#c-bugs--inconsistencies)

---

## A. Complete Flow Maps

### 1. Dashboard (Root)

**Entry:** `/start` command → `cmd_start()`  
**Screen Title:** `🤖 edgeX Agent — Your Own AI Trading Agent`  
**Buttons (conditional):**

| Condition | Button | callback_data |
|-----------|--------|---------------|
| Has edgeX account | 📈 Trade on edgeX | `trade_hub` |
| No edgeX account | 🔗 Connect edgeX | `show_login` |
| Has AI configured | 🤖 AI Agent | `ai_hub` |
| No AI configured | ✨ Activate AI | `ai_activate_prompt` |
| Always | 📰 Event Trading | `news_settings` |

---

### 2. Trade on edgeX Module

#### 2a. Trade Hub (`trade_hub`)
**Handler:** `handle_trade_callback` → `query.data == "trade_hub"`  
**Screen Title:** `📈 Trade on edgeX — edgeX Agent`  
**Shows:** Equity, Available Balance, Open Positions with PnL  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 🔴 Close Position | `quick_close` |
| 📋 Orders | `quick_orders` |
| 📜 History | `quick_history` |
| 🚪 Disconnect | `logout_confirm` |
| 🔙 Back | `back_to_dashboard` |

#### 2b. Close Position (`quick_close`)
**Handler:** `handle_trade_callback` → `query.data == "quick_close"`  
**Screen Title:** `🔴 Close Position — edgeX Agent`  
**Shows:** List of open positions  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| Close {SYMBOL} {SIDE} (per position) | `close_{contractId}` |
| 🔙 Back | `trade_hub` |

#### 2c. Close Execution (`close_{contractId}`)
**Handler:** `handle_trade_callback` → `query.data.startswith("close_")`  
**On Success — Screen Title:** `{emoji} Close {SYMBOL} — edgeX Agent`  
**Buttons (success):**

| Button | callback_data |
|--------|---------------|
| 📊 Status | `quick_status` |
| 📈 P&L | `quick_pnl` |
| 📜 History | `quick_history` |
| 📋 Orders | `quick_orders` |
| 🏠 Main Menu | `back_to_dashboard` |

**On MARGIN_BLOCKED_BY_ORDERS — Buttons:**

| Button | callback_data |
|--------|---------------|
| ❌ Cancel All {SYMBOL} Orders | `cancelorders_{contractId}` |
| 🔄 Retry Close {SYMBOL} | `close_{contractId}` |
| 📋 View Orders | `vieworders_{contractId}` |
| 🏠 Main Menu | `back_to_dashboard` |

**On Failure — Buttons:** `🏠 Main Menu` → `back_to_dashboard`

#### 2d. Open Orders (`quick_orders`)
**Handler:** `handle_trade_callback` → `query.data == "quick_orders"`  
**Screen Title:** `📋 Open Orders — edgeX Agent`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| ❌ Cancel {SYM} {SIDE} {SIZE}@{PRICE} (per order) | `cancelone_{orderId}` |
| ❌ Cancel All Orders | `cancelorders_all` |
| 🔙 Back | `trade_hub` |

#### 2e. Trade History (`quick_history`)
**Handler:** `handle_trade_callback` → `query.data == "quick_history"`  
**Screen Title:** `📜 Recent Trades — edgeX Agent`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 🔙 Back | `trade_hub` |

#### 2f. Cancel Orders (`cancelorders_{target}`)
**Handler:** `handle_trade_callback` → `query.data.startswith("cancelorders_")`  
**On Success — Buttons:**

| Button | callback_data |
|--------|---------------|
| 🔴 Close {SYMBOL} (if specific contract) | `close_{contractId}` |
| 📊 Status | `quick_status` |
| 🏠 Main Menu | `back_to_dashboard` |

**On Failure — Buttons:** `🏠 Main Menu` → `back_to_dashboard`

#### 2g. View Orders for Contract (`vieworders_{contractId}`)
**Handler:** `handle_trade_callback` → `query.data.startswith("vieworders_")`  
**Screen Title:** `📋 Open Orders for {SYMBOL}`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| ❌ Cancel {SIDE} {SIZE}@{PRICE} (per order) | `cancelone_{orderId}` |
| ❌ Cancel All {SYMBOL} Orders | `cancelorders_{contractId}` |
| 🏠 Main Menu | `back_to_dashboard` |

#### 2h. Cancel Single Order (`cancelone_{orderId}`)
**Handler:** `handle_trade_callback` → `query.data.startswith("cancelone_")`  
**On Success — Buttons:**

| Button | callback_data |
|--------|---------------|
| 📋 View Orders | `quick_orders` |
| 🔴 Close | `quick_close` |
| 🏠 Main Menu | `back_to_dashboard` |

**On Failure — Buttons:** `🏠 Main Menu` → `back_to_dashboard`

#### 2i. Logout Confirm (`logout_confirm`)
**Handler:** `handle_trade_callback` → `query.data == "logout_confirm"`  
(Also handled in `handle_login_choice`)  
**Screen Title:** `🚪 Disconnect — edgeX Agent`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| ✅ Yes, logout | `logout_yes` |
| ❌ Cancel | `logout_no` |

#### 2j. Logout Yes (`logout_yes`)
**Handler:** `handle_trade_callback` → `query.data == "logout_yes"`  
(Also in `handle_login_choice`)  
**Screen:** `🚪 Disconnect — edgeX Agent` / ✅ Logged out  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 🔗 Reconnect | `show_login` |

#### 2k. Logout No (`logout_no`)
**Handler:** `handle_trade_callback` → `query.data == "logout_no"`  
(Also in `handle_login_choice`)  
**Action:** Returns to Dashboard  

---

### 3. AI Agent Module

#### 3a. AI Hub (`ai_hub`)
**Handler:** `handle_trade_callback` → `query.data == "ai_hub"`  
**Screen Title:** `🤖 AI Agent — edgeX Agent`  
**Shows:** Personality, Provider, Memory stats  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 🎭 Personality | `change_persona` |
| 🔑 AI Provider | `ai_activate_prompt` |
| 📝 Memory | `settings_memory` |
| 🔙 Back | `back_to_dashboard` |

#### 3b. AI Activate Prompt (`ai_activate_prompt`)
**Handler:** `handle_trade_callback` → `query.data == "ai_activate_prompt"`  
(Also in `handle_login_choice`)  
**Screen Title:** `✨ Activate AI — edgeX Agent`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 💳 Use edgeX Account Balance | `ai_edgex_credits` |
| 🔑 Use My Own API Key | `ai_own_key_setup` |
| ⚡ Use Aaron's API (temp) | `ai_use_free` |

#### 3c. edgeX Credits (`ai_edgex_credits`)
**Handler:** `handle_trade_callback` → `query.data == "ai_edgex_credits"`  
**Screen Title:** `💳 edgeX Balance — edgeX Agent` (Coming Soon)  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 🔙 Back | `ai_activate_prompt` |

#### 3d. Own Key Setup (`ai_own_key_setup`)
**Handler:** `handle_trade_callback` → `query.data == "ai_own_key_setup"`  
**Screen Title:** `🔑 AI Provider — edgeX Agent`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| OpenAI / DeepSeek | `setai_openai` |
| Anthropic (Claude) | `setai_anthropic` |
| Google Gemini | `setai_gemini` |

**Note:** These `setai_*` callbacks are handled by `handle_setai_provider` in the `/setai` ConversationHandler, NOT by `handle_trade_callback`. See Bug #1.

#### 3e. Use Free API (`ai_use_free`)
**Handler:** `handle_trade_callback` → `query.data == "ai_use_free"`  
**Screen Title:** `✅ AI Activated — edgeX Agent`  
**Buttons:** Persona selection (see 3f)

#### 3f. Change Persona (`change_persona` / `settings_persona`)
**Handler:** `handle_trade_callback` → `query.data in ("change_persona", "settings_persona")`  
**Screen Title:** `🎭 Personality — edgeX Agent`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 🔥 Degen | `persona_degen` |
| 🎯 Sensei | `persona_sensei` |
| 🤖 Cold Blood | `persona_coldblood` |
| 👀 Shitposter | `persona_shitposter` |
| 📚 Professor | `persona_professor` |
| 🐺 Wolf | `persona_wolf` |
| 🌸 Moe | `persona_moe` |
| 🔙 Back | `ai_hub` |

#### 3g. Persona Selection (`persona_{name}`)
**Handler:** `handle_trade_callback` → `query.data.startswith("persona_")`  
**Action:** Sets persona, returns to AI Hub screen  
**Buttons:** Same as AI Hub (3a)

#### 3h. Memory Settings (`settings_memory`)
**Handler:** `handle_trade_callback` → `query.data == "settings_memory"`  
**Screen Title:** `📝 Memory — edgeX Agent`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 🗑 Clear Memory | `memory_clear_confirm` |
| 🔙 Back | `ai_hub` |

#### 3i. Memory Clear Confirm (`memory_clear_confirm`)
**Handler:** `handle_trade_callback` → `query.data == "memory_clear_confirm"`  
**Screen Title:** `🗑 Clear Memory — edgeX Agent`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| ✅ Yes, clear all | `memory_clear_yes` |
| ❌ Keep | `memory_clear_no` |

#### 3j. Memory Clear Yes (`memory_clear_yes`)
**Handler:** `handle_trade_callback` → `query.data == "memory_clear_yes"`  
**Screen Title:** `📝 Memory — edgeX Agent` (✅ Memory cleared)  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 🔙 Back | `ai_hub` |

#### 3k. Memory Clear No (`memory_clear_no`)
**Handler:** `handle_trade_callback` → `query.data == "memory_clear_no"`  
**Action:** Returns to Memory Settings screen (same as 3h)  

#### 3l. Own API Key (legacy) (`ai_own_key`)
**Handler:** `handle_trade_callback` → `query.data == "ai_own_key"`  
**Screen:** `🔑 Own API Key — edgeX Agent` (tells user to use /setai)  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 🔙 Back | `back_to_dashboard` |

#### 3m. Settings Menu (legacy) (`settings_menu`)
**Handler:** `handle_trade_callback` → `query.data == "settings_menu"`  
**Action:** Redirects to AI Hub (same screen as 3a)

---

### 4. Event Trading (News) Module

#### 4a. News Settings Main (`news_settings`)
**Handler:** `handle_trade_callback` → `query.data == "news_settings"`  
**Screen Title:** `📰 Event Trading — edgeX Agent`  
**Shows:** List of subscribed sources with status  
**Buttons (per source):**

| Button | callback_data |
|--------|---------------|
| ❌/✅ {name} (toggle) | `news_toggle_{sourceId}_on` or `news_toggle_{sourceId}_off` |
| ⏱ Frequency | `news_freq_{sourceId}` |
| 🗑 (remove) | `news_remove_{sourceId}` |
| ➕ Add News Source | `news_add` |
| 🔙 Back | `back_to_dashboard` |

#### 4b. News Toggle (`news_toggle_{sourceId}_{on/off}`)
**Handler:** `handle_trade_callback` → `query.data.startswith("news_toggle_")`  
**Action:** Toggles subscription, returns to News Settings Main (4a)

#### 4c. News Frequency (`news_freq_{sourceId}`)
**Handler:** `handle_trade_callback` → `query.data.startswith("news_freq_")`  
**Screen Title:** `⏱ Push Frequency — edgeX Agent`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 1/hr, 2/hr, 3/hr, 5/hr, 10/hr | `news_setfreq_{sourceId}_{n}` |
| 🔙 Back | `news_settings` |

#### 4d. Set Frequency (`news_setfreq_{sourceId}_{n}`)
**Handler:** `handle_trade_callback` → `query.data.startswith("news_setfreq_")`  
**Action:** Sets frequency, returns to News Settings Main (4a)

#### 4e. Remove Source (`news_remove_{sourceId}`)
**Handler:** `handle_trade_callback` → `query.data.startswith("news_remove_")`  
**Action:** Removes/disables source, returns to News Settings Main (4a)

#### 4f. Add News Source (`news_add`)
**Handler:** `handle_trade_callback` → `query.data == "news_add"`  
**Screen Title:** `➕ Add News Source — edgeX Agent`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 💰 Bitcoin News | `news_addsrc_btc` |
| 💠 Ethereum News | `news_addsrc_eth` |
| 🌍 DeFi News | `news_addsrc_defi` |
| 🔙 Back | `news_settings` |

#### 4g. Add Source Topic (`news_addsrc_{topic}`)
**Handler:** `handle_trade_callback` → `query.data.startswith("news_addsrc_")`  
**Action:** Adds source, returns to News Settings Main (4a)

#### 4h. News Mute (`news_mute_{sourceId}`)
**Handler:** `handle_trade_callback` → `query.data.startswith("news_mute_")`  
**Action:** Mutes source, removes reply markup from news alert message

#### 4i. News Dismiss (`news_dismiss`)
**Handler:** `handle_trade_callback` → `query.data == "news_dismiss"`  
**Action:** Deletes the news alert message

#### 4j. News Translate (`tl_{langCode}`)
**Handler:** `handle_trade_callback` → `query.data.startswith("tl_")`  
**Supported codes:** zh, ja, ko, ru  
**Action:** Sends translated news card as new message with same buttons

#### 4k. News Trade (`news_trade_{asset}_{side}_{leverage}_{notional}`)
**Handler:** `handle_trade_callback` → `query.data.startswith("news_trade_")`  
**Action:** Generates AI trade plan from news, shows trade confirmation  
**On TRADE — Buttons:**

| Button | callback_data |
|--------|---------------|
| ✅ Confirm Execute | `confirm_trade` |
| ❌ Cancel | `cancel_trade` |

---

### 5. Login/Connect Flow

#### 5a. Show Login (`show_login`)
**Handler:** `handle_login_choice` AND `handle_trade_callback`  
**Screen Title:** `🔗 Connect edgeX — edgeX Agent`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| ⚡ One-Click Login (coming soon) | `login_oauth` |
| 🔑 Connect with API Key | `login_api` |
| 👤 Use Aaron's edgeX Account (temp) (conditional) | `login_demo` |
| 🔙 Back | `back_to_start` (in handle_login_choice) / `back_to_dashboard` (in handle_trade_callback) |

#### 5b. Login OAuth (`login_oauth`)
**Handler:** `handle_login_choice`  
**Screen:** `⚡ One-Click Login — Coming Soon!`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 🔙 Back | `back_to_start` |

#### 5c. Login Demo (`login_demo`)
**Handler:** `handle_login_choice`  
**Action:** Connects demo account, shows dashboard

#### 5d. Login API (`login_api`)
**Handler:** `handle_login_choice`  
**Action:** Starts text input flow (WAITING_ACCOUNT_ID → WAITING_PRIVATE_KEY)

---

### 6. Trade Execution Flow

#### 6a. Trade Confirmation (from natural language or news trade)
**Shown after AI generates a TRADE plan**  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| ✅ Confirm Execute | `confirm_trade` |
| ❌ Cancel | `cancel_trade` |

#### 6b. Confirm Trade (`confirm_trade`)
**Handler:** `handle_trade_callback` → `query.data == "confirm_trade"`  
**On Success — Screen:** `{emoji} {SIDE} {ASSET} — edgeX Agent`  
**Buttons (success):**

| Button | callback_data |
|--------|---------------|
| 📊 {ASSET} Position | `quick_status` |
| 📈 Live P&L | `quick_pnl` |
| 🔴 Close {ASSET} | `close_{contractId}` |
| 📜 History | `quick_history` |
| 🏠 Main Menu | `back_to_dashboard` |

**On Failure — Buttons include contextual actions + `🏠 Main Menu`**

#### 6c. Cancel Trade (`cancel_trade`)
**Handler:** `handle_trade_callback` → `query.data == "cancel_trade"`  
**Screen Title:** `❌ Trade Cancelled — edgeX Agent`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 📊 Status | `quick_status` |
| 📈 P&L | `quick_pnl` |
| 🏠 Main Menu | `back_to_dashboard` |

---

### 7. Misc/Utility Screens

#### 7a. Quick Status / Quick PnL (`quick_status` / `quick_pnl`)
**Handler:** `handle_trade_callback` → `query.data in ("quick_status", "quick_pnl")`  
**Action:** Redirects to Dashboard (NOT trade_hub)

#### 7b. Cancel Feedback (`cancel_feedback`)
**Handler:** `handle_trade_callback` → `query.data == "cancel_feedback"`  
**Screen:** `❌ Feedback cancelled.`  
**Buttons:**

| Button | callback_data |
|--------|---------------|
| 🏠 Main Menu | `back_to_dashboard` |

#### 7c. Back to Start (`back_to_start`)
**Handler:** `handle_login_choice` AND `handle_trade_callback`  
**Action:** Returns to Dashboard

#### 7d. Back to Dashboard (`back_to_dashboard`)
**Handler:** `handle_login_choice` AND `handle_trade_callback`  
**Action:** Returns to Dashboard (root)

---

## B. Shared Screens

These screens are reachable from multiple parent contexts:

### 1. **Dashboard** (`back_to_dashboard` / `back_to_start`)
Reachable from:
- `trade_hub` → Back
- `ai_hub` → Back
- `news_settings` → Back
- `cancel_trade` → Main Menu
- `confirm_trade` (success/failure) → Main Menu
- `close_{cid}` (success) → Main Menu
- `cancelorders_{id}` (success) → Main Menu
- `cancelone_{id}` (success) → Main Menu
- `vieworders_{cid}` → Main Menu
- `logout_no` (both handlers)
- `cancel_feedback` → Main Menu
- `quick_status` / `quick_pnl` (redirect)
- `ai_own_key` → Back
- Multiple error/command screens → Main Menu
- `settings_menu` (legacy redirect)

### 2. **Logout Confirmation** (`logout_confirm`)
Reachable from:
- `trade_hub` → Disconnect button
- `/logout` command
- `handle_login_choice` handler

### 3. **Logout Yes/No** (`logout_yes` / `logout_no`)
Handled in BOTH:
- `handle_login_choice`
- `handle_trade_callback`

### 4. **Show Login** (`show_login`)
Handled in BOTH:
- `handle_login_choice`
- `handle_trade_callback`

### 5. **AI Activate Prompt** (`ai_activate_prompt`)
Reachable from:
- Dashboard → "Activate AI" (when no AI configured)
- `ai_hub` → "AI Provider"
- `handle_login_choice` handler
- `handle_message` (when no AI configured)

### 6. **Persona Selection Screen** (PERSONA_BUTTONS)
Shown after:
- `ai_use_free` activation
- `change_persona` / `settings_persona`
- After completing `/setai` flow (both `handle_model_button` and `receive_ai_model`)
- Defined as constant `PERSONA_BUTTONS`

### 7. **Trade Confirmation** (`confirm_trade` / `cancel_trade`)
Reachable from:
- Natural language message → AI TRADE plan
- `news_trade_{...}` → AI TRADE plan

### 8. **`_quick_actions_keyboard()`** (🏠 Main Menu only)
Used by:
- `/status`, `/pnl`, `/history`, `/close` command responses
- Various error states
- `cancelorders_` failure
- `cancelone_` failure
- `close_` failure

---

## C. Bugs & Inconsistencies

### BUG 1: `ai_own_key_setup` → `setai_*` callbacks have no handler in `handle_trade_callback`
**Severity: HIGH — Broken flow**

When `ai_own_key_setup` is clicked (from `handle_trade_callback`), it shows the provider keyboard with callbacks `setai_openai`, `setai_anthropic`, `setai_gemini`. However, these callbacks are ONLY handled in the `/setai` ConversationHandler's `handle_setai_provider`. Since the user arrived via a button click (not `/setai`), there is no active ConversationHandler — the callbacks fall through to `handle_trade_callback` which has no handler for `setai_*` patterns. The click will do nothing (silently fall through to the end of `handle_trade_callback`).

**Fix:** Add `setai_*` handling to `handle_trade_callback`, or redirect to `/setai` instead.

### BUG 2: `quick_status` and `quick_pnl` go to Dashboard, NOT Trade Hub
**Severity: MEDIUM — Confusing UX**

When clicking "📊 Status" or "📈 P&L" buttons (used after trade confirm, cancel, close success, etc.), the user expects to see their status/PnL data. Instead, these redirect to the main Dashboard. The handler explicitly says "Redirect legacy quick_status/quick_pnl to trade_hub" in the comment, but the actual code sends to Dashboard, not trade_hub.

```python
# Comment says: "Re-trigger trade_hub by sending the callback manually"
# But code does:
await safe_edit(query, _dashboard_text(user, user_ai), ...)  # Dashboard, not trade_hub!
```

### BUG 3: `back_to_start` inconsistency between handlers
**Severity: LOW**

In `handle_login_choice`: `back_to_start` sends a NEW message saying "Use /start or tap below:" with a Main Menu button.
In `handle_trade_callback`: `back_to_start` edits current message to Dashboard.
Same callback_data, different behavior depending on which handler catches it.

### BUG 4: `show_login` Back button inconsistency
**Severity: LOW**

In `handle_login_choice`: Back button → `back_to_start`
In `handle_trade_callback`: Back button → `back_to_dashboard`

### BUG 5: Duplicate `logout_confirm` handling
**Severity: LOW — Functional but wasteful**

`logout_confirm` is handled in BOTH `handle_login_choice` and `handle_trade_callback`. The behavior differs slightly:
- `handle_login_choice`: sends a NEW message, button says "Yes, disconnect"
- `handle_trade_callback`: edits current message, button says "Yes, logout"

Similarly, `logout_yes` and `logout_no` are duplicated with slightly different behavior:
- `handle_login_choice` `logout_yes`: sends new message
- `handle_trade_callback` `logout_yes`: edits current message
- `handle_login_choice` `logout_no`: sends new message "✅ Cancelled." with Main Menu button
- `handle_trade_callback` `logout_no`: edits to Dashboard

### BUG 6: `/memory` command Back button goes to `back_to_start`, not `back_to_dashboard`
**Severity: LOW**

The `/memory` command's Back button uses `back_to_start`, while all other screens use `back_to_dashboard`. Due to Bug #3, this means the behavior may differ depending on which handler catches the callback.

### BUG 7: `vieworders_{contractId}` has no Back to Trade Hub button
**Severity: LOW**

The `vieworders_` screen only has individual cancel buttons, Cancel All, and Main Menu. There's no "Back to Trade Hub" button, unlike `quick_orders` and `quick_close` which both have Back → `trade_hub`.

### BUG 8: `ai_own_key` is a dead-end requiring manual `/setai`
**Severity: MEDIUM**

When the RATE_LIMITED response shows "🔑 Add my own API Key (unlimited)" → callback `ai_own_key`, the screen says "Use /setai to add your key" with only a Back → Dashboard button. The user has to manually type `/setai`. This should either:
- Show the provider selection directly (like `ai_own_key_setup` does)
- Or at minimum link to the setup flow

### BUG 9: Post-trade buttons include `quick_status` and `quick_pnl` which just redirect to Dashboard
**Severity: MEDIUM**

After a successful trade (`confirm_trade`), the buttons show "📊 {ASSET} Position" (`quick_status`) and "📈 Live P&L" (`quick_pnl`). These suggest they'll show position/PnL data but actually just redirect to the main Dashboard (per Bug #2).

### BUG 10: `cancel_trade` offers `quick_status` and `quick_pnl` buttons
**Severity: LOW**

After cancelling a trade (no order placed), offering Status and P&L buttons is slightly misleading since no trade occurred. Minor UX issue.

### BUG 11: No handler for `login_oauth`, `login_api`, `login_demo` in `handle_trade_callback`
**Severity: MEDIUM — Broken flow when ConversationHandler is not active**

`show_login` in `handle_trade_callback` presents buttons with `login_oauth`, `login_api`, `login_demo`. These callbacks are only handled by `handle_login_choice` (inside the `/start` ConversationHandler). If the user reaches `show_login` via `handle_trade_callback` (e.g., from Dashboard when not connected), clicking these login buttons will fall through to the catch-all `CallbackQueryHandler(handle_trade_callback)` which has no handler for them — they'll silently fail.

**However:** The catch-all `CallbackQueryHandler(handle_trade_callback)` is registered globally, so if the `/start` ConversationHandler is not active, these callbacks WOULD reach `handle_trade_callback` which delegates to itself at the end of `handle_login_choice` via `await handle_trade_callback(update, context)`. But `handle_trade_callback` has no handlers for `login_oauth`, `login_api`, or `login_demo`, so they silently do nothing.

### BUG 12: Potential issue with `news_trade_` callback data length
**Severity: LOW**

Telegram limits callback_data to 64 bytes. Pattern `news_trade_{asset}_{side}_{leverage}_{notional}` could exceed this for assets with long names. Not a code bug per se but a Telegram API constraint.

---

## Complete Callback Data Registry

| callback_data | Handler Location | Notes |
|---|---|---|
| `trade_hub` | handle_trade_callback | L2 Trade screen |
| `ai_hub` | handle_trade_callback | L2 AI screen |
| `news_settings` | handle_trade_callback | L2 News screen |
| `back_to_dashboard` | handle_login_choice + handle_trade_callback | Dashboard |
| `back_to_start` | handle_login_choice + handle_trade_callback | Dashboard (inconsistent) |
| `show_login` | handle_login_choice + handle_trade_callback | Login method selection |
| `login_oauth` | handle_login_choice ONLY | Coming soon screen |
| `login_api` | handle_login_choice ONLY | Text input flow |
| `login_demo` | handle_login_choice ONLY | Demo connect |
| `logout_confirm` | handle_login_choice + handle_trade_callback | Confirm dialog |
| `logout_yes` | handle_login_choice + handle_trade_callback | Execute logout |
| `logout_no` | handle_login_choice + handle_trade_callback | Cancel logout |
| `ai_activate_prompt` | handle_login_choice + handle_trade_callback | AI setup menu |
| `ai_edgex_credits` | handle_trade_callback | Coming soon |
| `ai_own_key_setup` | handle_trade_callback | Provider selection |
| `ai_own_key` | handle_trade_callback | Legacy dead-end |
| `ai_use_free` | handle_trade_callback | Activate free AI |
| `setai_openai` | handle_setai_provider (ConvHandler ONLY) | ⚠️ Not in handle_trade_callback |
| `setai_anthropic` | handle_setai_provider (ConvHandler ONLY) | ⚠️ Not in handle_trade_callback |
| `setai_gemini` | handle_setai_provider (ConvHandler ONLY) | ⚠️ Not in handle_trade_callback |
| `url_*` | handle_url_button (ConvHandler ONLY) | Base URL selection |
| `model_*` | handle_model_button (ConvHandler ONLY) | Model selection |
| `change_persona` | handle_trade_callback | Persona picker |
| `settings_persona` | handle_trade_callback | Alias for change_persona |
| `persona_*` | handle_trade_callback | Set persona |
| `settings_memory` | handle_trade_callback | Memory screen |
| `settings_menu` | handle_trade_callback | Legacy → AI Hub |
| `memory_clear_confirm` | handle_trade_callback | Confirm dialog |
| `memory_clear_yes` | handle_trade_callback | Clear memory |
| `memory_clear_no` | handle_trade_callback | Cancel clear |
| `quick_close` | handle_trade_callback | Position list |
| `quick_orders` | handle_trade_callback | Order list |
| `quick_history` | handle_trade_callback | Trade history |
| `quick_status` | handle_trade_callback | ⚠️ Redirects to Dashboard |
| `quick_pnl` | handle_trade_callback | ⚠️ Redirects to Dashboard |
| `close_*` | handle_trade_callback | Close position |
| `cancelorders_*` | handle_trade_callback | Cancel orders |
| `cancelone_*` | handle_trade_callback | Cancel single order |
| `vieworders_*` | handle_trade_callback | View orders for contract |
| `confirm_trade` | handle_trade_callback | Execute trade |
| `cancel_trade` | handle_trade_callback | Cancel trade |
| `cancel_feedback` | handle_trade_callback | Cancel feedback |
| `news_toggle_*` | handle_trade_callback | Toggle news source |
| `news_freq_*` | handle_trade_callback | Show frequency options |
| `news_setfreq_*` | handle_trade_callback | Set frequency |
| `news_remove_*` | handle_trade_callback | Remove source |
| `news_add` | handle_trade_callback | Add source menu |
| `news_addsrc_*` | handle_trade_callback | Add specific source |
| `news_mute_*` | handle_trade_callback | Mute from alert |
| `news_dismiss` | handle_trade_callback | Dismiss alert |
| `news_trade_*` | handle_trade_callback | Trade from news alert |
| `tl_*` | handle_trade_callback | Translate news |
