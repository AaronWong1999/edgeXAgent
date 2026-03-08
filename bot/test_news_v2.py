import asyncio, httpx, json

TOKEN = open(".env").read().split("TELEGRAM_BOT_TOKEN=")[1].split("\n")[0].strip()
CHAT_ID = 7894288399
BASE = f"https://api.telegram.org/bot{TOKEN}"

async def send(text, kb=None):
    async with httpx.AsyncClient(timeout=10) as h:
        d = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown",
             "disable_web_page_preview": True}
        if kb: d["reply_markup"] = json.dumps(kb)
        r = await h.post(f"{BASE}/sendMessage", json=d)
        j = r.json()
        if not j.get("ok"):
            print("ERROR:", j.get("description", "")[:200])
            return None
        return j.get("result", {}).get("message_id")

async def main():
    # [1] New-format news alert (BTC BULLISH)
    mid = await send(
        "*A16Z CRYPTO TARGETS AROUND $2B FOR ITS FIFTH FUND: BBG*\n\n"
        "\U0001f7e2 BTC | BULLISH | \u2588\u2588\u2591 MEDIUM\n"
        "\u2b06\ufe0f LONG @ `$87,432.5` | 3x | TP `$94,427.1` SL `$83,935.2`",
        {"inline_keyboard": [
            [{"text": "\u2b06\ufe0f LONG BTC $50 3x", "callback_data": "nt_BTC_BUY_3_50"}],
            [{"text": "\u2b06\ufe0f LONG BTC $100 3x", "callback_data": "nt_BTC_BUY_3_100"}],
            [{"text": "\u2b06\ufe0f LONG BTC $200 3x", "callback_data": "nt_BTC_BUY_3_200"}],
            [{"text": "\U0001f1e8\U0001f1f3", "callback_data": "tl_zh"},
             {"text": "\U0001f1ef\U0001f1f5", "callback_data": "tl_ja"},
             {"text": "\U0001f1f0\U0001f1f7", "callback_data": "tl_ko"},
             {"text": "\U0001f1f7\U0001f1fa", "callback_data": "tl_ru"}],
        ]})
    print(f"[1] BTC BULLISH alert sent (msg {mid})")
    await asyncio.sleep(2)

    # [2] Macro news → QQQ SHORT
    mid = await send(
        "*FED SIGNALS MORE RATE HIKES AHEAD AS INFLATION PERSISTS*\n\n"
        "\U0001f534 QQQ | BEARISH | \u2588\u2588\u2588 HIGH\n"
        "\u2b07\ufe0f SHORT @ `$482.30` | 3x | TP `$443.72` SL `$501.59`",
        {"inline_keyboard": [
            [{"text": "\u2b07\ufe0f SHORT QQQ $50 3x", "callback_data": "nt_QQQ_SELL_3_50"}],
            [{"text": "\u2b07\ufe0f SHORT QQQ $100 3x", "callback_data": "nt_QQQ_SELL_3_100"}],
            [{"text": "\u2b07\ufe0f SHORT QQQ $200 3x", "callback_data": "nt_QQQ_SELL_3_200"}],
            [{"text": "\U0001f1e8\U0001f1f3", "callback_data": "tl_zh"},
             {"text": "\U0001f1ef\U0001f1f5", "callback_data": "tl_ja"},
             {"text": "\U0001f1f0\U0001f1f7", "callback_data": "tl_ko"},
             {"text": "\U0001f1f7\U0001f1fa", "callback_data": "tl_ru"}],
        ]})
    print(f"[2] QQQ BEARISH alert sent (msg {mid})")
    await asyncio.sleep(2)

    # [3] Trade Defaults screen
    mid = await send(
        "\u2699\ufe0f *Trade Defaults \u2014 Event Trading*\n\n"
        "Leverage: *3x*\n"
        "Amounts: *$50* / *$100* / *$200*\n"
        "Take Profit: *+8.0%*\n"
        "Stop Loss: *-4.0%*",
        {"inline_keyboard": [
            [{"text": "Leverage: 3x", "callback_data": "ntd_leverage"}],
            [{"text": "Amounts: $50/$100/$200", "callback_data": "ntd_amounts"}],
            [{"text": "TP: +8.0%", "callback_data": "ntd_tp"},
             {"text": "SL: -4.0%", "callback_data": "ntd_sl"}],
            [{"text": "\U0001f519 Back", "callback_data": "news_settings"}],
        ]})
    print(f"[3] Trade Defaults sent (msg {mid})")
    await asyncio.sleep(2)

    # [4] Leverage picker
    mid = await send(
        "\u2699\ufe0f *Leverage \u2014 Trade Defaults*\n\n"
        "Current: *3x*\n\nSelect default leverage:",
        {"inline_keyboard": [
            [{"text": "2x", "callback_data": "ntd_setlev_2"},
             {"text": "> 3x", "callback_data": "ntd_setlev_3"},
             {"text": "5x", "callback_data": "ntd_setlev_5"}],
            [{"text": "\U0001f519 Back", "callback_data": "news_trade_defaults"}],
        ]})
    print(f"[4] Leverage picker sent (msg {mid})")
    await asyncio.sleep(2)

    # [5] Amounts picker
    mid = await send(
        "\u2699\ufe0f *Trade Amounts \u2014 Trade Defaults*\n\n"
        "Current: *$50 / $100 / $200*\n\nSelect 3 tiers:",
        {"inline_keyboard": [
            [{"text": "$25/$50/$100", "callback_data": "ntd_setamt_25_50_100"}],
            [{"text": "> $50/$100/$200", "callback_data": "ntd_setamt_50_100_200"}],
            [{"text": "$100/$200/$500", "callback_data": "ntd_setamt_100_200_500"}],
            [{"text": "\U0001f519 Back", "callback_data": "news_trade_defaults"}],
        ]})
    print(f"[5] Amounts picker sent (msg {mid})")

    print("\n\u2705 All 5 screens sent!")

asyncio.run(main())
