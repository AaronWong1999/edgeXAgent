import asyncio, httpx, json

TOKEN = open(".env").read().split("TELEGRAM_BOT_TOKEN=")[1].split("\n")[0].strip()
CHAT_ID = 7894288399
BASE = f"https://api.telegram.org/bot{TOKEN}"

def sl(side):
    s = side.upper()
    if s == "BUY": return "LONG"
    if s == "SELL": return "SHORT"
    return side

async def send(text, kb=None):
    async with httpx.AsyncClient(timeout=10) as h:
        d = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
        if kb: d["reply_markup"] = json.dumps(kb)
        r = await h.post(f"{BASE}/sendMessage", json=d)
        j = r.json()
        if not j.get("ok"):
            print("SEND ERROR:", j.get("description", "")[:100])
        return j.get("result", {}).get("message_id")

MM = {"inline_keyboard": [[{"text": "\U0001f3e0 Main Menu", "callback_data": "back_to_dashboard"}]]}

async def main():
    # Simulate real order data as returned by edgeX API
    orders = [
        {"contractName": "BTCUSD", "side": "BUY", "type": "LIMIT", "size": "0.003",
         "price": "70000", "orderId": "698234567890123456", "createdTime": "1709654400000"},
        {"contractName": "ETHUSD", "side": "SELL", "type": "LIMIT", "size": "0.05",
         "price": "4100", "orderId": "698234567890123999", "createdTime": "1709740800000"},
    ]

    # [1] Orders list (like the bot shows)
    lines = ["\U0001f4cb *Open Orders \u2014 Trade on edgeX*\n"]
    for o in orders:
        sym = o["contractName"].replace("USD", "")
        side = sl(o["side"])
        otype = o.get("type", "LIMIT")
        sz = o["size"]
        px = o["price"]
        lines.append(f"\u2022 {sym} {side} {otype} | Size: `{sz}` @ `${px}`")
    lines.append(f"\n{len(orders)} active order(s)")
    mid1 = await send("\n".join(lines), {"inline_keyboard": [
        [{"text": "\u274c Cancel " + orders[0]["contractName"].replace("USD","") + " " + sl(orders[0]["side"]),
          "callback_data": "test"}],
        [{"text": "\u274c Cancel " + orders[1]["contractName"].replace("USD","") + " " + sl(orders[1]["side"]),
          "callback_data": "test"}],
        [{"text": "\u274c Cancel All Orders", "callback_data": "test"}],
        [{"text": "\U0001f519 Back", "callback_data": "test"}],
    ]})
    print(f"[1] Orders list sent (msg {mid1})")
    await asyncio.sleep(2)

    # [2] Cancel single order confirm
    o = orders[0]
    sym = o["contractName"].replace("USD", "")
    side = sl(o["side"])
    otype = o.get("type", "LIMIT")
    sz = o["size"]
    px = o["price"]
    oid = o["orderId"]
    cancel_text = (
        "\u274c *Cancel Order \u2014 Trade on edgeX*\n\n"
        "\u26a0\ufe0f Cancel this order?\n\n"
        "\u251c " + sym + " " + side + " " + otype + "\n"
        "\u251c Size: `" + sz + "` | Price: `$" + px + "`\n"
        "\u2514 Order ID: `" + oid + "`"
    )
    mid2 = await send(cancel_text, {"inline_keyboard": [
        [{"text": "\u2705 Yes, cancel", "callback_data": "test"},
         {"text": "\u274c Keep order", "callback_data": "test"}]
    ]})
    print(f"[2] Cancel confirm sent (msg {mid2})")
    await asyncio.sleep(2)

    # [3] Cancel success
    mid3 = await send(
        "\u2705 *Order Cancelled \u2014 Trade on edgeX*\n\n"
        "Order `" + oid + "` cancelled successfully.", MM)
    print(f"[3] Cancel success sent (msg {mid3})")
    await asyncio.sleep(2)

    # [4] Cancel kept
    mid4 = await send("\U0001f4cb *Orders \u2014 Trade on edgeX*\n\n\u274c Cancelled. Orders kept.", MM)
    print(f"[4] Cancel kept sent (msg {mid4})")
    await asyncio.sleep(2)

    # [5] Cancel All confirm
    lines2 = [
        "\u274c *Cancel All Orders \u2014 Trade on edgeX*\n\n"
        "\u26a0\ufe0f Cancel ALL open orders?\n\n"
        f"{len(orders)} order(s):"
    ]
    for o in orders:
        sym = o["contractName"].replace("USD", "")
        side = sl(o["side"])
        lines2.append(f"\u2022 {sym} {side} {o['size']} @ ${o['price']}")
    mid5 = await send("\n".join(lines2), {"inline_keyboard": [
        [{"text": "\u2705 Yes, cancel all", "callback_data": "test"},
         {"text": "\u274c Keep orders", "callback_data": "test"}]
    ]})
    print(f"[5] Cancel All confirm sent (msg {mid5})")
    await asyncio.sleep(2)

    # [6] Cancel All success
    mid6 = await send("\u2705 *Orders Cancelled \u2014 Trade on edgeX*\n\n\u2705 All orders cancelled.", MM)
    print(f"[6] Cancel All success sent (msg {mid6})")
    await asyncio.sleep(2)

    # [7] Cancel All kept
    mid7 = await send("\U0001f4cb *Orders \u2014 Trade on edgeX*\n\n\u274c Cancelled. Orders kept.", MM)
    print(f"[7] Cancel All kept sent (msg {mid7})")
    await asyncio.sleep(2)

    # [8] Logout confirm
    mid8 = await send(
        "\U0001f6aa *Disconnect \u2014 Trade on edgeX*\n\n"
        "This will log out your edgeX account. Are you sure?",
        {"inline_keyboard": [
            [{"text": "\u2705 Yes, logout", "callback_data": "test"},
             {"text": "\u274c Cancel", "callback_data": "test"}]
        ]})
    print(f"[8] Logout confirm sent (msg {mid8})")
    await asyncio.sleep(2)

    # [9] Logout yes
    mid9 = await send("\U0001f6aa *Disconnect \u2014 Trade on edgeX*\n\n\u2705 Successfully logged out.", MM)
    print(f"[9] Logout yes sent (msg {mid9})")
    await asyncio.sleep(2)

    # [10] Logout no
    mid10 = await send(
        "\U0001f6aa *Disconnect \u2014 Trade on edgeX*\n\n"
        "\u274c Logout cancelled. Your account is still connected.", MM)
    print(f"[10] Logout no sent (msg {mid10})")

    print("\n\u2705 All 10 order/logout screens sent!")

asyncio.run(main())
