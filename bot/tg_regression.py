"""Automated Telegram bot regression test via Telethon.
Sends messages to @edgeXAgentBot and validates responses.
"""
import asyncio
import os
import sys
import time
from telethon import TelegramClient

API_ID = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION_FILE = "tg_test_session"
BOT_USERNAME = "edgeXAgentBot"

PASS = 0
FAIL = 0


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")
        if detail:
            print(f"        -> {detail[:300]}")


async def get_last_bot_msg_id(client, bot):
    """Get the ID of the last message from the bot."""
    messages = await client.get_messages(bot, limit=1, from_user=bot)
    return messages[0].id if messages else 0


async def send_and_wait(client, bot, text, wait_secs=30):
    """Send message to bot and wait for NEW response (after our send)."""
    # Record last bot message ID before sending
    before_id = await get_last_bot_msg_id(client, bot)

    await client.send_message(bot, text)

    # Wait for a new bot message with ID > before_id
    for i in range(wait_secs * 2):
        await asyncio.sleep(0.5)
        messages = await client.get_messages(bot, limit=5, from_user=bot)
        for msg in messages:
            if msg.id > before_id:
                buttons = []
                if msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            buttons.append(btn.text)
                return msg.text or "", buttons
    return None, []


async def main():
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"Testing as: {me.first_name} (ID: {me.id})")

    bot = await client.get_entity(BOT_USERNAME)
    print(f"Bot: @{BOT_USERNAME} (ID: {bot.id})\n")

    print("=" * 50)
    print("  edgeX Agent Bot — Regression Tests")
    print("=" * 50)

    # ── Test 1: /start — should show Dashboard (user in DB) ──
    print("\n--- Test 1: /start (logged-in user) ---")
    text, buttons = await send_and_wait(client, bot, "/start", wait_secs=10)
    if text:
        has_dashboard = "Account" in text or "Connected" in text
        test("/start shows Dashboard", has_dashboard, text[:200])
        has_action_buttons = len(buttons) >= 3
        test("/start has quick action buttons", has_action_buttons, f"buttons={buttons}")
    else:
        test("/start responds", False, "No response")
        test("/start has buttons", False)

    await asyncio.sleep(3)

    # ── Test 2: /status ──
    print("\n--- Test 2: /status ---")
    text, buttons = await send_and_wait(client, bot, "/status", wait_secs=15)
    if text:
        test("/status responds", True)
        has_balance = "Equity" in text or "equity" in text or "Available" in text or "$" in text
        test("/status shows balance info", has_balance, text[:200])
    else:
        test("/status responds", False, "No response")
        test("/status shows balance", False)

    await asyncio.sleep(3)

    # ── Test 3: /help ──
    print("\n--- Test 3: /help ---")
    text, buttons = await send_and_wait(client, bot, "/help", wait_secs=10)
    if text:
        test("/help responds", True)
        test("/help lists commands", "/status" in text or "/start" in text, text[:200])
    else:
        test("/help responds", False, "No response")
        test("/help lists commands", False)

    await asyncio.sleep(3)

    # ── Test 4: /pnl ──
    print("\n--- Test 4: /pnl ---")
    text, buttons = await send_and_wait(client, bot, "/pnl", wait_secs=15)
    if text:
        test("/pnl responds", True)
        has_report = "P&L" in text or "Equity" in text or "Report" in text or "Trades" in text or "equity" in text
        test("/pnl shows report", has_report, text[:200])
    else:
        test("/pnl responds", False, "No response")
        test("/pnl shows report", False)

    await asyncio.sleep(3)

    # ── Test 5: /history ──
    print("\n--- Test 5: /history ---")
    text, buttons = await send_and_wait(client, bot, "/history", wait_secs=15)
    if text:
        test("/history responds", True)
        ok = "trade" in text.lower() or "order" in text.lower() or "history" in text.lower() or "no" in text.lower()
        test("/history shows content", ok, text[:200])
    else:
        test("/history responds", False, "No response")
        test("/history shows content", False)

    await asyncio.sleep(3)

    # ── Test 6: AI chat — price query (long wait for AI) ──
    print("\n--- Test 6: AI — BTC price query ---")
    text, buttons = await send_and_wait(client, bot, "BTC现在多少钱", wait_secs=60)
    if text:
        test("AI responds to price query", True)
        is_natural = not text.startswith("{") and not text.startswith('{"type"')
        test("Response is natural language", is_natural, text[:200])
        mentions_btc = "BTC" in text.upper() or "比特币" in text or "$" in text
        test("Mentions BTC or price", mentions_btc, text[:200])
    else:
        test("AI responds to price query", False, "No response within 60s")
        test("Natural language", False)
        test("Mentions BTC", False)

    await asyncio.sleep(5)

    # ── Test 7: AI — CRCL recognition ──
    print("\n--- Test 7: AI — CRCL recognition ---")
    text, buttons = await send_and_wait(client, bot, "crcl现在什么价格", wait_secs=60)
    if text:
        test("AI responds to CRCL query", True)
        is_natural = not text.startswith("{")
        test("CRCL response is natural language", is_natural, text[:200])
        wrong_crv = "CRV" in text.upper() and "CRCL" not in text.upper()
        test("Does NOT confuse CRCL with CRV", not wrong_crv, text[:200])
    else:
        test("AI responds to CRCL query", False, "No response within 60s")
        test("Natural language", False)
        test("Not CRV", False)

    await asyncio.sleep(5)

    # ── Test 8: AI strategy question (should give real analysis, not fallback) ──
    print("\n--- Test 8: AI — strategy question ---")
    text, buttons = await send_and_wait(client, bot, "crcl最近涨的厉害，有啥我能赚钱的操作", wait_secs=60)
    if text:
        test("AI responds to strategy question", True)
        is_real_analysis = len(text) > 50 and "clearer direction" not in text and "Try:" not in text
        test("Response is real analysis (not hardcoded fallback)", is_real_analysis, text[:300])
        no_confirm_btn = not any("Confirm" in b for b in buttons)
        test("No Confirm button (it's analysis, not trade)", no_confirm_btn, f"buttons={buttons}")
    else:
        test("AI responds to strategy", False, "No response within 60s")
        test("Real analysis", False)
        test("No Confirm button", False)

    await asyncio.sleep(5)

    # ── Test 9: AI trade — confirmation flow ──
    print("\n--- Test 9: AI — trade with confirmation ---")
    text, buttons = await send_and_wait(client, bot, "帮我做多BTC 小仓位试试", wait_secs=60)
    if text:
        test("AI responds to trade request", True)
        is_natural = not text.startswith('{"type"')
        test("Trade response not raw JSON wrapper", is_natural, text[:200])
        # Should show trade plan with confirm/cancel buttons OR a chat response
        has_confirm = any("Confirm" in b or "Execute" in b for b in buttons)
        has_trade_plan = "BTC" in text and ("Entry" in text or "entry" in text or "BUY" in text)
        is_chat = len(text) > 20  # Could be a chat analysis response
        test("Shows trade plan or analysis", has_confirm or has_trade_plan or is_chat,
             f"buttons={buttons}, text={text[:150]}")
    else:
        test("AI responds to trade", False, "No response within 60s")
        test("Format", False)
        test("Content", False)

    # ── Summary ──
    print("\n" + "=" * 50)
    print(f"Results: {PASS}/{PASS + FAIL} passed, {FAIL} failed")
    if FAIL == 0:
        print("ALL REGRESSION TESTS PASSED")
    else:
        print(f"WARNING: {FAIL} tests failed!")
    print("=" * 50)

    await client.disconnect()
    sys.exit(1 if FAIL > 0 else 0)

asyncio.run(main())
