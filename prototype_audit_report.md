# Prototype vs Code Audit Report

Comparing `tg_prototype.html` (v6) with `bot/main.py`.

---

## DASHBOARD

### dash_new — New User
- **Title:** ✅ Match. Prototype: `🤖 **edgeX Agent — Your Own AI Trading Agent**` / Code `_dashboard_text()`: `🤖 *edgeX Agent — Your Own AI Trading Agent*` (Markdown bold syntax differs: HTML uses `**`, code uses `*`, both render bold in Telegram — OK)
- **Body text:** ✅ Match. edgeX line, AI line, example phrases all match.
- **Button 1:** ✅ `🔗 Connect edgeX` → `callback_data="show_login"` — matches code `_dashboard_keyboard(has_edgex=False)`
- **Button 2:** ✅ `✨ Activate AI` → `callback_data="ai_activate_prompt"` — matches code
- **Button 3:** ✅ `📰 Event Trading` → `callback_data="news_settings"` — matches code
- **Footer:** ✅ Accurate

### dash_conn — Connected
- **Title:** ✅ Same dashboard text
- **Button 1:** ✅ `📈 Trade on edgeX` → `callback_data="trade_hub"` — matches code `_dashboard_keyboard(has_edgex=True)`
- **Button 2:** ✅ `✨ Activate AI` → `callback_data="ai_activate_prompt"` — matches code `has_ai=False`
- **Button 3:** ✅ `📰 Event Trading` → `callback_data="news_settings"` — matches

### dash_full — Full State
- **Button 1:** ✅ `📈 Trade on edgeX` → `trade_hub`
- **Button 2:** ✅ `🤖 AI Agent` → `ai_hub` — matches code `has_ai=True`
- **Button 3:** ✅ `📰 Event Trading` → `news_settings`

---

## TRADE MODULE

### show_login — 🔗 Connect edgeX
- **Title:** ✅ `🔗 **Connect edgeX — Trade on edgeX**` matches code
- **Body:** ✅ "Choose how to connect:" matches
- **Button 1:** ✅ `⚡ One-Click OAuth (soon)` → `login_oauth` — matches
- **Button 2:** ✅ `🔑 Connect with API Key` → `login_api` — matches
- **Button 3:** ✅ `👤 Aaron's Account (temp)` → `login_demo` — matches (conditional on config)
- **Button 4:** ✅ `🔙 Back` → `back_to_dashboard` — matches

### trade_hub — 📈 Trade Hub
- **Title:** ✅ `📈 **Trade on edgeX — Trade on edgeX**` matches code
- **Body format:** ✅ Equity/Available format matches. Position format `🟢 BTC LONG $712.00 (5x) @ $71,200.00 | PnL: +$12.30` matches code pattern.
- **Button 1:** ✅ `📈 P&L` → `quick_pnl`
- **Button 2:** ⚠️ **DISCREPANCY** — Prototype shows `💰 Position` but code shows `💰 Position` and `📋 Orders` on the **same row** (2 buttons). Prototype shows each as full-width. Code layout: `[📈 P&L]` on row 1, then `[💰 Position, 📋 Orders]` on row 2, then `[📜 History, 🚪 Disconnect]` on row 3, then `[🔙 Back]`. Prototype shows all buttons as full-width (class `f`) except `💰 Position` (no `f`), `📋 Orders` (no `f`), `📜 History` (no `f`), `🚪 Disconnect` (no `f`). So the prototype actually does show some buttons as half-width, which roughly matches the code's row grouping. **However**, the code groups `📜 History` and `🚪 Disconnect` on the **same row**, while the prototype has `🚪 Disconnect` as its own half-width button next to History — which matches.
- **Button labels:** ✅ All labels match: `📈 P&L`, `💰 Position`, `📋 Orders`, `📜 History`, `🚪 Disconnect`, `🔙 Back`
- **Button callback_data:** ✅ `quick_pnl`, `quick_close`, `quick_orders`, `quick_history`, `logout_confirm`, `back_to_dashboard` — all match

### login_oauth — ⚡ One-Click Login
- **Title:** ✅ `⚡ **One-Click Login — Trade on edgeX**` matches code
- **Body text:** ✅ OAuth spec text matches exactly (POST endpoint, client_id, redirect_uri, scope, response_type, callback URL)
- **Button:** ✅ `🔙 Back` → `show_login`

### login_api — 🔑 Connect with API Key
- **Title:** ✅ `🔑 **Connect with API Key — Trade on edgeX**` matches code
- **Body:** ✅ "Go to edgex.exchange → **API Management**\nCopy your **Account ID** and send it to me:" — matches code exactly

