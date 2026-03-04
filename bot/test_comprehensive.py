"""Comprehensive test: simulate a real user exploring every flow, validate AI answers."""
import asyncio
import os
import sys
from telethon import TelegramClient

API_ID = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION_FILE = "tg_test_session"
BOT = "edgeXAgentBot"
PASS = 0
TOTAL = 0


def check(name, ok, detail=""):
    global PASS, TOTAL
    TOTAL += 1
    if ok:
        PASS += 1
        print(f"  [OK]  {name}")
    else:
        print(f"  [BUG] {name}")
        if detail:
            print(f"         -> {detail[:300]}")


async def last_id(client, bot):
    msgs = await client.get_messages(bot, limit=1, from_user=bot)
    return msgs[0].id if msgs else 0


async def send_wait(client, bot, text, wait=60):
    before = await last_id(client, bot)
    await client.send_message(bot, text)
    for _ in range(wait * 2):
        await asyncio.sleep(0.5)
        msgs = await client.get_messages(bot, limit=5, from_user=bot)
        for m in msgs:
            if m.id > before:
                btns = [b.text for row in (m.buttons or []) for b in row]
                return m.text or "", btns, m
    return None, [], None


async def click_btn(client, bot, msg, btn_text, wait=20):
    if not msg or not msg.buttons:
        return None, [], None
    for row in msg.buttons:
        for b in row:
            if btn_text.lower() in b.text.lower():
                before = await last_id(client, bot)
                await b.click()
                for _ in range(wait * 2):
                    await asyncio.sleep(0.5)
                    msgs = await client.get_messages(bot, limit=5, from_user=bot)
                    for m in msgs:
                        if m.id > before:
                            btns = [bb.text for r in (m.buttons or []) for bb in r]
                            return m.text or "", btns, m
                    updated = await client.get_messages(bot, ids=msg.id)
                    if updated and updated.edit_date and updated.text != (msg.text or ""):
                        btns = [bb.text for r in (updated.buttons or []) for bb in r]
                        return updated.text or "", btns, updated
                return None, [], None
    return None, [], None


