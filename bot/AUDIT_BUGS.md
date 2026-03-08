# Deep Code Audit — `/bot/main.py` Bug Report

**Audited file:** `/Users/aaron/Desktop/aaron/edgeXAgent/bot/main.py` (~3501 lines)
**Date:** 2026-03-06

---

## BUG #1 — CRITICAL: Unreachable Code in News Trade Handler (`nt_` / `news_trade_`)

**File:** `main.py`, lines ~2055–2130
**Severity:** CRITICAL

**Description:**
In the `nt_` / `news_trade_` callback handler (starting at line 2039), after parsing the callback data parts and the `else` branch (invalid data → early return at line 2054), the remaining trade execution code (lines 2056–2130) is **indented one level too deep** — it's inside the `else` block that already returned. This means **all news-triggered trades are completely dead code** and will never execute.

The code structure is:
```python
if query.data.startswith("nt_") and len(parts) >= 5:
    asset = parts[1]
    ...
elif len(parts) >= 6:
    asset = parts[2]
    ...
else:
    await query.answer("❌ Invalid trade data")
    return

    # ← THIS IS UNREACHABLE — indented under the else block
    user = db.get_user(user_id)
    if not user or not _has_edgex(user):
        ...
```

All code after the `return` in the `else` block (user check, AI check, trade generation, execution) is unreachable. When users tap trade buttons on news alerts, the bot parses the params but **never executes any trade**.

**Suggested Fix:**
De-indent the trade execution code (lines ~2056–2130) by one level so it's at the same level as the `if/elif/else` block.

---

## BUG #2 — HIGH: Missing `query.answer()` in Multiple Callback Handlers

**File:** `main.py`, various lines
**Severity:** HIGH

**Description:**
Several callback handlers in `handle_trade_callback()` and `handle_login_choice()` do not call `query.answer()`, which means the Telegram loading spinner will hang indefinitely for the user. Affected handlers:

1. **`cancel_feedback`** (line 985) — No `query.answer()` before `edit_message_text`
2. **`ai_hub`** (line 1076) — No `query.answer()`
3. **`news_settings`** (line 1696) — No `query.answer()`
4. **`news_toggle_*`** (line 1705) — No `query.answer()`
5. **`news_freq_*`** (line 1715) — No `query.answer()`
6. **`news_setfreq_*`** (line 1735) — No `query.answer()`
7. **`news_remove_*`** (line 1745) — No `query.answer()`
8. **`news_add`** (line 1757) — No `query.answer()`
9. **`news_trade_defaults`** (line 1771) — No `query.answer()`
10. **`ntd_leverage`** (line 1791) — No `query.answer()`
11. **`ntd_setlev_*`** (line 1808) — No `query.answer()`
12. **`ntd_setamt_*`** (line 1832) — No `query.answer()`
13. **`ntd_settp_*`** (line 1855) — No `query.answer()`
14. **`ntd_setsl_*`** (line 1877) — No `query.answer()`
15. **`ntd_amounts`** (line 1899) — No `query.answer()`
16. **`ntd_tp`** (line 1914) — No `query.answer()`
17. **`ntd_sl`** (line 1929) — No `query.answer()`
18. **`settings_menu`** (line 2141) — No `query.answer()`
19. **`settings_memory`** (line 2165) — No `query.answer()`
20. **`ai_activate_prompt`** (line 2185) — No `query.answer()` (in handle_trade_callback)
21. **`ai_use_free`** (line 2194) — No `query.answer()`
22. **`ai_own_key_setup`** (line 2209) — No `query.answer()`
23. **`setai_*`** (line 2216) — No `query.answer()`
24. **`persona_*`** (line 2227) — calls `query.answer()` with persona name but AFTER `safe_edit()` which may fail
25. **`back_to_start/back_to_dashboard`** (line 1688) — No `query.answer()` (in handle_trade_callback version)
26. **`tl_*` (translation)** (line 1962) — No `query.answer()` — user waits for AI translation with spinner

Note: `handle_login_choice()` at the top does call `query.answer()` once at entry (line 245), which covers callbacks routed through it. But `handle_trade_callback()` also calls it at entry (line 976). The issue is that many paths in the code flow through handle_trade_callback's individual if-blocks that call `query.answer()` again (redundantly), while some don't — but since the entry-level call covers it, the truly problematic ones are when `handle_trade_callback` is called from within `handle_login_choice` line 369 (`await handle_trade_callback(update, context)`) where `query.answer()` was already called at line 245, so there's no spinner issue from that path.

