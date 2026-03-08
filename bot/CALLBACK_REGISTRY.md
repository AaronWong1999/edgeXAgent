# Complete Callback Handler Registry — main.py

## Handler Functions Overview

There are **3 functions** that handle callback queries:
1. `handle_login_choice()` (line 245) — inside ConversationHandler for `/start` flow (state `WAITING_LOGIN_CHOICE`)
2. `handle_setai_provider()` (line 852) — inside ConversationHandler for `/setai` flow (state `WAITING_AI_CONFIG`, pattern `^setai_`)
3. `handle_trade_callback()` (line 972) — **global** CallbackQueryHandler (catches everything else)

**Note:** `handle_login_choice` delegates unrecognized callbacks to `handle_trade_callback` at line 371.
Many callbacks are handled in **BOTH** `handle_login_choice` and `handle_trade_callback` (duplicated).

---

## COMPLETE CALLBACK REGISTRY (Ordered by Line Number)

### ═══ handle_login_choice() — Lines 245-372 ═══

| # | Line | callback_data | Screen Title (msg text first 100 chars) | Buttons (callback_data values) | Back → |
|---|------|--------------|----------------------------------------|-------------------------------|--------|
| 1 | 250 | `logout_confirm` | "🚪 *Disconnect — Trade on edgeX*\n\nThis will log out your edgeX account. Are you sure?" | `logout_yes`, `logout_no` | N/A (confirm/cancel modal) |
| 2 | 262 | `logout_yes` | "🚪 *Disconnect — Trade on edgeX*\n\n✅ Successfully logged out." | `back_to_dashboard` | `back_to_dashboard` |
| 3 | 273 | `logout_no` | Dashboard text (via `_dashboard_text()`) | `trade_hub` or `show_login`, `ai_hub` or `ai_activate_prompt`, `news_settings` | Returns to dashboard |
| 4 | 282 | `back_to_start` | Dashboard text (via `_dashboard_text()`) | `trade_hub`/`show_login`, `ai_hub`/`ai_activate_prompt`, `news_settings` | IS the dashboard |
| 5 | 291 | `back_to_dashboard` | Dashboard text (via `_dashboard_text()`) | `trade_hub`/`show_login`, `ai_hub`/`ai_activate_prompt`, `news_settings` | IS the dashboard |
| 6 | 300 | `ai_activate_prompt` | "✨ *Activate AI — AI Agent*\n\nChoose how to power your Agent:" | `ai_edgex_credits`, `ai_own_key_setup`, `ai_use_free`, `back_to_dashboard` | `back_to_dashboard` |
| 7 | 309 | `show_login` | "🔗 *Connect edgeX — Trade on edgeX*\n\nChoose how to connect:" | `login_oauth`, `login_api`, `login_demo` (conditional), `back_to_dashboard` | `back_to_dashboard` |
| 8 | 322 | `login_oauth` | "⚡ *One-Click Login — Trade on edgeX*\n\nComing Soon! Waiting for edgeX team OAuth integrat..." | `show_login` | `show_login` |
| 9 | 340 | `login_demo` | Connects demo account → shows dashboard text | Dashboard buttons | Dashboard |
| 10 | 361 | `login_api` | "🔑 *Connect with API Key — Trade on edgeX*\n\n👉 *Step 1:* Go to edgex.exchange → *API Manag..." | (none — waits for text input) | N/A (enters WAITING_ACCOUNT_ID state) |

### ═══ handle_setai_provider() — Lines 852-873 ═══

| # | Line | callback_data | Screen Title | Buttons | Back → |
|---|------|--------------|-------------|---------|--------|
| 11 | 852 | `setai_openai` | "🔑 *OpenAI-compatible — AI Agent*\n\nWorks with: OpenAI, DeepSeek, Groq, NVIDIA, etc..." | (none — waits for text input) | N/A (enters WAITING_AI_CONFIG) |
| 12 | 852 | `setai_anthropic` | "🔑 *Anthropic — AI Agent*\n\n🔗 Get key at: console.anthropic.com..." | (none — waits for text input) | N/A (enters WAITING_AI_CONFIG) |
| 13 | 852 | `setai_gemini` | "🔑 *Google Gemini — AI Agent*\n\n🔗 Get key at: aistudio.google.com/apikey..." | (none — waits for text input) | N/A (enters WAITING_AI_CONFIG) |

