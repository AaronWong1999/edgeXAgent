# edgeX Agent — Lessons Learned & Conventions

## Critical Rules

### 1. Prototype Must 100% Match Code
**Mistake:** When building HTML prototypes, AI compressed/abbreviated text to save tokens. Example: "Choose how to connect:" was shortened, button labels like "💳 Use edgeX Account Balance" were changed to "💳 edgeX Balance (soon)", the 5 language examples in Dashboard were cut to 3.

**Rule:** ALWAYS read the actual code line-by-line before writing prototype text. Every screen in the prototype must have:
- Exact title text from code (e.g. `🔗 **Connect edgeX — edgeX Agent**`)
- Exact button labels (e.g. `🔑 Connect with API Key`, not `🔑 API Key`)
- Exact body text including ├/└ tree formatting
- All buttons, not a subset
- All callback_data values documented in footer

### 2. Arrows in Flow Maps Must Represent Real Navigation
**Mistake:** Used `→` arrows between screens that are mutually exclusive states (e.g. AI Hub → Activate AI), implying you navigate from one to the other. Actually they are the same button position in different states.

**Rule:**
- `or` = mutually exclusive states (same button, different conditions)
- Tree lines `├──` = parent→child click navigation (click button X → go to screen Y)
- Sequential `→` = only for edit-in-place chains (Plan → Executing → Result)
- Never draw arrows between screens that can't actually be navigated between

### 3. Don't Invent callback_data Values
**Mistake:** Some prototype screens had buttons with made-up callback_data that didn't exist in code, leading to silent failures when clicked.

**Rule:** Every button in the prototype must correspond to a real `InlineKeyboardButton(..., callback_data="...")` in `main.py`.

### 4. Shared Screens Must Be Identified
**Mistake:** Didn't initially notice that `ai_activate_prompt` is the same screen reached from both Dashboard (Activate AI) and AI Hub (AI Provider), leading to duplicated/inconsistent code.

**Rule:** When multiple buttons use the same callback_data, mark the target screen as SHARED and ensure the handler works correctly from all entry points.

## Bug Patterns Found

### Pattern: ConversationHandler-Only Callbacks
Buttons that create callback_data values only handled inside a ConversationHandler (e.g. `setai_openai` only in `/setai` ConversationHandler) will silently fail when clicked from outside that conversation. Always add a fallback handler in `handle_trade_callback`.

### Pattern: Redirect Mismatch
Comment says "redirect to trade_hub" but code actually sends to Dashboard. Always verify the actual code behavior, not just the comment.

### Pattern: Dead-End Screens
Screens that tell the user "Use /setai command" with only a Back button are bad UX. Either show the actual UI inline or start the command programmatically.

## Architecture Reference

- 3 modules: 📈 Trade on edgeX / 🤖 AI Agent / 📰 Event Trading
- L1 Dashboard: always 3 buttons, edits in place
- L2 Hubs: Trade Hub, AI Hub, News Hub — Back → Dashboard
- L3 Sub-screens: Back → parent L2 Hub
- Push Layer: news alerts, AI chat, trade execution — separate messages
- 28 screens total, 53+ callback_data patterns, 8 shared screens