**Actual Impact:** Since `handle_trade_callback()` calls `query.answer()` at line 976 at the top, most paths ARE covered. However, in some branches that call `await query.answer()` again (e.g., line 993, 1100), a `BadRequest` error could occur if already answered (though it's in a try/except). The real issue is code clarity and redundant answer calls causing log warnings.

**Revised Severity:** MEDIUM (most paths are covered by the entry-level call)

**Suggested Fix:**
Remove the redundant `await query.answer()` calls inside individual branches since the entry-level call at line 976 already handles it. Or restructure to only call it once at entry.

---

## BUG #3 — HIGH: Duplicate Callback Handlers Between `handle_login_choice` and `handle_trade_callback`

**File:** `main.py`
**Severity:** HIGH

**Description:**
The following callback_data patterns are handled in BOTH `handle_login_choice()` and `handle_trade_callback()`:
- `logout_confirm` (lines 252 and 1568)
- `logout_yes` (lines 264 and 1581)
- `logout_no` (lines 275 and 1592)
- `back_to_start` / `back_to_dashboard` (lines 284/293 and 1688)
- `show_login` (lines 311 and 1598)
- `login_oauth` (lines 324 and 1612)
- `login_demo` (lines 342 and 1630)
- `login_api` (lines 363 and 1651)
- `ai_activate_prompt` (lines 302 and 2185)

Furthermore, `handle_login_choice()` line 369 falls through to `handle_trade_callback()` for unrecognized callbacks. This creates confusing control flow where callbacks may be handled differently depending on whether the user is in the ConversationHandler state or not.

**Impact:** The `login_api` handler behaves differently in the two locations: in `handle_login_choice()` (line 363) it prompts for account ID and returns `WAITING_ACCOUNT_ID`, while in `handle_trade_callback()` (line 1651) it tells the user to use `/start` instead. If the ConversationHandler state is lost (which can happen), the user gets stuck.

**Suggested Fix:**
Consolidate duplicate handlers. Have `handle_login_choice` delegate to `handle_trade_callback` earlier, or extract shared handlers into utility functions.

---

## BUG #4 — HIGH: `handle_login_choice` Returns `None` for `back_to_dashboard`

**File:** `main.py`, line 300
**Severity:** HIGH

**Description:**
The `back_to_dashboard` handler in `handle_login_choice()` does `return` (implicit `None`) without returning a ConversationHandler state. When `back_to_dashboard` is clicked while in the setup ConversationHandler, this returns `None` which is equivalent to not moving to any state — the conversation remains in whatever state it was in. The user is stuck in the conversation handler and their next text message will be routed to the wrong handler (e.g., `receive_account_id` instead of `handle_message`).

**Suggested Fix:**
Change `return` to `return ConversationHandler.END` on line 300.

---

## BUG #5 — HIGH: `pending_plans` Is a Global Dict With No TTL/Cleanup

**File:** `main.py`, line 32 (`pending_plans = {}`)
**Severity:** HIGH

**Description:**
`pending_plans` is a module-level dictionary that maps `user_id → plan`. Plans are added when the AI generates a trade plan and removed when the user confirms or cancels. But if the user simply ignores the confirmation (doesn't click confirm or cancel), the plan stays in memory forever. Over time with many users, this is a **memory leak**.

Additionally, if the bot restarts, all pending plans are lost but the confirmation buttons in Telegram chat remain — clicking "Confirm Execute" after restart will show "Trade Expired" which is correct, but clicking "show_trade_plan" for the trade button summary will also show "Trade Expired".

**Suggested Fix:**
Add a TTL mechanism. For example, store `(plan, timestamp)` tuples and clean up plans older than 5 minutes in a periodic task. Or use the ConversationHandler state to manage plan lifecycle.

---

## BUG #6 — HIGH: `callback_data` Pattern Collision Between `close_confirm_*` and `close_*`

**File:** `main.py`, lines 2430 and 2551
**Severity:** HIGH

**Description:**
The handlers check `if query.data.startswith("close_confirm_")` (line 2430) and later `if query.data.startswith("close_")` (line 2551). Since `close_confirm_all` starts with `close_`, the order matters. Because `close_confirm_` is checked first, it catches `close_confirm_*` correctly. BUT `close_cancel` (line 2511) is checked before `close_*` and `close_all_yes` (line 2518) is checked before `close_*`, so those are fine too.

However, `cancelorders_confirm_all` (line 2772) and `cancelorders_*` (line 2665) also have a potential collision, but since `cancelorders_confirm_all` has its own exact-match handler before `cancelorders_*` it's fine.

The actual collision bug is: `cancelone_confirm_*` (line 2741) vs `cancelone_*` (line 2811). Since `cancelone_confirm_` is checked BEFORE `cancelone_`, this works. But note that `cancelone_` ALSO matches `cancelone_confirm_` if the ordering were reversed. The current ordering is correct but **fragile**.

**Actual Severity Revised:** MEDIUM (currently working but fragile)

**Suggested Fix:**
Use exact matching with regex patterns or use a more structured callback_data format (e.g., `action:param` style). At minimum, add code comments warning about the ordering dependency.

---

## BUG #7 — MEDIUM: `cmd_status` Displays Positions With `size=0`

**File:** `main.py`, lines ~2850–2900
**Severity:** MEDIUM

**Description:**
In `cmd_status()`, the positions are displayed without filtering for `size != 0`:
```python
positions = summary.get("positions", [])
if positions:
    msg += f"\n📈 *Open Positions ({len(positions)}):*\n"
    for p in positions:
```
This displays ALL positions including closed ones (size=0). Other handlers like `trade_hub`, `quick_close`, etc. correctly filter with `float(p.get("size", "0")) != 0`.

**Suggested Fix:**
Add the same filter: `open_positions = [p for p in positions if isinstance(p, dict) and float(p.get("size", "0")) != 0]`

---

## BUG #8 — MEDIUM: `cmd_pnl` Displays Positions With `size=0`

**File:** `main.py`, lines ~3175–3200
**Severity:** MEDIUM

**Description:**
Same issue as BUG #7 — `cmd_pnl()` iterates all positions without filtering for non-zero size. The PnL card will show closed (size=0) positions.

**Suggested Fix:**
Filter positions: `open_pos = [p for p in positions if isinstance(p, dict) and float(p.get("size", "0")) != 0]`

---

## BUG #9 — MEDIUM: Markdown Parse Errors in Dynamic Content

**File:** `main.py`, various locations
**Severity:** MEDIUM

**Description:**
Several places insert dynamic content (user names, error messages, asset symbols, etc.) into Telegram Markdown messages without escaping special characters (`_`, `*`, `[`, `` ` ``, etc.). This will cause `BadRequest: Can't parse entities` errors.

Examples:
1. **Line ~155 `_friendly_order_error`**: `raw_error[:150]` is inserted into a Markdown message — if the error contains `_` or `*`, parsing fails.
2. **Line ~1370 share_pnl**: `display_name = tg_user.full_name` — user names often contain underscores or special chars.
3. **Line ~1490 share_closed**: Same display_name issue.
4. **Line ~2008 translation card**: `f"*{source_prefix}: {translation}*"` — translated text may contain Markdown special chars.
5. **News alert titles** (news_push.py line 340): `title.replace("**", "").replace("__", "").replace("*", "")` — partially escaped but misses `_`, `[`, `` ` `` and other Markdown chars.

**Suggested Fix:**
Create a `_escape_md(text)` helper that escapes all Markdown special characters for MarkdownV1 (`_*[\``), or switch to `parse_mode="MarkdownV2"` with proper escaping, or use `parse_mode="HTML"` which is easier to escape.

---

## BUG #10 — MEDIUM: No Message Length Check for Trade Hub / PnL / Orders

**File:** `main.py`, various handlers
**Severity:** MEDIUM

**Description:**
Telegram messages have a 4096 character limit. While `handle_message()` (line 680) correctly truncates AI responses (`if len(reply_text) > 4000: reply_text = reply_text[:4000] + "..."`), many other handlers that build dynamic messages don't check:

1. **`trade_hub`** (line ~993): Builds position list with no length check. A user with 10+ positions could exceed 4096 chars.
2. **`quick_pnl`** (line ~1100): Builds open + closed trade lists — easily exceeds 4096 with many trades.
3. **`quick_orders`** (line ~1515): Order list could exceed limit.
4. **`cmd_status`** (line ~2843): Position list without length check.
5. **`cmd_pnl`** (line ~3150): Full PnL card with positions.
6. **`cmd_history`** (line ~3085): Trade history.

**Suggested Fix:**
Add a `_truncate_msg(msg, limit=4000)` helper and apply it before every `safe_edit` or `reply_text` call, or paginate results when they exceed a threshold.

---

## BUG #11 — MEDIUM: `close_*` Pattern Catches `close_cancel` and `close_all_yes`

**File:** `main.py`, line 2551
**Severity:** MEDIUM (currently working due to ordering)

**Description:**
The handler at line 2551 `if query.data.startswith("close_")` would match `close_cancel` and `close_all_yes`, but these are caught by earlier explicit checks. However, the handler also matches `close_confirm_*` — which IS caught earlier at line 2430. The issue is that if any code reorganization moves handlers around, this breaks silently.

Additionally, the `close_` handler (line 2551) will match any `close_ANYTHING` — there's no validation that the contract_id extracted is actually a valid contract ID. If a user crafts a malicious callback_data like `close_malicious_payload`, the code will try to fetch positions and create a client, potentially causing confusing errors.

**Suggested Fix:**
Add an explicit check that the extracted contract_id looks like a valid edgeX contract ID (numeric), or use a prefix like `close_cid_` to avoid collisions.

---

## BUG #12 — MEDIUM: Race Condition in `pending_plans` for Concurrent Users

**File:** `main.py`, line 32
**Severity:** MEDIUM

**Description:**
`pending_plans[user_id] = plan` is set in `handle_message()` and consumed in `confirm_trade`. If the same user sends two trade requests in quick succession, the second plan overwrites the first. When they click "Confirm Execute" on the first plan, they'll actually execute the second plan. This is a silent data integrity issue.

**Suggested Fix:**
Use a unique plan ID in the callback_data (e.g., `confirm_trade_{plan_id}`) and store plans as `{plan_id: plan}` instead of `{user_id: plan}`.

---

## BUG #13 — MEDIUM: `_edit_exec` Helper Uses Positional *kw Args Incorrectly

**File:** `main.py`, line ~2330
**Severity:** MEDIUM

**Description:**
The `_edit_exec` function is defined as:
```python
async def _edit_exec(text, *kw):
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=_exec_msg_id, text=text, *kw)
    except Exception:
        await safe_send(context, chat_id, text, *kw)
```
The function takes `*kw` (positional args), but callers pass **keyword** arguments:
```python
await _edit_exec(msg, parse_mode="Markdown", reply_markup=_main_menu_kb)
```
Since `parse_mode` and `reply_markup` are passed as keyword args, they're NOT captured by `*kw` — they go into... actually Python handles this correctly because keyword args after `*kw` are passed through. Wait, let me reconsider.

Actually, `*kw` captures extra positional args. `parse_mode="Markdown"` is a keyword arg that gets passed to the outer function scope — but `_edit_exec` doesn't accept `**kwargs`. So this would raise `TypeError: _edit_exec() got an unexpected keyword argument 'parse_mode'`.

**THIS IS A BUG.** The function should be:
```python
async def _edit_exec(text, **kw):
```

But wait — the code is currently running in production. Let me re-read... The function signature is `async def _edit_exec(text, *kw):` and callers do `await _edit_exec(msg, parse_mode="Markdown", reply_markup=_main_menu_kb)`. Python will raise `TypeError` here. Unless... this code path has never been tested.

**REVISED: CRITICAL** — Every successful trade execution that calls `_edit_exec` with keyword args will crash with TypeError, and the fallback `safe_send` also receives `*kw` (empty tuple) so it at least sends a raw message without formatting.

Actually wait — re-reading more carefully: the `except Exception` catches the TypeError, so the fallback `safe_send` is called with `(context, chat_id, text, *kw)` where `*kw` is empty since keyword args weren't captured. The keyword args are lost. So the success message after a trade is sent as **plain text without Markdown formatting and without the Main Menu keyboard**. The trade executes but the confirmation message is ugly/broken.

**Suggested Fix:**
Change `*kw` to `**kw`:
```python
async def _edit_exec(text, **kw):
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=_exec_msg_id, text=text, **kw)
    except Exception:
        await safe_send(context, chat_id, text, **kw)
```

---

## BUG #14 — MEDIUM: `error_handler` Exposes Internal Error Details to Users

**File:** `main.py`, line ~173
**Severity:** MEDIUM (Security)

**Description:**
The global error handler sends `str(context.error)[:200]` to the user. This could expose internal details like file paths, database errors, API keys in URLs, or stack traces.

**Suggested Fix:**
Remove the error detail from the user-facing message. Log it server-side only:
```python
await context.bot.send_message(
    chat_id=update.effective_chat.id,
    text="❌ Something went wrong. Please try again.",
)
```

---

## BUG #15 — MEDIUM: `_friendly_order_error` Exposes Raw Error to User

**File:** `main.py`, line ~153
**Severity:** MEDIUM (Security)

**Description:**
The fallback case in `_friendly_order_error()` includes `_Technical detail: {raw_error[:150]}_` which can expose internal edgeX API errors to the user. These may contain account IDs, contract details, or other sensitive info.

**Suggested Fix:**
Remove or redact the technical detail in the generic fallback.

---

## BUG #16 — LOW: `cmd_orders` Uses `cancelorders_all` but Confirmation Uses `cancelorders_confirm_all`

**File:** `main.py`, line ~2885
**Severity:** LOW

**Description:**
In `cmd_orders()`, the "Cancel All Orders" button uses `callback_data="cancelorders_all"` (line ~2885), which skips the confirmation dialog and goes directly to order cancellation. Meanwhile, the inline orders view (`quick_orders`) uses `cancelorders_confirm_all` which shows a confirmation first.

This is an inconsistency — the `/orders` command lets users cancel all orders in one click with no confirmation, while the inline UI shows a confirmation.

**Suggested Fix:**
Change `cmd_orders` to use `cancelorders_confirm_all` for consistency.

---

## BUG #17 — LOW: `cmd_close` Uses Direct `close_{cid}` Without Confirmation

**File:** `main.py`, line ~3038
**Severity:** LOW

**Description:**
Similarly, `cmd_close()` generates buttons with `callback_data=f"close_{cid}"` which directly closes the position (no confirmation). The inline UI (`quick_close`) uses `close_confirm_{cid}` which shows a confirmation.

**Suggested Fix:**
Change to `close_confirm_{cid}` for consistency and safety.

---

## BUG #18 — LOW: Translation Handler Spawns External Process Without Sanitization

**File:** `main.py`, lines ~1978–2010
**Severity:** LOW (Security)

**Description:**
The translation handler extracts the headline from the message text and passes it to an external `droid exec` command. While `create_subprocess_exec` (not `shell`) is used (which prevents shell injection), the headline content is passed as a command-line argument. Extremely long headlines or headlines with null bytes could cause issues.

**Suggested Fix:**
Truncate the headline to a reasonable length (e.g., 500 chars) before passing to the subprocess.

---

## BUG #19 — LOW: `handle_message` Creates Minimal User Record But Doesn't Set AI

**File:** `main.py`, line ~619
**Severity:** LOW

**Description:**
When a user who has never used the bot sends a message, `handle_message` creates a minimal user record with `db.save_user(update.effective_user.id, "", "")`. This is fine. But it then checks for AI config and prompts activation. However, if the user later connects edgeX via the button flow (not /start), the user record already exists with empty credentials, so `db.save_user` must handle the update case. This works if `save_user` does an upsert, but if it does an INSERT, it would fail.

**Impact:** Depends on `db.save_user` implementation. If it's INSERT OR REPLACE, it's fine.

---

## BUG #20 — LOW: `logout_yes` Doesn't Clean Up `ai_config` Table

**File:** `main.py`, lines 264-272 and 1581-1590
**Severity:** LOW

**Description:**
The logout handler deletes from `users` and `ai_usage` tables but does NOT delete the AI configuration. After logout and re-login, the old AI config persists, which may be intentional (preserve settings) but could also be confusing if the user expected a full reset.

**Suggested Fix:**
Document this as intentional behavior, or add an option to also clear AI config on logout.

---

## BUG #21 — LOW: `safe_edit` Swallows All Exceptions Silently

**File:** `main.py`, line ~166
**Severity:** LOW

**Description:**
`safe_edit` catches all exceptions and logs a warning. This means if the edit fails (e.g., message was deleted, or content hasn't changed), the user sees stale content with no feedback. This is by design for robustness but could hide real issues during development.

---

## BUG #22 — LOW: No Rate Limiting on Message Handler

**File:** `main.py`, `handle_message()`
**Severity:** LOW

**Description:**
Any user can spam messages and trigger AI calls (which cost money via API). The AI rate limiting is done inside `ai_trader.generate_trade_plan` (returns RATE_LIMITED), but only for the free tier. Users with their own API key have no rate limit, and even the free tier check happens AFTER the message is processed, meaning each spam message still hits the database and config lookups.

**Suggested Fix:**
Add a simple in-memory rate limiter (e.g., max 10 messages per minute per user) at the top of `handle_message`.

---

## BUG #23 — MEDIUM: `tl_*` Translation Doesn't Dismiss Loading Spinner Before Long Operation

**File:** `main.py`, line ~1962
**Severity:** MEDIUM

**Description:**
The translation handler (line 1962) does NOT call `query.answer()` before starting the AI translation which can take up to 30 seconds. The Telegram loading spinner will show for the full translation duration, and after 30 seconds Telegram auto-fails the callback with a "query is too old" error, even though the translation may complete and the message may be sent.

**Suggested Fix:**
Add `await query.answer()` immediately at the start of the `tl_*` handler.

---

## BUG #24 — MEDIUM: News Alert `format_news_alert` Doesn't Add Mute/Dismiss Buttons

**File:** `news_push.py`, line 318
**Severity:** MEDIUM

**Description:**
The `format_news_alert()` function generates trade buttons and translation buttons but does NOT include "Mute Source" or "Dismiss" buttons. However, `handle_trade_callback` has handlers for `news_mute_*` (line 1944) and `news_dismiss` (line 1954). These buttons are never generated anywhere, making those handlers dead code.

**Suggested Fix:**
Add mute/dismiss buttons to the news alert keyboard in `format_news_alert()`:
```python
buttons.append([
    InlineKeyboardButton("🔇 Mute", callback_data=f"news_mute_{source_id}"),
    InlineKeyboardButton("✔️ Dismiss", callback_data="news_dismiss"),
])
```

---

## BUG #25 — MEDIUM: `callback_data` Length Limit (64 bytes) Not Checked for Trade Buttons

**File:** `news_push.py`, line ~385 and `main.py` various places
**Severity:** MEDIUM

**Description:**
Telegram callback_data has a maximum of 64 bytes. The news trade button format is:
```
nt_{asset}_{side}_{leverage}_{amount}
```
For example: `nt_TSLA_BUY_3_200` = 18 bytes, which is fine. But `share_closed_{order_id}` checks the 64-byte limit (line ~1226 in main.py), while many other callback_data patterns don't:

- `close_confirm_{contract_id}` — contract IDs can be long
- `cancelone_confirm_{order_id}` — order IDs can be long
- `cancelone_{order_id}` — same
- `vieworders_{contract_id}` — contract IDs
- `cancelorders_{contract_id}` — contract IDs

If IDs are very long (e.g., UUID format = 36 chars), the callback_data could exceed 64 bytes, causing the button to fail silently.

**Suggested Fix:**
Add length validation before creating buttons, or use shorter callback_data formats.

---

## Summary

| # | Severity | Description |
|---|----------|-------------|
| 1 | CRITICAL | News trade handler code is unreachable (indentation bug) |
| 13 | CRITICAL | `_edit_exec` uses `*kw` instead of `**kw` — trade success messages lose formatting |
| 2 | HIGH (revised MEDIUM) | Missing `query.answer()` in some handlers (most covered by entry call) |
| 3 | HIGH | Duplicate callback handlers between login choice and trade callback |
| 4 | HIGH | `back_to_dashboard` in login_choice returns None (doesn't end conversation) |
| 5 | HIGH | `pending_plans` memory leak — no TTL/cleanup |
| 6 | MEDIUM | Fragile callback_data pattern ordering |
| 7 | MEDIUM | `cmd_status` shows closed positions |
| 8 | MEDIUM | `cmd_pnl` shows closed positions |
| 9 | MEDIUM | Markdown special chars not escaped in dynamic content |
| 10 | MEDIUM | No message length check (4096 char limit) |
| 11 | MEDIUM | `close_*` pattern fragility |
| 12 | MEDIUM | Race condition in `pending_plans` |
| 13 | See above | (merged with CRITICAL) |
| 14 | MEDIUM | Error handler exposes internal details |
| 15 | MEDIUM | `_friendly_order_error` exposes raw error |
| 16 | LOW | `/orders` cancel-all skips confirmation |
| 17 | LOW | `/close` skips confirmation |
| 18 | LOW | Translation subprocess headline not sanitized |
| 19 | LOW | Minimal user record creation edge case |
| 20 | LOW | Logout doesn't clean AI config |
| 21 | LOW | `safe_edit` swallows all exceptions |
| 22 | LOW | No rate limiting on message handler |
| 23 | MEDIUM | Translation doesn't answer callback before long operation |
| 24 | MEDIUM | Mute/dismiss buttons never generated for news alerts |
| 25 | MEDIUM | callback_data 64-byte limit not checked everywhere |

**CRITICAL bugs that need immediate fixing:** #1 (unreachable news trade code) and #13 (`_edit_exec` *kw vs **kw)