### ═══ handle_trade_callback() — Lines 972-2780 ═══

| # | Line | callback_data | Screen Title (msg text first 100 chars) | Buttons (callback_data values) | Back → |
|---|------|--------------|----------------------------------------|-------------------------------|--------|
| 14 | 983 | `cancel_feedback` | "❌ Feedback cancelled." | `back_to_dashboard` | `back_to_dashboard` |
| 15 | 990 | `trade_hub` | "📈 *Trade on edgeX — Trade on edgeX*\n\n├ Equity: `$...`\n└ Available: `$...`" + positions | `quick_pnl`, `quick_close`, `quick_orders`, `quick_history`, `logout_confirm`, `back_to_dashboard` | `back_to_dashboard` |
| 16 | 990 | `quick_status` | (same as `trade_hub` — handled in same branch) | (same as trade_hub) | `back_to_dashboard` |
| 17 | 1074 | `ai_hub` | "🤖 *AI Agent — AI Agent*\n\n├ 🎭 Personality: `...`\n└ 📝 Memory: `...` msgs, `...` summaries" | `change_persona`, `ai_activate_prompt`, `settings_memory`, `back_to_dashboard` | `back_to_dashboard` |
| 18 | 1097 | `quick_pnl` | "📤 *Share PnL — Trade on edgeX*\n\n" + open positions + closed trades | `share_pnl_{contractId}`, `share_closed_{orderId}`, `quick_pnl_page_{n}`, `trade_hub` | `trade_hub` |
| 19 | 1097 | `quick_pnl_page_{n}` (startswith) | Same as `quick_pnl` but paginated | Same as quick_pnl | `trade_hub` |
| 20 | 1253 | `share_pnl_{contractId}` (startswith) | PnL share card: "──────────────────\n⬆️ *{sym}/USDT* · {side}..." | Forward to Chat (switch_inline_query) | N/A (sends new message) |
| 21 | 1332 | `share_closed_{orderId}` (startswith) | Closed trade share card: "──────────────────\n⬆️ *{sym}/USDT* · {side}..." | Forward to Chat (switch_inline_query) | N/A (sends new message) |
| 22 | 1405 | `quick_history` | "📜 *Recent Trades — Trade on edgeX*\n\n" + trade list | `trade_hub` | `trade_hub` |
| 23 | 1455 | `quick_close` | "💰 *Position — Trade on edgeX*\n\n" + position list | `close_confirm_{contractId}` per position, `close_confirm_all`, `trade_hub` | `trade_hub` |
| 24 | 1513 | `quick_orders` | "📋 *Open Orders — Trade on edgeX*\n\n{n} order(s):" + order list | `cancelone_confirm_{orderId}` per order, `cancelorders_confirm_all`, `trade_hub` | `trade_hub` |
| 25 | 1566 | `logout_confirm` (DUPLICATE) | "🚪 *Disconnect — Trade on edgeX*\n\nThis will log out your edgeX account. Are you sure?" | `logout_yes`, `logout_no` | N/A (confirm modal) |
| 26 | 1579 | `logout_yes` (DUPLICATE) | "🚪 *Disconnect — Trade on edgeX*\n\n✅ Successfully logged out." | `back_to_dashboard` | `back_to_dashboard` |
| 27 | 1590 | `logout_no` (DUPLICATE) | "🚪 *Disconnect — Trade on edgeX*\n\n❌ Logout cancelled. Your account is still connected." | `back_to_dashboard` | `back_to_dashboard` |
| 28 | 1596 | `show_login` (DUPLICATE) | "🔗 *Connect edgeX — Trade on edgeX*\n\nChoose how to connect:" | `login_oauth`, `login_api`, `login_demo` (conditional), `back_to_dashboard` | `back_to_dashboard` |
| 29 | 1610 | `login_oauth` (DUPLICATE) | "⚡ *One-Click Login — Trade on edgeX*\n\nComing Soon!..." | `show_login` | `show_login` |
| 30 | 1628 | `login_demo` (DUPLICATE) | Connects demo → dashboard text | Dashboard buttons | Dashboard |
| 31 | 1649 | `login_api` (DUPLICATE) | "🔑 *Connect with API Key — Trade on edgeX*\n\nPlease use the /start command..." | `show_login` | `show_login` |
| 32 | 1658 | `ai_edgex_credits` | "💳 *edgeX Balance — AI Agent*\n\nComing Soon! Waiting for edgeX team billing integration..." | `ai_activate_prompt` | `ai_activate_prompt` |
| 33 | 1677 | `ai_own_key` | "🔑 *AI Provider — AI Agent*\n\nChoose your provider:" | `setai_openai`, `setai_anthropic`, `setai_gemini`, `ai_activate_prompt` | `ai_activate_prompt` |
| 34 | 1684 | `back_to_start` (DUPLICATE) | Dashboard text | Dashboard buttons | IS the dashboard |
| 35 | 1684 | `back_to_dashboard` (DUPLICATE) | Dashboard text | Dashboard buttons | IS the dashboard |
| 36 | 1694 | `news_settings` | "📰 *Event Trading — Event Trading*\n\nAI-analyzed news with one-tap trade buttons..." | `news_toggle_{id}_{on/off}`, `news_freq_{id}`, `news_remove_{id}`, `news_add`, `news_trade_defaults`, `back_to_dashboard` | `back_to_dashboard` |
| 37 | 1699 | `news_noop_{...}` (startswith) | (no-op, just answers query) | N/A | N/A |
| 38 | 1703 | `news_toggle_{sourceId}_{on/off}` (startswith) | Re-renders news_settings main menu | Same as `news_settings` | `back_to_dashboard` |
| 39 | 1713 | `news_freq_{sourceId}` (startswith) | "⏱ *Push Frequency — Event Trading*\n\nHow many alerts per hour?\nCurrent: *{n}/hr*" | `news_setfreq_{sourceId}_{1,2,3,5,10}`, `news_settings` | `news_settings` |
| 40 | 1733 | `news_setfreq_{sourceId}_{n}` (startswith) | Re-renders news_settings main menu | Same as `news_settings` | `back_to_dashboard` |
| 41 | 1743 | `news_remove_{sourceId}` (startswith) | Re-renders news_settings main menu | Same as `news_settings` | `back_to_dashboard` |
| 42 | 1755 | `news_add` | "➕ *Add News Source — Event Trading*\n\nSend an MCP news server URL:..." | `news_settings` | `news_settings` |
| 43 | 1769 | `news_trade_defaults` | "⚙️ *Trade Defaults — Event Trading*\n\nLeverage: *{n}x*\nAmounts: *$...*\nTP: *+{n}%*\nSL: *-{n}%*" | `ntd_leverage`, `ntd_amounts`, `ntd_tp`, `ntd_sl`, `news_settings` | `news_settings` |
| 44 | 1789 | `ntd_leverage` | "⚙️ *Leverage — Trade Defaults*\n\nCurrent: *{n}x*\n\nSelect default leverage:" | `ntd_setlev_{2,3,5}`, `news_trade_defaults` | `news_trade_defaults` |
| 45 | 1806 | `ntd_setlev_{n}` (startswith) | Re-renders `news_trade_defaults` screen | Same as `news_trade_defaults` | `news_settings` |
| 46 | 1830 | `ntd_setamt_{a}_{b}_{c}` (startswith) | Re-renders `news_trade_defaults` screen | Same as `news_trade_defaults` | `news_settings` |
| 47 | 1853 | `ntd_settp_{pct}` (startswith) | Re-renders `news_trade_defaults` screen | Same as `news_trade_defaults` | `news_settings` |
| 48 | 1875 | `ntd_setsl_{pct}` (startswith) | Re-renders `news_trade_defaults` screen | Same as `news_trade_defaults` | `news_settings` |
| 49 | 1897 | `news_mute_{sourceId}` (startswith) | "🔕 Source muted" (toast) — removes reply markup | N/A | N/A |
| 50 | 1907 | `news_dismiss` | Deletes message or shows "✔️ Dismissed" | N/A | N/A |
| 51 | 1915 | `tl_{lang_code}` (startswith, e.g. `tl_zh`, `tl_ja`, `tl_ko`, `tl_ru`) | Translated news card: "*{source}: {translation}*" | Same buttons as original news card | N/A (sends new message) |
| 52 | 1992 | `nt_{asset}_{side}_{lev}_{notional}` (startswith) | "🔄 *{LONG/SHORT} {asset} — Trade on edgeX*\nGenerating trade plan (~${n}, {lev}x)..." → then trade confirmation | `confirm_trade`, `cancel_trade` (if TRADE) or `back_to_dashboard` | `back_to_dashboard` |
| 53 | 1992 | `news_trade_{asset}_{side}_{lev}_{notional}` (startswith) | Same as `nt_` above | Same | Same |
| 54 | 2094 | `settings_menu` | Redirects → same as `ai_hub`: "🤖 *AI Agent — AI Agent*..." | `change_persona`, `ai_activate_prompt`, `settings_memory`, `back_to_dashboard` | `back_to_dashboard` |
| 55 | 2118 | `settings_memory` | "📝 *Memory — AI Agent*\n\n├ Messages: `{n}`\n└ Summaries: `{n}`" | `memory_clear_confirm`, `ai_hub` | `ai_hub` |
| 56 | 2132 | `change_persona` | "🎭 *Personality — AI Agent*\n\nChoose your Agent's vibe:" | `persona_degen`, `persona_sensei`, `persona_coldblood`, `persona_shitposter`, `persona_professor`, `persona_wolf`, `persona_moe`, `ai_hub` | `ai_hub` |
| 57 | 2132 | `settings_persona` | (same as `change_persona`) | (same) | `ai_hub` |
| 58 | 2138 | `ai_activate_prompt` (DUPLICATE) | "✨ *Activate AI — AI Agent*\n\nChoose how to power your Agent:" | `ai_edgex_credits`, `ai_own_key_setup`, `ai_use_free`, `back_to_dashboard` | `back_to_dashboard` |
| 59 | 2147 | `ai_use_free` | "✅ *AI Activated — AI Agent*\n\n├ Provider: `Aaron's API`\n└ Model: `claude-sonnet-4.5`" | `change_persona`, `back_to_dashboard` | `back_to_dashboard` |
| 60 | 2162 | `ai_own_key_setup` | "🔑 *AI Provider — AI Agent*\n\nChoose your provider:" | `setai_openai`, `setai_anthropic`, `setai_gemini`, `ai_activate_prompt` | `ai_activate_prompt` |
| 61 | 2169 | `setai_{provider}` (startswith, outside ConvHandler) | "🔑 *AI Provider — AI Agent*\n\nUse /setai to configure your AI provider..." | `ai_hub` | `ai_hub` |
| 62 | 2180 | `persona_{name}` (startswith: `persona_degen`, `persona_sensei`, `persona_coldblood`, `persona_shitposter`, `persona_professor`, `persona_wolf`, `persona_moe`) | "🎭 *Personality Set — AI Agent*\n\n✅ Active: *{name}*\n\n_{greeting}_" | `back_to_dashboard` | `back_to_dashboard` |
| 63 | 2197 | `memory_clear_confirm` | "🗑 *Clear Memory — AI Agent*\n\nAll conversation history and preferences will be deleted..." | `memory_clear_yes`, `memory_clear_no` | N/A (confirm modal — sends new msg) |
| 64 | 2210 | `memory_clear_yes` | "🗑 *Clear Memory — AI Agent*\n\n✅ Memory cleared.\n\n├ Deleted: `{n}` messages..." | `back_to_dashboard` | `back_to_dashboard` |
| 65 | 2225 | `memory_clear_no` | "🗑 *Clear Memory — AI Agent*\n\n❌ Cancelled. Your memory is safe..." | `back_to_dashboard` | `back_to_dashboard` |
| 66 | 2233 | `cancel_trade` | "❌ *Trade Cancelled — Trade on edgeX*\n\nNo order was placed." | `back_to_dashboard` | `back_to_dashboard` |
| 67 | 2241 | `show_trade_plan` | Shows formatted trade plan (from `ai_trader.format_trade_plan(plan)`) | `confirm_trade`, `cancel_trade` | `cancel_trade` |
| 68 | 2259 | `confirm_trade` | "🔄 *Executing {LONG/SHORT} {asset} — Trade on edgeX*\nPlacing order on edgeX..." → then result | `back_to_dashboard` (on success/failure) | `back_to_dashboard` |
| 69 | 2383 | `close_confirm_{contractId}` (startswith, specific) | "🔴 *Market Close {symbol} {side} — Trade on edgeX*\n\n⚠️ This will market-close your {symbol}..." | `close_{contractId}`, `close_cancel` | `close_cancel` |
| 70 | 2383 | `close_confirm_all` (startswith, matched by `close_confirm_`) | "🔴 *Market Close All — Trade on edgeX*\n\n⚠️ This will market-close ALL open positions..." | `close_all_yes`, `close_cancel` | `close_cancel` |
| 71 | 2464 | `close_cancel` | "💰 *Position — Trade on edgeX*\n\n❌ Close cancelled. No positions were closed." | `back_to_dashboard` | `back_to_dashboard` |
| 72 | 2471 | `close_all_yes` | "🔴 *Close All — Trade on edgeX*\n\n" + per-position results | `back_to_dashboard` | `back_to_dashboard` |
| 73 | 2504 | `close_{contractId}` (startswith, after `close_confirm_` and `close_cancel` and `close_all_yes`) | On success: "⬆️ *Close {symbol} {side} — Trade on edgeX*\n\n✅ {side} position closed..." | `back_to_dashboard` | `back_to_dashboard` |
|    |      |               | On MARGIN_BLOCKED_BY_ORDERS: "⚠️ *Close {symbol} — Trade on edgeX*\n\nMargin insufficient..." | `cancelorders_{contractId}`, `close_{contractId}`, `vieworders_{contractId}`, `back_to_dashboard` | `back_to_dashboard` |
| 74 | 2618 | `cancelorders_{contractId_or_all}` (startswith) | "✅ *Orders Cancelled — Trade on edgeX*\n\n✅ {label} orders cancelled." or error | `back_to_dashboard` | `back_to_dashboard` |
| 75 | 2648 | `vieworders_{contractId}` (startswith) | "📋 *Open Orders for {symbol}* ({n}):" + order list | `cancelone_{orderId}` per order, `cancelorders_{contractId}`, `trade_hub`, `back_to_dashboard` | `trade_hub` |
| 76 | 2694 | `cancelone_confirm_{orderId}` (startswith) | "❌ *Cancel Order — Trade on edgeX*\n\n⚠️ Cancel this order?" + order details | `cancelone_{orderId}`, `cancel_dismiss` | `cancel_dismiss` |
| 77 | 2725 | `cancelorders_confirm_all` | "❌ *Cancel All Orders — Trade on edgeX*\n\n⚠️ Cancel ALL open orders?" + order list | `cancelorders_all`, `cancel_dismiss` | `cancel_dismiss` |
| 78 | 2757 | `cancel_dismiss` | "📋 *Orders — Trade on edgeX*\n\n❌ Cancelled. Orders kept." | `back_to_dashboard` | `back_to_dashboard` |
| 79 | 2764 | `cancelone_{orderId}` (startswith, after `cancelone_confirm_`) | "✅ *Order Cancelled — Trade on edgeX*\n\nOrder `{orderId}` cancelled successfully." or error | `back_to_dashboard` | `back_to_dashboard` |

