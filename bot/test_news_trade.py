"""Test news trade button flow: simulates clicking a news trade button."""
import asyncio, os, sys, time
from telethon import TelegramClient
from telethon.tl.types import ReplyInlineMarkup

API_ID = int(os.environ.get("TG_API_ID", "32692718"))
API_HASH = os.environ.get("TG_API_HASH", "699fd59ab02a0f09b89db38c4a6ff149")
SESSION_FILE = "tg_test_session"
BOT = "edgeXAgentBot"


async def last_id(client, bot):
    msgs = await client.get_messages(bot, limit=1, from_user=bot)
    return msgs[0].id if msgs else 0


async def send(client, bot, text, wait=15):
    before = await last_id(client, bot)
    await client.send_message(bot, text)
    deadline = time.time() + wait
    while time.time() < deadline:
        await asyncio.sleep(0.5)
        msgs = await client.get_messages(bot, limit=5, from_user=bot)
        for m in msgs:
            if m.id > before:
                btns = [b.text for row in (m.buttons or []) for b in row]
                return m.text or "", btns, m
    return None, [], None


async def tap(client, bot, msg, btn_text, wait=60):
    if not msg or not msg.buttons:
        return None, [], None
    for row in msg.buttons:
        for b in row:
            if btn_text.lower() in b.text.lower():
                before = await last_id(client, bot)
                original_text = msg.text
                await b.click()
                deadline = time.time() + wait
                last_seen = original_text
                while time.time() < deadline:
                    await asyncio.sleep(1)
                    # Check for new messages
                    msgs = await client.get_messages(bot, limit=5, from_user=bot)
                    for m in msgs:
                        if m.id > before:
                            btns = [bb.text for r in (m.buttons or []) for bb in r]
                            return m.text or "", btns, m
                    # Check edited message
                    updated = await client.get_messages(bot, ids=msg.id)
                    if updated and updated.text and updated.text != last_seen:
                        if "🔄" in updated.text or "Generating" in updated.text:
                            last_seen = updated.text
                            print(f"    [transient] {updated.text[:80]}")
                            continue
                        btns = [bb.text for r in (updated.buttons or []) for bb in r]
                        return updated.text or "", btns, updated
                return None, [], None
    return None, [], None


async def main():
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    bot = await client.get_entity(BOT)
    print(f"Testing as: {me.first_name} (ID: {me.id})\n")

    # Make sure connected
    text, btns, msg = await send(client, bot, "/start", wait=10)
    if not any("Status" in b for b in btns):
        print("Not connected! Connect first.")
        await client.disconnect()
        sys.exit(1)
    print(f"[OK] Connected, dashboard has {len(btns)} buttons\n")

    # Check for recent news alerts with trade buttons
    print("Looking for news alerts with trade buttons...")
    msgs = await client.get_messages(bot, limit=20, from_user=bot)
    news_msg = None
    for m in msgs:
        if m.buttons:
            for row in m.buttons:
                for b in row:
                    if "LONG" in b.text or "SHORT" in b.text:
                        news_msg = m
                        break
                if news_msg:
                    break
        if news_msg:
            break

    if news_msg:
        print(f"[OK] Found news alert:")
        print(f"     {news_msg.text[:100]}...")
        trade_btns = []
        for row in news_msg.buttons:
            for b in row:
                trade_btns.append(b.text)
        print(f"     Buttons: {trade_btns}")

        # Check button format — should show $ amounts, not "small"/"medium"
        has_dollar = any("$" in b for b in trade_btns if "LONG" in b or "SHORT" in b)
        has_small = any("small" in b.lower() for b in trade_btns)
        has_medium = any("medium" in b.lower() for b in trade_btns)
        print(f"\n     Has $ amounts: {has_dollar}")
        print(f"     Has 'small': {has_small}")
        print(f"     Has 'medium': {has_medium}")

        if has_dollar:
            print("\n[OK] Buttons show specific dollar amounts!")
        elif has_small or has_medium:
            print("\n[BUG] Buttons still say 'small'/'medium' — old format")

        # Click the first trade button
        for b_text in trade_btns:
            if "LONG" in b_text or "SHORT" in b_text:
                print(f"\n>> Clicking: '{b_text}'")
                result_text, result_btns, result_msg = await tap(client, bot, news_msg, b_text, wait=60)
                if result_text:
                    print(f"\n[RESULT]:\n{result_text[:500]}")
                    print(f"\nButtons: {result_btns}")
                    if "Trade failed" in result_text or "error" in result_text.lower():
                        print("\n[BUG] Trade failed!")
                    elif "Confirm" in str(result_btns):
                        print("\n[OK] Trade plan generated with Confirm button!")
                        # Cancel it
                        c_text, _, _ = await tap(client, bot, result_msg, "Cancel", wait=10)
                        print(f"[OK] Cancelled: {(c_text or '')[:80]}")
                    else:
                        print(f"\n[INFO] Got response (may be analysis/chat)")
                else:
                    print("\n[BUG] No response after clicking trade button")
                break
    else:
        # No news alerts found — simulate by sending a trade request directly
        print("[INFO] No news alerts found. Testing trade flow directly...")
        print('\n>> "long XAUT with $30 at 2x leverage"')
        text, btns, msg = await send(client, bot, "long XAUT with $30 at 2x leverage", wait=60)
        if text:
            print(f"\n[RESULT]:\n{text[:500]}")
            print(f"\nButtons: {btns}")
            if any("Confirm" in b for b in btns):
                print("\n[OK] Trade plan generated!")
                c_text, _, _ = await tap(client, bot, msg, "Cancel", wait=10)
                print(f"[OK] Cancelled: {(c_text or '')[:80]}")
        else:
            print("[BUG] No response")

    await client.disconnect()


asyncio.run(main())