### login_demo — 👤 Aaron's Account
- **Title/Body:** ✅ Prototype: `🔄 Connecting to Aaron's edgeX account...` — Code: `🔄 Connecting to Aaron's edgeX account...` — matches
- **Behavior:** ✅ Auto-connects + activates AI as described

### quick_pnl — 📈 P&L
- **Title:** ✅ `📈 **P&L — Trade on edgeX**` matches code
- **Open positions section title:** ⚠️ **DISCREPANCY** — Prototype shows `**🟢 Open Positions:**` but code shows `**🟢 Open Positions:**` — ✅ matches
- **Open position format:** ⚠️ **DISCREPANCY** — Prototype: `🟢 **BTC LONG** (5x) | $712.00 | PnL: +$12.30`. Code: `{pnl_emoji} **{symbol} {side}**{lev_str} | {pos_val} | PnL: {pnl_str}`. The code uses `p.get("side", "?")` which returns the raw API value (likely "BUY"/"SELL"), NOT "LONG"/"SHORT". Prototype shows "LONG"/"SHORT" but code would show "BUY"/"SELL" at this screen. **MISMATCH: Prototype says LONG/SHORT, code uses raw API side (BUY/SELL).**
- **Closed section title:** ⚠️ **DISCREPANCY** — Prototype: `**🔴 Recent Closed (5):**`. Code: `**🔴 Recent Closed ({total_items}):**`. Label matches, count is dynamic — OK.
- **Closed trade format:** ⚠️ **DISCREPANCY** — Prototype: `🟢 BTC BUY 0.01 @ $71,234 | PnL: +$2.34`. Code: `{side_emoji} {sym} {side} {fill_size} @ ${fill_price} | PnL: {pnl_str}`. Code does NOT include order type or leverage in the closed trade format here. **Prototype omits type+leverage too, so this matches.**
- **Share buttons:** ✅ `📤 Share BTC PnL (+$12.30)` → `share_pnl_{cid}` — matches code pattern
- **Pagination buttons:** ✅ `◀ Prev` / `Next ▶` — matches code
- **Back button:** ✅ `🔙 Back` → `trade_hub` — matches

### quick_close — 💰 Position
- **Title:** ✅ `💰 **Position — Trade on edgeX**` matches code
- **Position format:** ✅ Prototype format with Value/Entry/PnL tree structure matches code exactly
- **Close buttons:** ✅ `🔴 Market Close BTC LONG` → `close_confirm_{cid}` — matches code. Code uses `f"🔴 Market Close {symbol} {side}"` where side comes from `p.get("side", "?")` — **same BUY/SELL vs LONG/SHORT issue as quick_pnl**.
- **Close All button:** ✅ `🔴 Market Close All` → `close_confirm_all` — matches
- **Back:** ✅ `🔙 Back` → `trade_hub`

### close_confirm — ⚠️ Confirm Close
- **Title:** ✅ `🔴 **Market Close BTC — Trade on edgeX**` — code: `🔴 **Market Close {symbol} — Trade on edgeX**` — matches pattern
- **Body:** ✅ "⚠️ This will market-close your BTC position. Are you sure?" — matches code pattern `This will market-close your {symbol} position. Are you sure?`
- **Button 1:** ✅ `✅ Yes, close BTC` → `close_{target}` — matches code `f"✅ Yes, close {symbol}"`
- **Button 2:** ✅ `❌ Cancel` → `quick_close` — matches code

### quick_orders — 📋 Open Orders
- **Title:** ✅ `📋 **Open Orders — Trade on edgeX**` — matches code
- **Order count:** ✅ `{len(orders)} order(s):` — matches prototype
- **Order format:** ✅ Prototype: `• BTC BUY LIMIT (5x) | Size: 100 | Price: $70,000 | Now: $71,234 (1.7% away)`. Code: `• {sym} {o_side} {o_type}{lev_str} | Size: {o_size} | Price: ${o_price}{dist_str}` where dist_str = `| Now: ${cur_f:.2f} ({dist_pct:.1f}% away)`. **Matches.**
- **Cancel buttons:** ✅ `❌ Cancel BTC BUY 100@70000` → `cancelone_confirm_{id}` — matches code pattern `f"❌ Cancel {sym} {o_side} {o_size}@{o_price}"`
- **Cancel All:** ✅ `❌ Cancel All Orders` → `cancelorders_confirm_all` — matches
- **Back:** ✅ `🔙 Back` → `trade_hub`

