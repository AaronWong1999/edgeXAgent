"""Test that ntd_amounts/ntd_tp/ntd_sl handlers work (were missing before fix)."""
import asyncio, httpx, json

TOKEN = open(".env").read().split("TELEGRAM_BOT_TOKEN=")[1].split("\n")[0].strip()
CHAT_ID = 7894288399
BASE = f"https://api.telegram.org/bot{TOKEN}"

async def send(text, kb=None):
    async with httpx.AsyncClient(timeout=10) as h:
        d = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
        if kb: d["reply_markup"] = json.dumps(kb)
        r = await h.post(f"{BASE}/sendMessage", json=d)
        return r.json().get("result", {}).get("message_id")

async def main():
    # Test: send amounts picker with real callback (should work after fix)
    mid = await send(
        "\u2699\ufe0f *Trade Amounts \u2014 Trade Defaults*\n\nCurrent: *$50 / $100 / $200*\n\nSelect 3 tiers:",
        {"inline_keyboard": [
            [{"text": "$25/$50/$100", "callback_data": "ntd_setamt_25_50_100"}],
            [{"text": "> $50/$100/$200", "callback_data": "ntd_setamt_50_100_200"}],
            [{"text": "$100/$200/$500", "callback_data": "ntd_setamt_100_200_500"}],
            [{"text": "\U0001f519 Back", "callback_data": "news_trade_defaults"}],
        ]})
    print(f"Amounts picker sent (msg {mid}) - click buttons to test!")

asyncio.run(main())
