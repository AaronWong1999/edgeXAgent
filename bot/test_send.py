import asyncio, httpx, json, ai_trader

TOKEN = open(".env").read().split("TELEGRAM_BOT_TOKEN=")[1].split("\n")[0].strip()
CHAT_ID = 7894288399
BASE = f"https://api.telegram.org/bot{TOKEN}"

async def send(text, kb=None):
    async with httpx.AsyncClient(timeout=10) as h:
        d = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
        if kb: d["reply_markup"] = json.dumps(kb)
        r = await h.post(f"{BASE}/sendMessage", json=d)
        return r.json().get("result", {}).get("message_id")

MM = {"inline_keyboard": [[{"text": "\U0001f3e0 Main Menu", "callback_data": "back_to_dashboard"}]]}

async def main():
    plan = await ai_trader.generate_trade_plan("long doge 10u 5x", market_prices=None, tg_user_id=CHAT_ID)
    if plan.get("action") != "TRADE":
        print("Not TRADE:", plan.get("reply", "")[:100])
        return

    sw = "LONG" if plan.get("side") == "BUY" else "SHORT"
    se = "\u2b06\ufe0f" if plan.get("side") == "BUY" else "\u2b07\ufe0f"
    a = plan.get("asset", "?")
    l = plan.get("leverage", "1")
    v = plan.get("position_value_usd", "?")
    tp = plan.get("take_profit", "")
    sl = plan.get("stop_loss", "")
    ep = plan.get("entry_price", "?")
    sz = plan.get("size", "?")
    btn = f"{se} {sw} {a} ${v} {l}x"
    if tp: btn += f" TP:${tp}"
    if sl: btn += f" SL:${sl}"

    reasoning = plan.get("reasoning", "")
    text = f"\u2728 {reasoning}" if reasoning else f"\u2728 {sw} {a} looks good."

    # [1] AI suggestion with trade button
    mid = await send(text, {"inline_keyboard": [
        [{"text": btn, "callback_data": "show_trade_plan"}],
        [{"text": "\U0001f3e0 Main Menu", "callback_data": "back_to_dashboard"}]
    ]})
    print(f"[1] AI suggestion sent (msg {mid})")
    print(f"    Button: {btn}")
    await asyncio.sleep(2)

    # [2] Trade Plan
    plan_text = ai_trader.format_trade_plan(plan)
    mid2 = await send(plan_text, {"inline_keyboard": [
        [{"text": "\u2705 Confirm Execute", "callback_data": "confirm_trade"},
         {"text": "\u274c Cancel", "callback_data": "cancel_trade"}]
    ]})
    print(f"[2] Trade Plan sent (msg {mid2})")
    await asyncio.sleep(2)

    # [3] Trade success
    success = (
        se + " *" + sw + " " + a + " \u2014 Trade on edgeX*\n\n"
        "\u2705 Order Placed!\n\n"
        "\u251c Entry: `$" + str(ep) + "`\n"
        "\u251c Size: `" + str(sz) + "` (" + str(l) + "x)\n"
        "\u251c Value: `~$" + str(v) + "`\n"
        "\u251c TP: `$" + str(tp) + "`\n"
        "\u251c SL: `$" + str(sl) + "`\n"
        "\u2514 Order ID: `ord_test_12345678`"
    )
    mid3 = await send(success, MM)
    print(f"[3] Trade Success sent (msg {mid3})")
    await asyncio.sleep(2)

    # [4] Trade cancel
    mid4 = await send("\u274c *Trade Cancelled \u2014 Trade on edgeX*\n\nNo order was placed.", MM)
    print(f"[4] Trade Cancel sent (msg {mid4})")
    await asyncio.sleep(2)

    # [5] Trade failed
    mid5 = await send("\u274c *Trade Failed \u2014 Trade on edgeX*\n\nInsufficient balance (available: `$14.84`)", MM)
    print(f"[5] Trade Failed sent (msg {mid5})")
    await asyncio.sleep(2)

    # [6] BTC insufficient balance (CHAT response)
    plan2 = await ai_trader.generate_trade_plan("long btc 50u", market_prices=None, tg_user_id=CHAT_ID)
    reply = plan2.get("reply", "Insufficient balance")
    mid6 = await send("\u2728 " + reply, MM)
    print(f"[6] BTC insufficient (CHAT) sent (msg {mid6})")
    print(f"    Reply: {reply[:100]}")

    print("\n\u2705 All 6 screens sent to TG!")

asyncio.run(main())
