import asyncio, httpx, json

TOKEN = open(".env").read().split("TELEGRAM_BOT_TOKEN=")[1].split("\n")[0].strip()
CHAT_ID = 7894288399
BASE = f"https://api.telegram.org/bot{TOKEN}"

async def send(text, kb=None):
    async with httpx.AsyncClient(timeout=10) as h:
        d = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
        if kb: d["reply_markup"] = json.dumps(kb)
        r = await h.post(f"{BASE}/sendMessage", json=d)
        j = r.json()
        if not j.get("ok"):
            print("ERROR:", j.get("description", "")[:200])
        return j.get("result", {}).get("message_id")

async def main():
    # [1] Event Trading Hub (new UI)
    await send(
        "\U0001f4f0 *Event Trading \u2014 Event Trading*\n\n"
        "AI-analyzed news with one-tap trade buttons.\n\n"
        "\u2705 *BWEnews* \u2014 5/hr",
        {"inline_keyboard": [
            [{"text": "BWEnews", "callback_data": "news_noop_bwenews"}],
            [{"text": "\U0001f534 Switch OFF", "callback_data": "test"},
             {"text": "\U0001f552", "callback_data": "test"},
             {"text": "\U0001f5d1", "callback_data": "test"}],
            [{"text": "\u2795 Add News Source", "callback_data": "test"}],
            [{"text": "\U0001f519 Back", "callback_data": "test"}],
        ]}
    )
    print("[1] Event Trading Hub sent")
    await asyncio.sleep(2)

    # [2] Frequency picker
    await send(
        "\u23f1 *Push Frequency \u2014 Event Trading*\n\n"
        "How many alerts per hour?\nCurrent: *5/hr*",
        {"inline_keyboard": [
            [{"text": "1/hr", "callback_data": "test"},
             {"text": "2/hr", "callback_data": "test"},
             {"text": "3/hr", "callback_data": "test"}],
            [{"text": "> 5/hr", "callback_data": "test"},
             {"text": "10/hr", "callback_data": "test"}],
            [{"text": "\U0001f519 Back", "callback_data": "test"}],
        ]}
    )
    print("[2] Frequency picker sent")
    await asyncio.sleep(2)

    # [3] Add Source (MCP URL input)
    await send(
        "\u2795 *Add News Source \u2014 Event Trading*\n\n"
        "Send an MCP news server URL:\n\n"
        "Format: `https://your-server.com/mcp`\n\n"
        "_The server must support MCP JSON-RPC tools/call._\n\n"
        "Send /cancel to go back.",
        {"inline_keyboard": [
            [{"text": "\U0001f519 Back", "callback_data": "test"}],
        ]}
    )
    print("[3] Add Source sent")
    await asyncio.sleep(2)

    # [4] Hub with source OFF
    await send(
        "\U0001f4f0 *Event Trading \u2014 Event Trading*\n\n"
        "AI-analyzed news with one-tap trade buttons.\n\n"
        "\u274c *BWEnews* \u2014 5/hr",
        {"inline_keyboard": [
            [{"text": "BWEnews", "callback_data": "test"}],
            [{"text": "\U0001f7e2 Switch ON", "callback_data": "test"},
             {"text": "\U0001f552", "callback_data": "test"},
             {"text": "\U0001f5d1", "callback_data": "test"}],
            [{"text": "\u2795 Add News Source", "callback_data": "test"}],
            [{"text": "\U0001f519 Back", "callback_data": "test"}],
        ]}
    )
    print("[4] Hub OFF state sent")

    print("\n\u2705 All 4 Event Trading UI screens sent!")

asyncio.run(main())