### cancel_confirm — ⚠️ Confirm Cancel
- **Title:** ✅ `❌ **Cancel Order — Trade on edgeX**` — matches code
- **Body:** ✅ "Cancel this order?" — matches code
- **Button 1:** ✅ `✅ Yes, cancel` → `cancelone_{order_id}` — matches code
- **Button 2:** ✅ `❌ Keep order` → `quick_orders` — matches code

### quick_history — 📜 Recent Trades
- **Title:** ✅ `📜 **Recent Trades — Trade on edgeX**` — matches code
- **Trade format:** ⚠️ **DISCREPANCY** — Prototype: `🟢 BTC BUY LIMIT (5x) 0.01 @ $71,234.00 | PnL: +$2.3400 | 03/05 08:00`. Code: `{side_emoji} {sym} {side}{type_str}{lev_str} {fill_size} @ {price_str}{pnl_str}{ts_str}`. This matches the pattern (type + leverage are included). ✅ Match.
- **Back button:** ✅ `🔙 Back` → `trade_hub`

### logout_confirm — 🚪 Disconnect
- **Title:** ✅ `🚪 **Disconnect — Trade on edgeX**` — matches code
- **Body:** ✅ "This will log out your edgeX account. Are you sure?" — matches code
- **Button 1:** ✅ `✅ Yes, logout` → `logout_yes` — matches code
- **Button 2:** ✅ `❌ Cancel` → `logout_no` — matches code

---

## AI MODULE

### ai_activate — ✨ Activate AI
- **Title:** ✅ `✨ **Activate AI — AI Agent**` — matches code
- **Body:** ✅ "Choose how to power your Agent:" — matches code
- **Button 1:** ⚠️ **DISCREPANCY** — Prototype: `💳 Use edgeX Account Balance` (grayed out). Code `_ai_activate_keyboard()`: `💳 Use edgeX Account Balance` → `ai_edgex_credits`. **Label matches, but prototype shows it as GRAYED (gy class), while code sends it as a normal clickable button.** The code does handle the click by showing "Coming Soon", so functionally it's the same. Cosmetic difference only.
- **Button 2:** ✅ `🔑 Use My Own API Key` → `ai_own_key_setup` — matches
- **Button 3:** ✅ `⚡ Use Aaron's API (temp)` → `ai_use_free` — matches

### ai_hub — 🤖 AI Agent Hub
- **Title:** ✅ `🤖 **AI Agent — AI Agent**` — matches code
- **Info display:** ✅ Personality/Provider/Memory format matches code exactly
- **Button 1:** ✅ `🎭 Personality` → `change_persona` — matches code
- **Button 2:** ✅ `🔑 AI Provider` → `ai_activate_prompt` — matches code
- **Button 3:** ✅ `📝 Memory` → `settings_memory` — matches code
- **Button 4:** ✅ `🔙 Back` → `back_to_dashboard` — matches code

### ai_credits — 💳 edgeX Balance
- **Title:** ✅ `💳 **edgeX Balance — AI Agent**` — matches code
- **Body:** ✅ "Coming Soon.\nUse /setai to add your own API key." — matches code
- **Back button:** ✅ `🔙 Back` → `ai_activate_prompt` — matches code

### ai_own_key — 🔑 AI Provider
- **Title:** ✅ `🔑 **AI Provider — AI Agent**` — matches code
- **Body:** ✅ "Choose your provider:" — matches code
- **Buttons:** ✅ `OpenAI / DeepSeek`, `Anthropic (Claude)`, `Google Gemini` — matches `_setai_provider_keyboard()` exactly

### ai_free — ⚡ Aaron's API (personality selection after activation)
- **Title:** ✅ `✅ **AI Activated — AI Agent**` — matches code (`ai_use_free` handler)
- **Body:** ✅ "Choose your Agent's personality:" — matches code
- **Personality buttons:** ✅ All 7 personalities match code `PERSONA_BUTTONS`: 🔥 Degen, 🎯 Sensei, 🤖 Cold Blood, 👀 Shitposter, 📚 Professor, 🐺 Wolf, 🌸 Moe
- **Back button:** ✅ `🔙 Back` → `ai_hub` — matches code

### persona — 🎭 Personality
- **Title:** ✅ `🎭 **Personality — AI Agent**` — matches code (`change_persona` / `settings_persona` handler)
- **Body:** ⚠️ **DISCREPANCY** — Prototype: "Choose your Agent's **vibe**:" Code: "Choose your Agent's **vibe**:" — ✅ Actually matches.
- **Personality buttons:** ✅ Same 7 personalities + Back. Matches `PERSONA_BUTTONS`.
- **Back button:** ✅ `🔙 Back` → `ai_hub` — matches code

