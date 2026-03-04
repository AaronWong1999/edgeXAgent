"""Test the /setai flow with NVIDIA API (qwen/qwen3.5-397b-a17b)."""
import asyncio
import os
from telethon import TelegramClient

API_ID = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION_FILE = "tg_test_session"
BOT = "edgeXAgentBot"

# NVIDIA test creds (OpenAI-compatible)
NVIDIA_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = "qwen/qwen3.5-397b-a17b"


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
                btns = []
                if m.buttons:
                    for row in m.buttons:
                        for b in row:
                            btns.append(b.text)
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
                            btns = []
                            if m.buttons:
                                for r in m.buttons:
                                    for bb in r:
                                        btns.append(bb.text)
                            return m.text or "", btns, m
                    updated = await client.get_messages(bot, ids=msg.id)
                    if updated and updated.edit_date and updated.text != (msg.text or ""):
                        btns = []
                        if updated.buttons:
                            for r in updated.buttons:
                                for bb in r:
                                    btns.append(bb.text)
                        return updated.text or "", btns, updated
                return None, [], None
    return None, [], None


async def main():
    if not NVIDIA_KEY:
        print("ERROR: Set NVIDIA_API_KEY env var")
        return

    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    bot = await client.get_entity(BOT)
    print(f"Testing as: {me.first_name}")

    passed = 0
    total = 0

    def check(name, ok, detail=""):
        nonlocal passed, total
        total += 1
        if ok:
            passed += 1
            print(f"  [OK]  {name}")
        else:
            print(f"  [BUG] {name}")
            if detail:
                print(f"         -> {detail[:300]}")

    # Step 1: /setai
    print("\n--- /setai ---")
    text, btns, msg = await send_wait(client, bot, "/setai", wait=10)
    check("/setai responds", text is not None)
    check("Shows provider options", any("OpenAI" in b or "DeepSeek" in b for b in btns), str(btns))
    await asyncio.sleep(2)

    # Step 2: Click OpenAI/DeepSeek provider
    print("\n--- Select OpenAI/DeepSeek ---")
    text2, btns2, msg2 = await click_btn(client, bot, msg, "OpenAI", wait=10)
    check("Provider selected", text2 is not None and "API key" in text2.lower(), (text2 or "")[:200])
    await asyncio.sleep(2)

    # Step 3: Send NVIDIA API key in format: key|base_url|model
    print("\n--- Submit NVIDIA API key ---")
    api_string = f"{NVIDIA_KEY}|{NVIDIA_BASE}|{NVIDIA_MODEL}"
    text3, btns3, msg3 = await send_wait(client, bot, api_string, wait=30)
    # Might get "Testing..." first
    if text3 and "Testing" in text3:
        await asyncio.sleep(15)
        msgs = await client.get_messages(bot, limit=3, from_user=bot)
        for m in msgs:
            if m.id > (msg3.id if msg3 else 0):
                text3 = m.text or ""
                btns3 = []
                if m.buttons:
                    for row in m.buttons:
                        for b in row:
                            btns3.append(b.text)
                msg3 = m
                break

    check("API key accepted", text3 and ("Activated" in text3 or "Professional" in str(btns3)), (text3 or "")[:200])
    if btns3:
        check("Personality selection shown", any("Professional" in b for b in btns3), str(btns3))
    await asyncio.sleep(2)

    # Step 4: Pick personality
    if msg3 and msg3.buttons:
        print("\n--- Pick personality ---")
        text4, _, _ = await click_btn(client, bot, msg3, "Professional", wait=10)
        check("Personality set", text4 and "Professional" in text4, (text4 or "")[:200])
        await asyncio.sleep(3)

    # Step 5: Test AI response with NVIDIA model
    print("\n--- Chat with NVIDIA model ---")
    text5, _, _ = await send_wait(client, bot, "What's BTC price right now?", wait=90)
    if text5:
        check("NVIDIA model responds", True)
        check("Response mentions BTC or $", "BTC" in text5 or "$" in text5, text5[:200])
        print(f"         Response: {text5[:200]}")
    else:
        check("NVIDIA model responds", False, "Timeout")

    await asyncio.sleep(5)

    # Step 6: Test strategy
    print("\n--- Strategy with NVIDIA ---")
    text6, _, _ = await send_wait(client, bot, "CRCL is going up, how to play it?", wait=90)
    if text6:
        check("Strategy response", len(text6) > 30, text6[:200])
        print(f"         Response: {text6[:200]}")
    else:
        check("Strategy", False, "Timeout")

    print(f"\n{'=' * 50}")
    print(f"  RESULTS: {passed}/{total} passed")
    print(f"{'=' * 50}")

    await client.disconnect()

asyncio.run(main())
