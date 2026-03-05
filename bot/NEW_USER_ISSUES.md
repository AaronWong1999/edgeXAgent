# New User Exploration — Issues Found & Fixed

Date: 2026-03-05

## Issues Found (2 real bugs, all fixed)

1. **[UX]** `/close` with no positions — message had no buttons → FIXED: added `_quick_actions_keyboard()`
2. **[feedback]** Feedback text intercepted by AI handler instead of feedback ConversationHandler → FIXED: replaced ConversationHandler with `context.user_data` flag

## Additional UX Improvements Made

3. All "not connected" messages (`/orders`, `/close`, `/history`, `/pnl`) now have a "Connect edgeX" button
4. "No trade history" message now has quick action buttons