### mem — 📝 Memory
- **Title:** ✅ `📝 **Memory — AI Agent**` — matches code
- **Info display:** ✅ Messages/Summaries/Preferences format matches code
- **Button 1:** ✅ `🗑 Clear Memory` → `memory_clear_confirm` — matches code
- **Button 2:** ✅ `🔙 Back` → `ai_hub` — matches code

### mem_clear — 🗑 Clear Memory
- **Title:** ✅ `🗑 **Clear Memory — AI Agent**` — matches code
- **Body:** ✅ "All conversation history and preferences will be deleted." — matches code
- **Button 1:** ✅ `✅ Yes, clear all` → `memory_clear_yes` — matches code
- **Button 2:** ✅ `❌ Keep` → `memory_clear_no` — matches code

---

## EVENT TRADING

### news_hub — 📰 Event Trading Hub
- **Title:** ✅ `📰 **Event Trading — Event Trading**` — matches code `_news_main_menu()`
- **Body:** ✅ "AI-analyzed news with one-tap trade buttons." — matches code
- **Source display:** ✅ Status icon + source name + frequency format matches
- **Per-source buttons:** ✅ Toggle (❌/✅) / ⏱ Frequency / 🗑 — matches code
- **Add button:** ✅ `➕ Add News Source` → `news_add` — matches
- **Back:** ✅ `🔙 Back` → `back_to_dashboard` — matches

### news_freq — ⏱ Push Frequency
- **Title:** ✅ `⏱ **Push Frequency — Event Trading**` — matches code (uses `*` Markdown)
- **Body:** ✅ "How many alerts per hour?\nCurrent: **{current}/hr**" — matches code
- **Frequency options:** ✅ 1/hr, 2/hr, 3/hr, 5/hr, 10/hr — matches code `options = [1, 2, 3, 5, 10]`
- **Active highlight:** ✅ Code uses `> ` prefix for current value — matches prototype's `> 2/hr` blue button
- **Back:** ✅ `🔙 Back` → `news_settings` — matches code

### news_add — ➕ Add Source
- **Title:** ✅ `➕ **Add News Source — Event Trading**` — matches code (uses `*` Markdown)
- **Body:** ✅ "Choose a topic:" — matches code
- **Topic buttons:** ✅ `💰 Bitcoin News`, `💠 Ethereum News`, `🌍 DeFi News` — matches code exactly
- **Back:** ✅ `🔙 Back` → `news_settings` — matches code

---

## PUSH LAYER

### trade_plan — 📋 Trade Plan
- **Title:** ⚠️ **DISCREPANCY** — Prototype: `🟢 **Trade Plan — Trade on edgeX**`. Code (`format_trade_plan`): `{side_emoji} **Trade Plan — Trade on edgeX**`. The side_emoji is 🟢 for BUY, 🔴 for SELL. The prototype always shows 🟢 because the example is BUY. **Format matches.**
- **Body format:** ✅ `BUY BTC (5x)` + Entry/Size/Value/TP/SL tree + Confidence bar — matches code `format_trade_plan()` exactly
- **Buttons:** ✅ `✅ Confirm Execute` → `confirm_trade`, `❌ Cancel` → `cancel_trade` — matches code

### trade_exec — 🔄 Executing
- **Title:** ✅ `🔄 **Executing LONG BTC — Trade on edgeX**` — matches code `f"🔄 **Executing {side_word} {plan.get('asset', '')} — Trade on edgeX**"`
- **Body:** ✅ "Placing order on edgeX..." — matches code

### trade_ok — ✅ Result (LONG/SHORT)
- **Title:** ✅ `🟢 **LONG BTC — Trade on edgeX**` — matches code pattern `f"{side_emoji} **{side_word} {plan['asset']} — Trade on edgeX**"`
- **Body:** ✅ `✅ Order Placed!` + Entry/Size/Value/TP/SL/Order ID tree — matches code
- **Buttons:** ⚠️ **DISCREPANCY** — Prototype shows: `📊 BTC Position`, `📈 Live P&L`, `🔴 Close BTC`, `📜 History`, `🏠 Main Menu`. Code shows: `📊 {asset} Position` → `quick_status`, `📈 Live P&L` → `quick_pnl`, `🔴 Close {asset}` → `close_{contract_id}`, `📜 History` → `quick_history`, `🏠 Main Menu` → `back_to_dashboard`. **Labels match pattern. Callback data matches.**