---

## BUTTONS WITH NO HANDLER (Referenced in buttons but unhandled)

| callback_data | Where button appears | Issue |
|--------------|---------------------|-------|
| `ntd_amounts` | Line 1781+ (news_trade_defaults & re-renders) | **NO HANDLER** — falls through all checks silently |
| `ntd_tp` | Line 1782+ (news_trade_defaults & re-renders) | **NO HANDLER** — falls through all checks silently |
| `ntd_sl` | Line 1783+ (news_trade_defaults & re-renders) | **NO HANDLER** — falls through all checks silently |

---

## NAVIGATION TREE

```
Dashboard (back_to_dashboard / back_to_start)
├── 📈 Trade on edgeX (trade_hub / quick_status)
│   ├── 📤 Share PnL (quick_pnl)
│   │   ├── share_pnl_{contractId} → sends share card
│   │   ├── share_closed_{orderId} → sends share card
│   │   └── quick_pnl_page_{n} → pagination
│   ├── 💰 Position (quick_close)
│   │   ├── close_confirm_{contractId} → close_{contractId}
│   │   ├── close_confirm_all → close_all_yes
│   │   └── close_cancel
│   ├── 📋 Orders (quick_orders)
│   │   ├── cancelone_confirm_{orderId} → cancelone_{orderId}
│   │   ├── cancelorders_confirm_all → cancelorders_all
│   │   └── cancel_dismiss
│   ├── 📜 History (quick_history)
│   └── 🚪 Disconnect (logout_confirm)
│       ├── logout_yes
│       └── logout_no
│
├── 🤖 AI Agent (ai_hub)
│   ├── 🎭 Personality (change_persona / settings_persona)
│   │   └── persona_{name} (7 options)
│   ├── 🔑 Provider (ai_activate_prompt)
│   │   ├── 💳 edgeX Balance (ai_edgex_credits) — coming soon
│   │   ├── 🔑 Own Key (ai_own_key_setup / ai_own_key)
│   │   │   ├── setai_openai → (text input in ConvHandler)
│   │   │   ├── setai_anthropic → (text input in ConvHandler)
│   │   │   └── setai_gemini → (text input in ConvHandler)
│   │   └── ⚡ Aaron's API (ai_use_free)
│   └── 📝 Memory (settings_memory)
│       └── 🗑 Clear (memory_clear_confirm)
│           ├── memory_clear_yes
│           └── memory_clear_no
│
├── 📰 Event Trading (news_settings)
│   ├── news_toggle_{id}_{on/off}
│   ├── news_freq_{id} → news_setfreq_{id}_{n}
│   ├── news_remove_{id}
│   ├── ➕ Add Source (news_add) → awaits MCP URL text
│   └── ⚙️ Trade Defaults (news_trade_defaults)
│       ├── ntd_leverage → ntd_setlev_{n}
│       ├── ntd_amounts ⚠️ NO HANDLER
│       ├── ntd_tp ⚠️ NO HANDLER
│       └── ntd_sl ⚠️ NO HANDLER
│
├── 🔗 Connect edgeX (show_login)
│   ├── login_oauth (coming soon)
│   ├── login_api → text input flow (ConvHandler)
│   └── login_demo
│
└── Trade Execution (from natural language / news)
    ├── show_trade_plan → confirm_trade / cancel_trade
    ├── confirm_trade → executes order
    ├── cancel_trade
    ├── nt_{asset}_{side}_{lev}_{notional} (news one-tap)
    └── news_trade_{asset}_{side}_{lev}_{notional} (news one-tap)

Other standalone:
├── cancel_feedback
├── settings_menu → redirects to ai_hub
├── news_mute_{sourceId} (from news alert cards)
├── news_dismiss (from news alert cards)
├── news_noop_{...} (no-op)
└── tl_{lang} (inline translation: zh, ja, ko, ru)
```

