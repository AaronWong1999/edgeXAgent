"""Quick test: /status, /pnl, /history commands only."""
import asyncio, os
from telethon import TelegramClient

API_ID = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
BOT = "edgeXAgentBot"

async def send_wait(client, bot, text, wait=15):
    msgs = await client.get_messages(bot, limit=1, from_user=bot)
    before = msgs[0].id if msgs else 0
    await client.send_message(bot, text)
    for _ in range(wait * 2):
        await asyncio.sleep(0.5)
        msgs = await client.get_messages(bot, limit=3, from_user=bot)
        for m in msgs:
            if m.id > before:
                return m.text or ""
    return None

async def main():
    client = TelegramClient("tg_test_session", API_ID, API_HASH)
    await client.start()
    bot = await client.get_entity(BOT)

    for cmd in ["/status", "/pnl", "/history"]:
        text = await send_wait(client, bot, cmd)
        print(f"\n{'='*40}")
        print(f"  {cmd}")
        print(f"{'='*40}")
        if text:
            print(text[:800])
        else:
            print("  [NO RESPONSE]")
        await asyncio.sleep(3)

    await client.disconnect()

asyncio.run(main())
