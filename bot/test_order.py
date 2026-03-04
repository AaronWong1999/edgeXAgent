"""Test real order placement with small DOGE position."""
import asyncio
from telethon import TelegramClient

async def main():
    import os
    api_id = int(os.environ.get("TG_API_ID", "0"))
    api_hash = os.environ.get("TG_API_HASH", "")
    client = TelegramClient("tg_test_session", api_id, api_hash)
    await client.start()
    bot = await client.get_entity("edgeXAgentBot")

    msgs = await client.get_messages(bot, limit=1, from_user=bot)
    before_id = msgs[0].id if msgs else 0

    await client.send_message(bot, "long DOGE, 10 DOGE, 1x leverage")
    print("Sent trade request...")

    for i in range(120):
        await asyncio.sleep(0.5)
        msgs = await client.get_messages(bot, limit=3, from_user=bot)
        for m in msgs:
            if m.id > before_id:
                txt = m.text[:300] if m.text else "(empty)"
                print(f"Response: {txt}")
                btns = []
                if m.buttons:
                    for row in m.buttons:
                        for b in row:
                            btns.append(b.text)
                print(f"Buttons: {btns}")

                if any("Confirm" in b for b in btns):
                    print("--- Clicking Confirm... ---")
                    for row in m.buttons:
                        for b in row:
                            if "Confirm" in b.text:
                                await b.click()
                                break
                        break
                    await asyncio.sleep(12)
                    updated = await client.get_messages(bot, ids=m.id)
                    if updated:
                        txt2 = updated.text[:300] if updated.text else "(empty)"
                        print(f"After confirm: {txt2}")

                await client.disconnect()
                return

    print("No response")
    await client.disconnect()

asyncio.run(main())