### trade_cancel — ❌ Cancelled
- **Title:** ✅ `❌ **Trade Cancelled — Trade on edgeX**` — matches code
- **Body:** ✅ "No order was placed." — matches code
- **Buttons:** ✅ `📈 Trade on edgeX` → `trade_hub`, `🏠 Main Menu` → `back_to_dashboard` — matches code

### trade_err — ❌ Blocked (Trade Blocked)
- **Title:** ✅ `❌ **Trade Blocked — Trade on edgeX**` — matches code (pre-trade check path)
- **Body:** ✅ `Insufficient balance (available: $12.34)` — matches code pattern
- **Buttons:** ⚠️ **DISCREPANCY** — Prototype: `🔴 Close a Position`, `📋 Cancel Orders`, `💰 Deposit USDT` (URL button), `📊 Status`, `🏠 Main Menu`. Code (pre_trade_check insufficient balance path): `🔴 Close a Position` → `quick_close`, `📋 Cancel Orders` → `quick_orders`, `💰 Deposit USDT` → URL, `📊 Status` → `quick_status`, `🏠 Main Menu` → `back_to_dashboard`. **Matches.** But the code's error path from `place_order` failure uses a slightly different button set (uses `_friendly_order_error` + error_rows) — may not always show `📋 Cancel Orders` button. The prototype only shows one "Blocked" variant.

### close_ok — ✅ Closed
- **Title:** ⚠️ **DISCREPANCY** — Prototype: `🟢 **Close BTC — Trade on edgeX**`. Code: `{pnl_emoji} **Close {symbol} — Trade on edgeX**`. The emoji depends on P&L (🟢 if positive, 🔴 if negative). Prototype always shows 🟢 as the example is profitable. **Pattern matches.**
- **Body:** ✅ `✅ LONG position closed` + Entry/Size/Realized P&L/Balance/Order ID tree — Code: `✅ {side} position closed` + same tree. **Matches.**
- **Buttons:** ✅ Prototype: `📊 Status`, `📈 P&L`, `📜 History`, `📋 Orders`, `🏠 Main Menu`. Code: `📊 Status` → `quick_status`, `📈 P&L` → `quick_pnl`, `📜 History` → `quick_history`, `📋 Orders` → `quick_orders`, `🏠 Main Menu` → `back_to_dashboard`. **Matches.**

### share_pnl — 📤 Share PnL
- **Title/Format:** ⚠️ **DISCREPANCY** — Prototype: `📈 **BTC LONG** (5x)\n\n💰 P&L: **+$12.30** (+8.2%)\n├ Entry: $71,200.00\n├ Value: $712.00\n└ 🟢\n\n⚡ Traded on edgeX via @edgeXAgentBot`. Code: `📈 **{symbol} {side}**{lev_str}\n\n💰 P&L: **{pnl_str}** ({roi_str})\n├ Entry: {entry_str}\n├ Value: {pos_val}\n└ {pnl_emoji}\n\n⚡ Traded on edgeX via @edgeXAgentBot`. **Pattern matches.** However, same issue: `side` from API is likely "BUY"/"SELL", not "LONG"/"SHORT". **Prototype says LONG, code may show BUY.**

### logout_done — 🚪 Logged Out
- **Title:** ✅ `🚪 **Disconnect — Trade on edgeX**` — matches code
- **Body:** ✅ `✅ Logged out. Use /start to reconnect.` — matches code
- **Button:** ✅ `🔗 Reconnect` → `show_login` — matches code

---

## SUMMARY OF ALL DISCREPANCIES

### 1. BUY/SELL vs LONG/SHORT terminology (MEDIUM severity)
**Screens affected:** `quick_pnl`, `quick_close`, `share_pnl`
- The prototype consistently shows **LONG/SHORT** for position sides
- The `trade_hub` screen correctly derives LONG/SHORT from the position size sign: `side = "LONG" if size_f > 0 else "SHORT"`
- But `quick_pnl`, `quick_close`, and `share_pnl` use `p.get("side", "?")` directly from the API, which typically returns **BUY/SELL** instead of LONG/SHORT
- The `quick_history` screen also uses raw `side` but the prototype matches that (shows BUY/SELL for historical trades)

### 2. ai_activate button styling (COSMETIC, LOW severity)
**Screen:** `ai_activate`
- Prototype shows `💳 Use edgeX Account Balance` as grayed/disabled (gy class)
- Code sends it as a normal clickable button (functionally shows "Coming Soon" when clicked)
- No functional impact, but visual representation differs

### 3. No other text/title/button-label/callback_data discrepancies found
All other screens match exactly in:
- Title text (including emoji)
- Body text patterns
- Button labels  
- Button callback_data values
- Navigation flow (Back button destinations)
- Button ordering
