"""Step 1: Send code request. Step 2: Sign in with code."""
import asyncio
import sys
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

import os
API_ID = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
PHONE = os.environ.get("TG_PHONE", "")
SESSION = "qa_user_session"

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Already authorized as: {me.first_name} (ID: {me.id})")
        await client.disconnect()
        return

    if len(sys.argv) < 2:
        # Step 1: request code
        result = await client.send_code_request(PHONE)
        print(f"Code sent to {PHONE}. Phone code hash: {result.phone_code_hash}")
        print(f"Run again with: python3 auth_qa_session.py <code> {result.phone_code_hash}")
        await client.disconnect()
        return

    # Step 2: sign in with code
    code = sys.argv[1]
    phone_hash = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        await client.sign_in(PHONE, code, phone_code_hash=phone_hash)
    except SessionPasswordNeededError:
        print("2FA required. Enter password as 3rd argument.")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"Signed in as: {me.first_name} (ID: {me.id})")
    await client.disconnect()

asyncio.run(main())