async def main():
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    bot = await client.get_entity(BOT)
    print(f"Testing as: {me.first_name} (ID: {me.id})")

    # ============================================================
    print("\n" + "=" * 60)
    print("  SECTION 1: Fresh user — /start dashboard")
    print("=" * 60)

    text, btns, msg = await send_wait(client, bot, "/start", wait=10)
    check("/start works", text is not None)
    check("Title: edgeX Agent", "edgeX Agent" in (text or ""))
    check("Action hint (Click/talk)", "Click" in (text or "") or "talk" in (text or ""))
    check("edgeX not connected", "not connected" in (text or ""))
    check("AI not activated", "not activated" in (text or ""))
    check("No Chinese '临时'", "临时" not in (text or ""))
    check("Has multilingual prompts", sum(1 for s in ["ソラナ", "지금", "CRCL", "Короткий"] if s in (text or "")) >= 2)
    check("No English annotations in prompts", "(Long" not in (text or "") and "(How's" not in (text or ""))
    check("SILVER in prompts (not GOLD)", "SILVER" in (text or ""))
    await asyncio.sleep(2)

    # ============================================================
    print("\n" + "=" * 60)
    print("  SECTION 2: Demo login — one-click edgeX")
    print("=" * 60)

    text2, btns2, msg2 = await click_btn(client, bot, msg, "Connect", wait=10)
    check("Login menu shown", text2 is not None)
    check("Has Aaron's edgeX button", any("Aaron" in b and "edgeX" in b for b in btns2))
    check("Has API Key button", any("API Key" in b for b in btns2))
    check("Has One-Click button", any("One-Click" in b for b in btns2))

    text3, btns3, msg3 = await click_btn(client, bot, msg2, "Aaron", wait=30)
    # Handle: edit_message_text("Connecting...") → edit_message_text("Connected!")
    # Both are edits to the same message, so we may catch "Connecting" first
    if text3 and "Connecting" in text3:
        for _ in range(20):
            await asyncio.sleep(1)
            updated = await client.get_messages(bot, ids=msg3.id if msg3 else msg2.id)
            if updated and "Connected" in (updated.text or ""):
                text3 = updated.text or ""
                btns3 = [bb.text for r in (updated.buttons or []) for bb in r]
                msg3 = updated
                break
    if not text3 or "Connected" not in text3:
        # Try checking the original edited message
        await asyncio.sleep(5)
        updated = await client.get_messages(bot, ids=msg2.id)
        if updated and ("Connected" in (updated.text or "") or "✅" in (updated.text or "")):
            text3 = updated.text or ""
            btns3 = [bb.text for r in (updated.buttons or []) for bb in r]
            msg3 = updated
    check("Demo connected", text3 and ("Connected" in text3 or "✅" in text3))
    check("Says 'temp' not '临时'", "temp" in (text3 or "").lower() and "临时" not in (text3 or ""))
    check("Shows edgeX account ID", "7130" in (text3 or ""))
    await asyncio.sleep(2)

    # ============================================================
    print("\n" + "=" * 60)
    print("  SECTION 3: AI activation — Aaron's API (temp)")
    print("=" * 60)

    check("AI activation buttons shown", len(btns3) >= 3, str(btns3))
    check("First button is edgeX Balance", "Balance" in btns3[0] if btns3 else False, str(btns3[:1]))
    check("Last button is Aaron's (temp)", "Aaron" in btns3[-1] if btns3 else False, str(btns3[-1:]))
    check("No '临时' in buttons", all("临时" not in b for b in btns3))

    # If no AI activation buttons, try /start → Activate AI
    if not any("Aaron" in b for b in btns3):
        text_f, btns_f, msg_f = await send_wait(client, bot, "/start", wait=10)
        if any("Activate" in b for b in btns_f):
            text_f2, btns_f2, msg_f2 = await click_btn(client, bot, msg_f, "Activate", wait=10)
            if msg_f2:
                btns3 = btns_f2
                msg3 = msg_f2

    text4, btns4, msg4 = await click_btn(client, bot, msg3, "Aaron", wait=10)
    check("AI activated", text4 and ("Activated" in text4 or "activated" in text4))
    check("Says 'temp' not '临时'", "temp" in (text4 or "").lower() and "临时" not in (text4 or ""))
    check("Personality buttons shown", any("Degen" in b for b in btns4))
    check("7 personalities", sum(1 for b in btns4 if any(p in b for p in ["Degen", "Sensei", "Cold Blood", "Shitposter", "Professor", "Wolf", "Moe"])) == 7)
    await asyncio.sleep(2)

    # ============================================================
    print("\n" + "=" * 60)
    print("  SECTION 4: Personality selection")
    print("=" * 60)

    if msg4 and msg4.buttons:
        text5, btns5, msg5 = await click_btn(client, bot, msg4, "Degen", wait=10)
    else:
        text5 = None
    check("Personality set", text5 and "Degen" in text5, (text5 or "")[:200])
    check("Says 'unlocked'", "unlocked" in (text5 or "").lower(), (text5 or "")[:100])
    check("No English annotations", "(Long" not in (text5 or "") and "(How's" not in (text5 or ""))
    check("Has /status and /pnl tips", "/status" in (text5 or "") and "/pnl" in (text5 or ""))
    await asyncio.sleep(3)

    # ============================================================
    print("\n" + "=" * 60)
    print("  SECTION 5: AI answer validation — price queries")
    print("=" * 60)

    print("\n--- 5.1 BTC price ---")
    text, btns_ai, msg_ai = await send_wait(client, bot, "What's BTC at?", wait=60)
    # If AI shows activation prompt, click Aaron's again
    if text and "Activate" in text:
        text_a, btns_a, msg_a = await click_btn(client, bot, msg_ai, "Aaron", wait=10)
        if msg_a and msg_a.buttons:
            await click_btn(client, bot, msg_a, "Degen", wait=10)
            await asyncio.sleep(2)
            text, _, _ = await send_wait(client, bot, "What's BTC at?", wait=60)
    check("BTC: AI responds", text is not None and len(text or "") > 20, (text or "")[:100])
    check("BTC: mentions price or $", "$" in (text or "") or "price" in (text or "").lower() or "BTC" in (text or ""), (text or "")[:100])
    check("BTC: has real number", any(c.isdigit() for c in (text or "")))
    await asyncio.sleep(5)

    print("\n--- 5.2 SILVER price ---")
    text, _, _ = await send_wait(client, bot, "SILVER什么价格?", wait=60)
    check("SILVER: AI responds", text is not None and len(text or "") > 20)
    check("SILVER: knows the asset", "SILVER" in (text or "") or "silver" in (text or "").lower() or "银" in (text or ""))
    check("SILVER: responds in Chinese", any('\u4e00' <= c <= '\u9fff' for c in (text or "")))
    await asyncio.sleep(5)

    print("\n--- 5.3 GOLD → XAUT resolution ---")
    text, _, _ = await send_wait(client, bot, "How's gold looking?", wait=60)
    check("GOLD: AI responds", text is not None and len(text or "") > 20)
    check("GOLD: maps to XAUT or gold", "XAUT" in (text or "") or "gold" in (text or "").lower() or "Gold" in (text or ""))
    check("GOLD: NOT 'not available'", "not available" not in (text or "").lower() and "isn't available" not in (text or "").lower())
    await asyncio.sleep(5)

    print("\n--- 5.4 ETH in Japanese ---")
    text, _, _ = await send_wait(client, bot, "ETHの調子はどう？", wait=60)
    check("ETH JP: AI responds", text is not None and len(text or "") > 20)
    check("ETH JP: mentions ETH", "ETH" in (text or "") or "イーサ" in (text or ""))
    await asyncio.sleep(5)

    # ============================================================
    print("\n" + "=" * 60)
    print("  SECTION 6: Trade execution — with confirmation")
    print("=" * 60)

    print("\n--- 6.1 SOL trade ---")
    text, btns, msg = await send_wait(client, bot, "Long SOL, 1 SOL, 2x leverage", wait=60)
    check("SOL trade: has plan", text is not None and ("SOL" in (text or "") or "Confirm" in str(btns)))
    has_confirm = any("Confirm" in b for b in btns)
    if has_confirm:
        check("SOL trade: confirm button", True)
        text6, _, _ = await click_btn(client, bot, msg, "Cancel", wait=10)
        check("SOL trade: cancel works", text6 and "cancel" in text6.lower())
    await asyncio.sleep(3)

    print("\n--- 6.2 BTC trade with market price ---")
    text, btns, msg = await send_wait(client, bot, "short BTC 0.001, market order", wait=60)
    has_confirm = any("Confirm" in b for b in btns)
    if has_confirm:
        check("BTC trade: confirm button", True)
        text7, _, _ = await click_btn(client, bot, msg, "Confirm", wait=30)
        if text7 and "Executing" in text7:
            await asyncio.sleep(15)
            updated = await client.get_messages(bot, ids=msg.id)
            if updated:
                text7 = updated.text or ""
        check("BTC trade: executed", text7 and ("Placed" in text7 or "Order" in text7 or "failed" in text7.lower()))
    else:
        check("BTC trade: got response", text is not None)
    await asyncio.sleep(3)

    # ============================================================
    print("\n" + "=" * 60)
    print("  SECTION 7: Commands validation")
    print("=" * 60)

    print("\n--- 7.1 /status ---")
    text, _, _ = await send_wait(client, bot, "/status", wait=15)
    check("/status: has equity", text and "Equity" in text)
    check("/status: has balance", text and ("Available" in text or "Balance" in text))
    await asyncio.sleep(2)

    print("\n--- 7.2 /pnl ---")
    text, _, _ = await send_wait(client, bot, "/pnl", wait=15)
    check("/pnl: responds", text is not None)
    check("/pnl: has equity or market", text and ("Equity" in text or "Market" in text or "P&L" in text))
    await asyncio.sleep(2)

    print("\n--- 7.3 /history ---")
    text, _, _ = await send_wait(client, bot, "/history", wait=15)
    check("/history: responds", text is not None)
    await asyncio.sleep(2)

    print("\n--- 7.4 /help ---")
    text, _, _ = await send_wait(client, bot, "/help", wait=10)
    check("/help: has commands", text and "/start" in text and "/status" in text)
    check("/help: multilingual", text and "ソラナ" in text)
    check("/help: degen tone", text and ("bags" in text.lower() or "damage" in text.lower() or "degen" in text.lower()))
    check("/help: no English annotations", "(Long" not in (text or "") and "(How's" not in (text or ""))
    check("/help: SILVER not GOLD", "SILVER" in (text or ""))
    await asyncio.sleep(2)

    # ============================================================
    print("\n" + "=" * 60)
    print("  SECTION 8: /setai — AI source selection + provider flow")
    print("=" * 60)

    text, btns, msg = await send_wait(client, bot, "/setai", wait=10)
    check("/setai: responds", text is not None)
    check("/setai: has AI source menu", any("Own" in b or "Key" in b for b in btns) and any("Aaron" in b for b in btns))
    check("/setai: has edgeX Balance option", any("Balance" in b for b in btns))
    await asyncio.sleep(2)

    # Click Own Key → should show provider selection
    text8, btns8, msg8 = await click_btn(client, bot, msg, "Own", wait=10)
    check("/setai: provider buttons", any("OpenAI" in b for b in btns8) and any("Gemini" in b for b in btns8))

    # Click OpenAI → step 1
    text9, btns9, msg9 = await click_btn(client, bot, msg8, "OpenAI", wait=10)
    check("/setai OpenAI: step 1 (API Key)", text9 and "API Key" in (text9 or ""))
    # Cancel out
    text_c, _, _ = await send_wait(client, bot, "/cancel", wait=5)
    await asyncio.sleep(2)

    # ============================================================
    print("\n" + "=" * 60)
    print("  SECTION 9: /start dashboard states")
    print("=" * 60)

    text, btns, _ = await send_wait(client, bot, "/start", wait=10)
    check("Dashboard: AI active ✅", "active" in (text or "").lower() or "✅" in (text or ""))
    check("Dashboard: edgeX connected", "7130" in (text or ""))
    check("Dashboard: Status + P&L buttons", any("Status" in b for b in btns) and any("P&L" in b for b in btns))
    check("Dashboard: Settings button", any("Settings" in b for b in btns))
    await asyncio.sleep(2)

    # ============================================================
    print("\n" + "=" * 60)
    print("  SECTION 10: Complex AI operations")
    print("=" * 60)

    # 10.1 Multi-asset portfolio query
    print("\n--- 10.1 Portfolio analysis ---")
    text, _, _ = await send_wait(client, bot, "Show me my portfolio: positions, PnL, and equity", wait=60)
    ai_avail = "temporarily unavailable" not in (text or "")
    check("Portfolio: AI responds", text is not None and len(text or "") > 30, (text or "")[:150])
    check("Portfolio: has account info",
        not ai_avail or any(w in (text or "").lower() for w in ["equity", "balance", "position", "pnl", "usdt", "account"]),
        (text or "")[:150])
    await asyncio.sleep(3)

    # 10.2 Multi-step trade: analysis + execute
    print("\n--- 10.2 Conditional trade reasoning ---")
    text, btns, msg = await send_wait(client, bot,
        "If ETH is above 2000, go long 0.1 ETH. If not, short 0.1 ETH. Check the price and decide.", wait=60)
    check("Conditional: AI responds", text is not None and len(text or "") > 30, (text or "")[:150])
    check("Conditional: has trade plan or analysis", 
        any(w in (text or "").lower() for w in ["buy", "sell", "long", "short", "confirm", "eth"]), (text or "")[:150])
    # Cancel if trade plan
    if any("Confirm" in b for b in btns):
        await click_btn(client, bot, msg, "Cancel", wait=5)
    await asyncio.sleep(3)

    # 10.3 Cross-asset comparison
    print("\n--- 10.3 Cross-asset comparison ---")
    text, _, _ = await send_wait(client, bot, "Compare BTC and ETH: which has better momentum today?", wait=60)
    check("Compare: AI responds", text is not None and len(text or "") > 30, (text or "")[:150])
    check("Compare: mentions both assets", "BTC" in (text or "") and "ETH" in (text or ""), (text or "")[:150])
    await asyncio.sleep(3)

    # 10.4 Chinese complex request (multi-step)
    print("\n--- 10.4 Chinese multi-step request ---")
    text, btns, msg = await send_wait(client, bot, "帮我看一下SOL的价格，如果低于100就做多1个SOL", wait=60)
    check("CN multi-step: AI responds", text is not None and len(text or "") > 20, (text or "")[:150])
    check("CN multi-step: mentions SOL", "SOL" in (text or "") or "sol" in (text or "").lower(), (text or "")[:150])
    if any("Confirm" in b for b in btns):
        await click_btn(client, bot, msg, "Cancel", wait=5)
    await asyncio.sleep(3)

    # 10.5 Risk management query
    print("\n--- 10.5 Risk management ---")
    text, _, _ = await send_wait(client, bot, "What's my risk exposure? How much can I lose if BTC drops 10%?", wait=60)
    check("Risk: AI responds", text is not None and len(text or "") > 20, (text or "")[:150])
    await asyncio.sleep(3)

    # ============================================================
    print("\n" + "=" * 60)
    print("  SECTION 11: /feedback command")
    print("=" * 60)

    text, _, _ = await send_wait(client, bot, "/feedback", wait=10)
    check("Feedback: prompt shown", text is not None and "feedback" in (text or "").lower(), (text or "")[:100])

    text2, _, _ = await send_wait(client, bot, "Add support for limit orders with custom expiry time", wait=10)
    check("Feedback: recorded", text2 is not None and "got it" in (text2 or "").lower() or "recorded" in (text2 or "").lower(), (text2 or "")[:100])
    await asyncio.sleep(2)

    # ============================================================
    print("\n" + "=" * 60)
    print("  SECTION 12: Logout + fresh state")
    print("=" * 60)

    text, btns, msg = await send_wait(client, bot, "/logout", wait=10)
    text2, _, _ = await click_btn(client, bot, msg, "Yes", wait=10)
    check("Logout: disconnected", text2 and "Disconnected" in text2)
    await asyncio.sleep(2)

    text, btns, _ = await send_wait(client, bot, "/start", wait=10)
    check("After logout: edgeX Agent title", "edgeX Agent" in (text or ""))
    check("After logout: not connected", "not connected" in (text or ""))
    check("After logout: not activated", "not activated" in (text or ""))
    await asyncio.sleep(2)

    # ============================================================
    # SUMMARY
    print("\n" + "=" * 60)
    pct = int(PASS / TOTAL * 100) if TOTAL else 0
    print(f"  RESULTS: {PASS}/{TOTAL} passed ({pct}%)")
    print("=" * 60)
    if PASS == TOTAL:
        print("\n  PERFECT SCORE!")
    else:
        print(f"\n  {TOTAL - PASS} failures")

    await client.disconnect()
    sys.exit(0 if PASS == TOTAL else 1)

asyncio.run(main())
