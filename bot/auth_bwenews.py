"""One-time Telethon authentication for BWEnews MCP.
Usage: TG_PHONE=+85365712199 python3 auth_bwenews.py
Then enter the code sent to your TG app.
"""
import asyncio
import os
import sys
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

api_id = int(os.environ.get("TG_API_ID", "0"))
api_hash = os.environ.get("TG_API_HASH", "")
phone = os.environ.get("TG_PHONE", "")

if not phone:
    phone = input("Enter phone number (with country code): ").strip()

def code_callback():
    code = os.environ.get("TG_CODE", "")
    if code:
        print(f"Using code from env: {code}")
        return code
    code_file = os.path.join(os.path.dirname(__file__), ".tg_code")
    print(f"Waiting for code in {code_file} ...", flush=True)
    for _ in range(300):
        if os.path.exists(code_file):
            code = open(code_file).read().strip()
            os.remove(code_file)
            print(f"Got code: {code}", flush=True)
            return code
        import time; time.sleep(1)
    raise RuntimeError("Timeout waiting for code")


async def main():
    session_path = os.path.join(os.path.dirname(__file__), "bwenews_session")
    client = TelegramClient(session_path, api_id, api_hash)
    await client.start(phone=phone, code_callback=code_callback)
    me = await client.get_me()
    print(f"Authenticated as: {me.first_name} (id={me.id})")

    entity = await client.get_entity("BWEnews")
    print(f"Channel: @BWEnews (id={entity.id})")

    msgs = await client.get_messages(entity, limit=3)
    for m in msgs:
        print(f"  [{m.date}] {(m.text or '')[:80]}")

    await client.disconnect()
    print("Session saved. You can now start the bwenews-mcp service.")

asyncio.run(main())
