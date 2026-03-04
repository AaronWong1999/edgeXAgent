"""Test demo login + Aaron's API one-click flows."""
import asyncio
import os
import sys
from telethon import TelegramClient

API_ID = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION_FILE = "tg_test_session"
BOT = "edgeXAgentBot"
PASS = 0
TOTAL = 0


def check(name, ok, detail=""):
    global PASS, TOTAL
    TOTAL += 1
    if ok:
        PASS += 1
        print(f"  [OK]  {name}")
    else:
        print(f"  [BUG] {name}")
        if detail:
            print(f"         -> {detail[:300]}")


async def last_id(client, bot):
    msgs = await client.get_messages(bot, limit=1, from_user=bot)
    return msgs[0].id if msgs else 0


async def send_wait(client, bot, text, wait=20):
    before = await last_id(client, bot)
    await client.send_message(bot, text)
    for _ in range(wait * 2):
        await asyncio.sleep(0.5)
        msgs = await client.get_messages(bot, limit=5, from_user=bot)
        for m in msgs:
            if m.id > before:
                btns = [b.text for row in (m.buttons or []) for b in row]
                return m.text or "", btns, m
    return None, [], None


async def click_btn(client, bot, msg, btn_text, wait=20):
    if not msg or not msg.buttons:
        return None, [], None
    for row in msg.buttons:
        for b in row:
            if btn_text.lower() in b.text.lower():
                before = await last_id(client, bot)
                await b.click()
                for _ in range(wait * 2):
                    await asyncio.sleep(0.5)
                    msgs = await client.get_messages(bot, limit=5, from_user=bot)
                    for m in msgs:
                        if m.id > before:
                            btns = [bb.text for r in (m.buttons or []) for bb in r]
                            return m.text or "", btns, m
                    updated = await client.get_messages(bot, ids=msg.id)
                    if updated and updated.edit_date and updated.text != (msg.text or ""):
                        btns = [bb.text for r in (updated.buttons or []) for bb in r]
                        return updated.text or "", btns, updated
                return None, [], None
    return None, [], None


async def main():
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    bot = await client.get_entity(BOT)
    print(f"Testing as: {me.first_name}")

    # === 1. /start ===
    print("\n--- 1. /start ---")
    text, btns, msg = await send_wait(client, bot, "/start", wait=10)
    check("/start responds", text is not None)
    check("Has Connect button", any("Connect" in b for b in btns))

    # === 2. Click Connect ===
    print("\n--- 2. Click Connect edgeX ---")
    text2, btns2, msg2 = await click_btn(client, bot, msg, "Connect", wait=10)
    check("Login menu shown", text2 is not None and "Connect" in (text2 or ""))
    has_demo = any("Aaron" in b for b in btns2)
    check("Has Aaron's demo button", has_demo, str(btns2))

    # === 3. Click Aaron's demo ===
    if has_demo:
        print("\n--- 3. Click Aaron's demo account ---")
        text3, btns3, msg3 = await click_btn(client, bot, msg2, "Aaron", wait=30)
        if text3 and "Connecting" in text3:
            await asyncio.sleep(10)
            msgs = await client.get_messages(bot, limit=3, from_user=bot)
            for m in msgs:
                if m.id > (msg3.id if msg3 else 0):
                    text3 = m.text or ""
                    btns3 = [bb.text for r in (m.buttons or []) for bb in r]
                    msg3 = m
                    break
        check("Demo connected", text3 and ("Connected" in text3 or "\u2705" in text3), (text3 or "")[:200])
        check("Shows temp notice", text3 and ("\u4e34\u65f6" in text3 or "temp" in (text3 or "").lower()), (text3 or "")[:200])

    # === 4. Click Aaron's AI ===
    print("\n--- 4. Activate Aaron's AI ---")
    if msg3 and msg3.buttons:
        text4, btns4, msg4 = await click_btn(client, bot, msg3, "Aaron", wait=10)
    else:
        text4, btns4, msg4 = await send_wait(client, bot, "test", wait=10)
        if text4 and "Aaron" in str(btns4):
            text4, btns4, msg4 = await click_btn(client, bot, msg4 if msg4 else msg3, "Aaron", wait=10)
    check("AI activated", text4 and ("Activated" in text4 or "\u4e34\u65f6" in text4), (text4 or "")[:200])
    check("Personality buttons", any("Professional" in b for b in (btns4 or [])), str(btns4))

    # === 5. Pick personality ===
    if msg4 and msg4.buttons:
        print("\n--- 5. Pick personality ---")
        text5, _, _ = await click_btn(client, bot, msg4, "Degen", wait=10)
        check("Personality set", text5 and "Degen" in text5, (text5 or "")[:200])

    # === 6. Chat ===
    print("\n--- 6. Chat test ---")
    text6, _, _ = await send_wait(client, bot, "What's BTC at?", wait=60)
    check("AI responds", text6 is not None and len(text6 or "") > 20, (text6 or "")[:200])

    # === 7. /status ===
    print("\n--- 7. /status ---")
    text7, _, _ = await send_wait(client, bot, "/status", wait=15)
    check("/status works", text7 and "Equity" in text7, (text7 or "")[:200])

    # === Cleanup ===
    print("\n--- Cleanup ---")
    text, btns, msg = await send_wait(client, bot, "/logout", wait=10)
    await click_btn(client, bot, msg, "Yes", wait=10)

    print(f"\n{'=' * 50}")
    print(f"  RESULTS: {PASS}/{TOTAL} passed")
    print(f"{'=' * 50}")
    if PASS == TOTAL:
        print("\n  PERFECT SCORE!")

    await client.disconnect()
    sys.exit(0 if PASS == TOTAL else 1)

asyncio.run(main())
