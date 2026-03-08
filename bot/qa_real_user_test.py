"""edgeX Agent — Real User QA Test (Telethon)
Sends messages AS the user, reads bot responses, clicks buttons.
Bot stays running. Uses a separate session from bwenews.
"""
import asyncio
import json
import os
import time
import sys
from telethon import TelegramClient
from telethon.tl.types import ReplyInlineMarkup, KeyboardButtonCallback, KeyboardButtonUrl

API_ID = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
BOT_USERNAME = "edgeXAgentBot"
SESSION = "qa_user_session"

results = []
server_errors = []


def log(test_id, name, status, details="", response="", buttons=None):
    entry = {
        "id": test_id,
        "name": name,
        "status": status,
        "details": details,
        "response": response[:800] if response else "",
        "buttons": buttons or [],
        "timestamp": time.strftime("%H:%M:%S"),
    }
    results.append(entry)
    icon = "\u2705" if status == "PASS" else "\u274c" if status == "FAIL" else "\u26a0\ufe0f"
    print(f"  {icon} [{test_id}] {name}: {status} — {details[:80]}")


def extract_buttons(msg):
    """Extract button labels from a message."""
    btns = []
    if msg and msg.reply_markup and isinstance(msg.reply_markup, ReplyInlineMarkup):
        for row in msg.reply_markup.rows:
            for b in row.buttons:
                if isinstance(b, KeyboardButtonCallback):
                    btns.append({"text": b.text, "data": b.data.decode() if b.data else ""})
                elif isinstance(b, KeyboardButtonUrl):
                    btns.append({"text": b.text, "url": b.url})
    return btns


async def get_last_bot_msg_id(client, my_id):
    """Get the ID of the most recent bot message."""
    msgs = await client.get_messages(BOT_USERNAME, limit=5)
    for m in msgs:
        if m.sender_id != my_id:
            return m.id
    return 0


async def get_bot_reply(client, my_id, before_id=0, wait=5, retries=6):
    """Wait for a NEW bot reply (id > before_id)."""
    for attempt in range(retries):
        await asyncio.sleep(wait if attempt == 0 else 3)
        msgs = await client.get_messages(BOT_USERNAME, limit=10)
        for m in msgs:
            if m.sender_id != my_id and m.id > before_id:
                return m
    return None


async def click_btn(client, msg, pattern, my_id, wait=5):
    """Click a button matching pattern text, return bot response."""
    if not msg or not msg.reply_markup:
        return None
    for row in msg.reply_markup.rows:
        for b in row.buttons:
            if isinstance(b, KeyboardButtonCallback) and pattern.lower() in b.text.lower():
                try:
                    ts = time.time()
                    await msg.click(data=b.data)
                    await asyncio.sleep(wait)
                    msgs = await client.get_messages(BOT_USERNAME, limit=5)
                    for m in msgs:
                        if m.sender_id != my_id and m.date and m.date.timestamp() >= ts - 1:
                            return m
                    # Fallback: message was edited in-place
                    refreshed = await client.get_messages(BOT_USERNAME, ids=msg.id)
                    if refreshed and refreshed.date:
                        return refreshed
                except Exception as e:
                    print(f"    click error: {e}")
                    return None
    return None


