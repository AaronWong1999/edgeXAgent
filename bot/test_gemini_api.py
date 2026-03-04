"""Test /setai flow with Google Gemini API."""
import asyncio
import os
import sys
from telethon import TelegramClient

API_ID = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
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


async def send_wait(client, bot, text, wait=45):
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

    # === Step 1: /setai ===
    print("\n--- 1. /setai ---")
    text, btns, msg = await send_wait(client, bot, "/setai", wait=10)
    check("/setai responds", text is not None)
    await asyncio.sleep(2)

    # === Step 2: Click Google Gemini ===
    print("\n--- 2. Select Gemini ---")
    if not msg:
        print("         [WARN] /setai returned no message, trying again")
        text, btns, msg = await send_wait(client, bot, "/setai", wait=15)
        check("/setai retry", msg is not None)
    text2, btns2, msg2 = await click_btn(client, bot, msg, "Gemini", wait=15)
    if not text2 and msg:
        await asyncio.sleep(3)
        updated = await client.get_messages(bot, ids=msg.id)
        if updated and updated.text and "Gemini" in updated.text:
            text2 = updated.text
            msg2 = updated
    check("Gemini selected", text2 is not None and ("key" in (text2 or "").lower() or "Gemini" in (text2 or "")), (text2 or "")[:200])
    await asyncio.sleep(2)

    # === Step 3: Send API key ===
    print("\n--- 3. Submit Gemini key ---")
    text3, btns3, msg3 = await send_wait(client, bot, GEMINI_KEY, wait=50)
    # May get "Testing..." first, wait for real result
    if text3 and "Testing" in text3:
        print("         (got 'Testing...', waiting for result)")
        for _ in range(30):
            await asyncio.sleep(1)
            msgs = await client.get_messages(bot, limit=5, from_user=bot)
            for m in msgs:
                if m.id > (msg3.id if msg3 else 0):
                    text3 = m.text or ""
                    btns3 = [bb.text for r in (m.buttons or []) for bb in r]
                    msg3 = m
                    break
            if text3 and "Testing" not in text3:
                break
    check("API key accepted + activated", text3 and ("Activated" in text3 or "Professional" in str(btns3) or "locked" in text3.lower()), (text3 or "")[:200])
    check("Shows personality buttons", any("Professional" in b for b in btns3), str(btns3))
    await asyncio.sleep(2)

    # === Step 4: Pick personality ===
    if msg3 and msg3.buttons:
        print("\n--- 4. Pick personality ---")
        text4, _, _ = await click_btn(client, bot, msg3, "Geek", wait=10)
        check("Personality set", text4 and "Geek" in text4, (text4 or "")[:200])
        await asyncio.sleep(3)

    # === Step 5: Test AI with Gemini ===
    print("\n--- 5. Chat with Gemini model ---")
    text5, btns5, _ = await send_wait(client, bot, "What's BTC price right now?", wait=90)
    if text5:
        check("Gemini responds", True)
        check("Response has BTC or $", "BTC" in text5 or "$" in text5, text5[:200])
        print(f"         Response: {text5[:150]}")
    else:
        check("Gemini responds", False, "Timeout")
    await asyncio.sleep(5)

    # === Step 6: Trade plan test ===
    print("\n--- 6. Trade plan with Gemini ---")
    text6, btns6, _ = await send_wait(client, bot, "Long SOL, small position", wait=90)
    if text6:
        check("Trade plan generated", "SOL" in text6 or "Long" in text6.upper() or "BUY" in text6, text6[:200])
        has_confirm = any("Confirm" in b for b in btns6)
        has_connect = any("Connect" in b for b in btns6)
        check("Has action button (Confirm or Connect)", has_confirm or has_connect, str(btns6))
        print(f"         Response: {text6[:150]}")
    else:
        check("Trade plan", False, "Timeout")

    # === Summary ===
    print(f"\n{'=' * 50}")
    print(f"  RESULTS: {PASS}/{TOTAL} passed")
    print(f"{'=' * 50}")

    await client.disconnect()
    sys.exit(0 if PASS == TOTAL else 1)

asyncio.run(main())
