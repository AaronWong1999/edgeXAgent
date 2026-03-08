"""Self-test: send messages as real user via Telethon, check bot replies."""
import asyncio
import os
import sys
import time

from telethon import TelegramClient

API_ID = int(os.environ.get("TG_API_ID", "32692718"))
API_HASH = os.environ.get("TG_API_HASH", "699fd59ab02a0f09b89db38c4a6ff149")
BOT_USERNAME = "edgeXAgentBot"
SESSION = os.environ.get("TG_SESSION", os.path.expanduser("~/qa_user_session"))

TESTS = [
    ("/start", 8, "Event Trading"),
    ("/news", 8, None),
    ("/status", 8, None),
    ("/pnl", 8, None),
    ("/history", 8, None),
    ("/memory", 8, "Memory"),
    ("What is BTC price right now?", 30, None),
    ("short NVDA 50 dollars", 30, None),
    ("CRCL现在什么价格", 30, None),
]


async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    entity = await client.get_entity(BOT_USERNAME)

    results = []
    for text, timeout, must_contain in TESTS:
        sent = await client.send_message(entity, text)
        sent_id = sent.id
        deadline = time.time() + timeout
        reply_text = None

        while time.time() < deadline:
            await asyncio.sleep(2)
            msgs = await client.get_messages(entity, limit=5)
            for m in msgs:
                if m.id > sent_id and m.sender_id != (await client.get_me()).id:
                    reply_text = (m.text or "")[:200]
                    break
            if reply_text is not None:
                break

        status = "PASS" if reply_text else "FAIL"
        if must_contain and reply_text and must_contain not in reply_text:
            status = "PARTIAL"

        results.append((text[:40], status, (reply_text or "NO_RESPONSE")[:120]))
        print(f"  [{status}] {text[:40]} -> {(reply_text or 'NO_RESPONSE')[:80]}")

        # Wait between tests to avoid stale cancel
        await asyncio.sleep(5)

    await client.disconnect()

    passed = sum(1 for _, s, _ in results if s == "PASS")
    total = len(results)
    print(f"\n=== {passed}/{total} PASS ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