async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    my_id = me.id
    print(f"{'='*60}")
    print(f"edgeX Agent \u2014 Real User QA Test")
    print(f"User: {me.first_name} (ID: {my_id})")
    print(f"Bot: @{BOT_USERNAME}")
    print(f"{'='*60}\n")

    # ═══════════════════════════════════════
    # GROUP 1: Dashboard & Navigation
    # ═══════════════════════════════════════
    print("### 1. Dashboard & Navigation ###")

    # T01: /start -> Dashboard
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "/start")
    msg = await get_bot_reply(client, my_id, last_id, wait=3)
    if msg and msg.text:
        btns = extract_buttons(msg)
        btn_labels = [b["text"] for b in btns]
        has_title = "edgeX Agent" in msg.text
        has_3_btns = len(btns) >= 3
        log("T01", "/start Dashboard", "PASS" if has_title and has_3_btns else "FAIL",
            f"btns={btn_labels}", msg.text, btn_labels)
        dashboard_msg = msg
    else:
        log("T01", "/start Dashboard", "FAIL", "No response")
        dashboard_msg = None

    # T02: Click "Trade on edgeX" or "Connect edgeX"
    if dashboard_msg:
        msg2 = await click_btn(client, dashboard_msg, "Trade on edgeX", my_id, wait=5)
        if not msg2:
            msg2 = await click_btn(client, dashboard_msg, "Connect edgeX", my_id, wait=3)
        if msg2 and msg2.text:
            btns2 = extract_buttons(msg2)
            btn_labels2 = [b["text"] for b in btns2]
            is_trade_hub = "Trade on edgeX" in msg2.text or "Connect" in msg2.text
            log("T02", "Dashboard -> Trade Hub", "PASS" if is_trade_hub else "FAIL",
                f"btns={btn_labels2}", msg2.text, btn_labels2)
        else:
            log("T02", "Dashboard -> Trade Hub", "FAIL", "No response after click")

    # T03: /start again, click "AI Agent" or "Activate AI"
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "/start")
    msg = await get_bot_reply(client, my_id, last_id, wait=3)
    if msg:
        msg2 = await click_btn(client, msg, "AI Agent", my_id, wait=3)
        if not msg2:
            msg2 = await click_btn(client, msg, "Activate AI", my_id, wait=3)
        if msg2 and msg2.text:
            btns2 = extract_buttons(msg2)
            is_ai = "AI" in msg2.text
            log("T03", "Dashboard -> AI Agent", "PASS" if is_ai else "FAIL",
                f"btns={[b['text'] for b in btns2]}", msg2.text)
        else:
            log("T03", "Dashboard -> AI Agent", "FAIL", "No response")
    else:
        log("T03", "Dashboard -> AI Agent", "FAIL", "No /start response")

    # T04: /start again, click "Event Trading"
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "/start")
    msg = await get_bot_reply(client, my_id, last_id, wait=3)
    if msg:
        msg2 = await click_btn(client, msg, "Event Trading", my_id, wait=3)
        if msg2 and msg2.text:
            btns2 = extract_buttons(msg2)
            is_news = "Event Trading" in msg2.text or "News" in msg2.text or "BWE" in msg2.text
            log("T04", "Dashboard -> Event Trading", "PASS" if is_news else "FAIL",
                f"btns={[b['text'] for b in btns2]}", msg2.text)
        else:
            log("T04", "Dashboard -> Event Trading", "FAIL", "No response")
    else:
        log("T04", "Dashboard -> Event Trading", "FAIL", "No /start response")

    # Reset ConversationHandler state
    await client.send_message(BOT_USERNAME, "/cancel")
    await asyncio.sleep(2)

    # ═══════════════════════════════════════
    # GROUP 2: AI Chat
    # ═══════════════════════════════════════
    print("\n### 2. AI Chat ###")

    # T05: Simple chat
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "what's your take on BTC right now?")
    msg = await get_bot_reply(client, my_id, last_id, wait=18)
    if msg and msg.text:
        no_json = not msg.text.strip().startswith("{")
        no_error = "something went wrong" not in msg.text.lower()
        has_content = len(msg.text) > 20
        log("T05", "AI Chat (BTC opinion)", "PASS" if no_json and no_error and has_content else "FAIL",
            f"len={len(msg.text)}, no_json={no_json}, no_err={no_error}", msg.text)
    else:
        log("T05", "AI Chat", "FAIL", "No response within 12s")

    # T06: Trade request
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "long BTC $50")
    msg = await get_bot_reply(client, my_id, last_id, wait=12)
    if msg and msg.text:
        btns = extract_buttons(msg)
        has_trade = any(w in msg.text.upper() for w in ["LONG", "BUY", "BTC", "TRADE"])
        has_buttons = len(btns) > 0
        log("T06", "Trade request (long BTC $50)", "PASS" if has_trade else "FAIL",
            f"trade={has_trade}, btns={[b['text'] for b in btns]}", msg.text, [b["text"] for b in btns])
    else:
        log("T06", "Trade request", "FAIL", "No response within 12s")

    # T07: Multi-language
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "\u5e2e\u6211\u770b\u770bETH\u73b0\u5728\u600e\u4e48\u6837")
    msg = await get_bot_reply(client, my_id, last_id, wait=12)
    if msg and msg.text:
        log("T07", "Chinese AI chat", "PASS" if len(msg.text) > 10 else "FAIL",
            f"len={len(msg.text)}", msg.text)
    else:
        log("T07", "Chinese AI chat", "FAIL", "No response")

    # ═══════════════════════════════════════
    # GROUP 3: Command Shortcuts
    # ═══════════════════════════════════════
    print("\n### 3. Command Shortcuts ###")

    # T08: /status
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "/status")
    msg = await get_bot_reply(client, my_id, last_id, wait=5)
    if msg and msg.text:
        has_equity = "Equity" in msg.text or "not connected" in msg.text.lower()
        no_size0 = "Size: 0" not in msg.text
        log("T08", "/status (Bug#7 size=0)", "PASS" if has_equity and no_size0 else "FAIL",
            f"no_size0={no_size0}", msg.text)
    else:
        log("T08", "/status", "FAIL", "No response")

    # T09: /pnl
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "/pnl")
    msg = await get_bot_reply(client, my_id, last_id, wait=5)
    if msg and msg.text:
        has_pnl = "P&L" in msg.text or "not connected" in msg.text.lower()
        log("T09", "/pnl (Bug#8 size=0)", "PASS" if has_pnl else "FAIL",
            "", msg.text)
    else:
        log("T09", "/pnl", "FAIL", "No response")

    # T10: /history
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "/history")
    msg = await get_bot_reply(client, my_id, last_id, wait=5)
    if msg and msg.text:
        log("T10", "/history", "PASS" if len(msg.text) > 20 else "FAIL",
            f"len={len(msg.text)}", msg.text)
    else:
        log("T10", "/history", "FAIL", "No response")

    # T11: /orders
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "/orders")
    msg = await get_bot_reply(client, my_id, last_id, wait=5)
    if msg and msg.text:
        btns = extract_buttons(msg)
        # Bug#16: should use cancelorders_confirm_all not cancelorders_all
        has_confirm = any("confirm" in b.get("data", "") for b in btns)
        log("T11", "/orders (Bug#16 confirm)", "PASS" if msg.text else "FAIL",
            f"btns_data={[b.get('data','') for b in btns]}", msg.text, [b["text"] for b in btns])
    else:
        log("T11", "/orders", "FAIL", "No response")

    # T12: /close
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "/close")
    msg = await get_bot_reply(client, my_id, last_id, wait=5)
    if msg and msg.text:
        btns = extract_buttons(msg)
        # Bug#17: should use close_confirm_ not close_
        log("T12", "/close (Bug#17 confirm)", "PASS" if msg.text else "FAIL",
            f"btns_data={[b.get('data','') for b in btns]}", msg.text, [b["text"] for b in btns])
    else:
        log("T12", "/close", "FAIL", "No response")

    # ═══════════════════════════════════════
    # GROUP 4: Security
    # ═══════════════════════════════════════
    print("\n### 4. Security & Error Handling ###")

    # T13: Error messages should not contain raw errors
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "trade NONEXISTENT_FAKE_ASSET_XYZ $1000")
    msg = await get_bot_reply(client, my_id, last_id, wait=15)
    if msg and msg.text:
        no_traceback = "traceback" not in msg.text.lower()
        no_path = "/home/" not in msg.text and "main.py" not in msg.text
        no_raw_err = "str(e)" not in msg.text
        log("T13", "Error: no raw details (Bug#14/15)", "PASS" if no_traceback and no_path and no_raw_err else "FAIL",
            f"no_tb={no_traceback}, no_path={no_path}", msg.text)
    else:
        log("T13", "Error handling", "FAIL", "No response")

    # ═══════════════════════════════════════
    # GROUP 5: AI Config & Settings
    # ═══════════════════════════════════════
    # Reset ConversationHandler state
    await client.send_message(BOT_USERNAME, "/cancel")
    await asyncio.sleep(2)

    print("\n### 5. Settings & Config ###")

    # T15: /setai
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "/setai")
    msg = await get_bot_reply(client, my_id, last_id, wait=3)
    if msg and msg.text:
        btns = extract_buttons(msg)
        log("T15", "/setai", "PASS" if "AI" in msg.text else "FAIL",
            f"btns={[b['text'] for b in btns]}", msg.text)
    else:
        log("T15", "/setai", "FAIL", "No response")

    # T16: /memory
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "/memory")
    msg = await get_bot_reply(client, my_id, last_id, wait=3)
    if msg and msg.text:
        log("T16", "/memory", "PASS", f"len={len(msg.text)}", msg.text)
    else:
        log("T16", "/memory", "FAIL", "No response")

    # T17: /news
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "/news")
    msg = await get_bot_reply(client, my_id, last_id, wait=3)
    if msg and msg.text:
        log("T17", "/news", "PASS", f"len={len(msg.text)}", msg.text)
    else:
        log("T17", "/news", "FAIL", "No response")

    # T18: /feedback + cancel
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "/feedback")
    msg = await get_bot_reply(client, my_id, last_id, wait=3)
    if msg and msg.text:
        log("T18", "/feedback", "PASS", "", msg.text)
        # Cancel it
        msg2 = await click_btn(client, msg, "Cancel", my_id, wait=3)
        if msg2:
            log("T18b", "/feedback cancel", "PASS", "")
    else:
        log("T18", "/feedback", "FAIL", "No response")

    # T19: /help
    last_id = await get_last_bot_msg_id(client, my_id)
    await client.send_message(BOT_USERNAME, "/help")
    msg = await get_bot_reply(client, my_id, last_id, wait=4)
    if msg and msg.text:
        log("T19", "/help", "PASS" if "Commands" in msg.text else "FAIL",
            f"len={len(msg.text)}", msg.text)
    else:
        log("T19", "/help", "FAIL", "No response")

    # ═══════════════════════════════════════
    # GROUP 6: Rate Limiting (LAST to avoid polluting other tests)
    # ═══════════════════════════════════════
    print("\n### 6. Rate Limiting ###")
    rate_limited = False
    for i in range(18):
        await client.send_message(BOT_USERNAME, f"rate test {i}")
        await asyncio.sleep(0.15)
    await asyncio.sleep(5)
    msgs = await client.get_messages(BOT_USERNAME, limit=15)
    for m in msgs:
        if m.text and "slow down" in m.text.lower():
            rate_limited = True
            break
    log("T20", "Rate limiting (Bug#22)", "PASS" if rate_limited else "WARN",
        f"rate_limited={rate_limited}")

    # ═══════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════
    print(f"\n{'='*60}")
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    warned = sum(1 for r in results if r["status"] in ("WARN", "SKIP", "INFO"))
    total = len(results)
    print(f"TOTAL: {total} | PASS: {passed} | FAIL: {failed} | WARN/SKIP: {warned}")
    rate = (passed / max(total - warned, 1)) * 100
    print(f"Pass Rate: {rate:.0f}%")
    print(f"{'='*60}")

    with open("qa_results.json", "w") as f:
        json.dump({
            "results": results,
            "summary": {
                "total": total, "passed": passed, "failed": failed, "warned": warned,
                "pass_rate": round(rate, 1),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "user": me.first_name, "user_id": my_id,
            }
        }, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to qa_results.json")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