---

## DUPLICATE HANDLERS (same callback_data handled in both handle_login_choice AND handle_trade_callback)

| callback_data | handle_login_choice line | handle_trade_callback line | Behavior difference |
|--------------|------------------------|--------------------------|-------------------|
| `logout_confirm` | 250 | 1566 | Identical |
| `logout_yes` | 262 | 1579 | Identical |
| `logout_no` | 273 (→ dashboard) | 1590 (→ "cancelled" msg) | **DIFFERENT** — login_choice returns dashboard, trade_callback shows cancelled text |
| `back_to_start` | 282 | 1684 | Identical |
| `back_to_dashboard` | 291 | 1684 | Identical |
| `show_login` | 309 | 1596 | Identical |
| `login_oauth` | 322 | 1610 | Identical |
| `login_demo` | 340 | 1628 | Identical |
| `login_api` | 361 (enters ConvHandler text input) | 1649 (tells user to use /start) | **DIFFERENT** — login_choice starts flow, trade_callback redirects |
| `ai_activate_prompt` | 300 | 2138 | Identical |

---

## STARTSWITH PATTERN OVERLAP RISKS

| Pattern | Line | Risk |
|---------|------|------|
| `close_confirm_` | 2383 | Must be checked BEFORE `close_` (2504) — ✅ it is |
| `close_` | 2504 | Catches `close_cancel`, `close_all_yes` etc — but those are checked first ✅ |
| `cancelone_confirm_` | 2694 | Must be checked BEFORE `cancelone_` (2764) — ✅ it is |
| `cancelone_` | 2764 | Catches anything starting with `cancelone_` not already matched |
| `nt_` | 1992 | Matches `ntd_leverage`, `ntd_setlev_`, `ntd_setamt_`, `ntd_settp_`, `ntd_setsl_` — but those are checked BEFORE this ✅ |
| `news_trade_` | 1992 | Only matches `news_trade_{asset}_{side}_{lev}_{notional}` — checked after `news_trade_defaults` (1769) ✅ |

---

## TOTAL COUNT: 79 distinct callback handler branches + 3 unhandled button callback_data values
