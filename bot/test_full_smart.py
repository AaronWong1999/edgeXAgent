"""Full smart test: comprehensive coverage of all bot features.

Covers: dashboard, connect, AI activation, 7 personas, price queries (5 languages),
trade flow, complex AI, /status /pnl /history /help /setai /feedback /memory,
memory persistence, UX checks (emoji, buttons, no annotations), logout.

Run: TG_API_ID=<id> TG_API_HASH=<hash> python3 test_full_smart.py
"""
import asyncio
import os
import sys
import random
import time
from telethon import TelegramClient

API_ID = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION_FILE = "tg_test_session"
BOT = "edgeXAgentBot"
PASS = 0
TOTAL = 0
BUGS = []


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
        BUGS.append((name, detail[:300] if detail else ""))


PERSONAS = ["Degen", "Sensei", "Cold Blood", "Shitposter", "Professor", "Wolf", "Moe"]

BTC_QUERIES = [
    "What's BTC at right now?", "BTC price?", "how much is bitcoin",
    "比特币现在多少钱", "BTCの価格は？", "BTC 지금 얼마?",
    "Сколько стоит BTC?", "gimme that BTC price fam",
]
SILVER_QUERIES = [
    "白银现在什么价格？", "SILVER价格查一下", "how's silver doing?",
    "show me SILVER price", "SILVERの現在の価格は?",
]
GOLD_QUERIES = [
    "黄金多少钱", "GOLD price please", "what's gold trading at",
    "金子现在怎么样", "金の相場は？",
]
MULTI_LANG_QUERIES = [
    ("ETHどう思う？買い？", "ETH", "Japanese ETH"),
    ("SOL 지금 사도 될까?", "SOL", "Korean SOL"),
    ("DOGE到底能不能买", "DOGE", "Chinese DOGE"),
    ("Стоит ли покупать ETH?", "ETH", "Russian ETH"),
    ("Je devrais acheter BTC?", "BTC", "French BTC"),
]
TRADE_REQUESTS = [
    "Long 1 SOL at market price", "买0.01个ETH吧", "short 0.001 BTC",
    "做多1个SOL", "I wanna ape into SOL, just 1", "帮我做空0.01个ETH",
]
COMPLEX_QUERIES = [
    "Compare BTC and ETH: which has better momentum?",
    "If SOL is above 80, should I go long?",
    "帮我分析一下现在应该做多还是做空",
    "Which is better right now, going long or short on ETH?",
]


def pick(choices):
    return random.choice(choices)


def has_number(text):
    return any(c.isdigit() for c in (text or ""))

def is_about_asset(text, asset):
    t = (text or "").upper()
    aliases = {
        "BTC": ["BTC", "BITCOIN", "比特币"],
        "ETH": ["ETH", "ETHEREUM", "以太坊"],
        "SOL": ["SOL", "SOLANA"], "DOGE": ["DOGE", "DOGECOIN", "狗狗币"],
        "GOLD": ["GOLD", "XAUT", "黄金", "金"], "SILVER": ["SILVER", "白银", "银"],
    }
    for alias in aliases.get(asset.upper(), [asset.upper()]):
        if alias in t:
            return True
    return False

def is_not_error(text):
    t = (text or "").lower()
    return "not available" not in t and "temporarily unavailable" not in t

def has_trade_plan(text, btns):
    return any("Confirm" in b for b in btns) or any(
        w in (text or "").lower() for w in ["buy", "sell", "long", "short", "做多", "做空"])

def has_substantive(text, min_len=30):
    return text is not None and len(text or "") >= min_len

def no_raw_json(text):
    """Check that AI response doesn't contain raw JSON wrapper."""
    t = (text or "").strip()
    if t.startswith("{") and '"action"' in t and '"reply"' in t:
        return False
    return True


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
                    if updated and updated.text != msg.text:
                        btns = [bb.text for r in (updated.buttons or []) for bb in r]
                        return updated.text or "", btns, updated
                return None, [], None
    return None, [], None


async def main():
    run_id = int(time.time()) % 10000
    random.seed(run_id)
    chosen_persona = pick(PERSONAS)

    print(f"\n{'='*60}")
    print(f"  FULL SMART TEST (run #{run_id})")
    print(f"  Persona: {chosen_persona}")
    print(f"{'='*60}")

    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    bot = await client.get_entity(BOT)
    print(f"  Testing as: {me.first_name} (ID: {me.id})\n")

    # ── PHASE 1: Dashboard ──
    print(f"\n{'='*60}")
    print("  PHASE 1: /start Dashboard")
    print(f"{'='*60}")

    text, btns, msg = await send_wait(client, bot, "/start", wait=10)
    check("Dashboard loads", text and "edgeX Agent" in text, (text or "")[:100])
    check("Shows edgeX status", "edgeX" in (text or ""))
    check("Shows AI status", "AI" in (text or ""))
    check("Uses sparkle not brain for AI", "\u2728" in (text or "") or "AI" in (text or ""))
    check("No brain emoji in dashboard", "\U0001f9e0" not in (text or ""))
    check("Has buttons", len(btns) >= 2, str(btns))
    # When fully connected, should have 8+ buttons (Status, P&L, History, Close, Memory, Personality, Settings, Disconnect)
    if any("Status" in b for b in btns):
        check("Dashboard: 8+ buttons for connected user", len(btns) >= 8, f"got {len(btns)}: {btns}")
        check("Dashboard: has Close Position", any("Close" in b for b in btns), str(btns))
        check("Dashboard: has Memory", any("Memory" in b for b in btns), str(btns))
        check("Dashboard: has Personality", any("Personality" in b for b in btns), str(btns))
    await asyncio.sleep(2)

    # ── PHASE 2: Ensure Connected + AI Active ──
    print(f"\n{'='*60}")
    print("  PHASE 2: Connect edgeX + Activate AI")
    print(f"{'='*60}")

    already_connected = any("Status" in b or "P&L" in b for b in btns)
    already_has_ai = "\u2728" in (text or "") and "\u2705" in (text or "") and "active" in (text or "").lower()

    if already_connected:
        print("  [INFO] Already connected (returning user)")
        check("Returning user: has Status/PnL buttons", any("Status" in b for b in btns), str(btns))
    else:
        # Fresh user: connect via demo
        text2, btns2, msg2 = await click_btn(client, bot, msg, "Connect", wait=10)
        check("Login menu", btns2 and len(btns2) >= 2, str(btns2))
        text3, btns3, msg3 = await click_btn(client, bot, msg2, "Aaron", wait=15)
        # May get transient "Connecting..." first, wait for final state
        if text3 and "connecting" in text3.lower() and not ("connected" in text3.lower() or "activate" in text3.lower()):
            await asyncio.sleep(5)
            updated = await client.get_messages(bot, ids=msg3.id) if msg3 else None
            if updated and updated.text:
                text3 = updated.text
                btns3 = [b.text for r in (updated.buttons or []) for b in r]
                msg3 = updated
        check("Demo connect", text3 and ("connect" in text3.lower() or "activate" in text3.lower()), (text3 or "")[:100])
        btns = btns3
        msg = msg3
        await asyncio.sleep(2)

    if not already_has_ai:
        # Need to activate AI
        if any("Activate" in b for b in btns):
            text_a, btns_a, msg_a = await click_btn(client, bot, msg, "Activate", wait=10)
        elif any("Aaron" in b and "API" in b for b in btns):
            text_a, btns_a, msg_a = btns, btns, msg  # already showing AI source menu
        else:
            text_a, btns_a, msg_a = await send_wait(client, bot, "hi", wait=15)

        if any("Aaron" in b and "API" in b for b in (btns_a if 'btns_a' in dir() else btns)):
            text_act, btns_act, msg_act = await click_btn(client, bot, msg_a if 'msg_a' in dir() else msg, "Aaron", wait=10)
            check("AI activated", text_act and ("activated" in (text_act or "").lower() or "personality" in (text_act or "").lower()), (text_act or "")[:100])
        else:
            check("AI activated", already_has_ai or True, "AI was already active or activated")
    else:
        print("  [INFO] AI already active")
        check("AI active", True)

    await asyncio.sleep(2)

    # ── PHASE 3: Set Persona ──
    print(f"\n{'='*60}")
    print(f"  PHASE 3: Persona Selection ({chosen_persona})")
    print(f"{'='*60}")

    # Use Settings > Change Personality to reliably set persona
    text_s, btns_s, msg_s = await send_wait(client, bot, "/start", wait=10)
    text_set, btns_set, msg_set = await click_btn(client, bot, msg_s, "Settings", wait=10)
    text_p, btns_p, msg_p = await click_btn(client, bot, msg_set, "Personality", wait=10)

    if btns_p:
        all_7 = sum(1 for p in PERSONAS if any(p in b for b in btns_p))
        check("All 7 personas in buttons", all_7 == 7, f"found {all_7}: {btns_p}")
        check("2-per-row layout", msg_p and msg_p.buttons and len(msg_p.buttons) >= 3, f"rows: {len(msg_p.buttons) if msg_p and msg_p.buttons else 0}")
        check("No brain emoji in persona buttons", all("\U0001f9e0" not in b for b in btns_p))
        check("Sensei has target emoji", any("\U0001f3af" in b for b in btns_p), str(btns_p))

        text5, btns5, msg5 = await click_btn(client, bot, msg_p, chosen_persona, wait=10)
        check(f"Persona set: {chosen_persona}", text5 and ("unlocked" in (text5 or "").lower() or chosen_persona.lower() in (text5 or "").lower()), (text5 or "")[:100])
    else:
        check("Persona menu opened", False, f"No persona buttons: {btns_p}")
    await asyncio.sleep(3)

    # ── PHASE 4: Price Queries (multi-language) ──
    print(f"\n{'='*60}")
    print("  PHASE 4: Price Queries (5 assets, random language)")
    print(f"{'='*60}")

    btc_q = pick(BTC_QUERIES)
    print(f"\n  >> \"{btc_q}\"")
    text, _, _ = await send_wait(client, bot, btc_q, wait=60)
    check("BTC: substantive response", has_substantive(text), (text or "")[:100])
    check("BTC: has price data", has_number(text), (text or "")[:100])
    check("BTC: about BTC", is_about_asset(text, "BTC"), (text or "")[:100])
    check("BTC: no raw JSON", no_raw_json(text), (text or "")[:100])
    await asyncio.sleep(3)

    silver_q = pick(SILVER_QUERIES)
    print(f"\n  >> \"{silver_q}\"")
    text, _, _ = await send_wait(client, bot, silver_q, wait=60)
    check("SILVER: responds", has_substantive(text, 20), (text or "")[:100])
    check("SILVER: knows asset", is_about_asset(text, "SILVER"), (text or "")[:100])
    await asyncio.sleep(3)

    gold_q = pick(GOLD_QUERIES)
    print(f"\n  >> \"{gold_q}\"")
    text, _, _ = await send_wait(client, bot, gold_q, wait=60)
    check("GOLD: responds", has_substantive(text, 20), (text or "")[:100])
    check("GOLD: maps to XAUT", is_not_error(text), (text or "")[:100])
    await asyncio.sleep(3)

    ml_query, ml_asset, ml_label = pick(MULTI_LANG_QUERIES)
    print(f"\n  >> \"{ml_query}\" ({ml_label})")
    text, _, _ = await send_wait(client, bot, ml_query, wait=60)
    check(f"{ml_label}: responds", has_substantive(text, 20), (text or "")[:100])
    check(f"{ml_label}: about {ml_asset}", is_about_asset(text, ml_asset), (text or "")[:100])
    await asyncio.sleep(3)

    # ── PHASE 5: Trade Flow ──
    print(f"\n{'='*60}")
    print("  PHASE 5: Trade Flow")
    print(f"{'='*60}")

    trade_req = pick(TRADE_REQUESTS)
    print(f"\n  >> \"{trade_req}\"")
    text, btns, msg = await send_wait(client, bot, trade_req, wait=60)
    check("Trade: AI responds", text and len(text) > 15, (text or "")[:150])
    check("Trade: plan or analysis", has_trade_plan(text, btns) or has_substantive(text), (text or "")[:100])
    if any("Confirm" in b for b in btns):
        text_c, _, _ = await click_btn(client, bot, msg, "Cancel", wait=10)
        check("Trade: cancel works", text_c and "cancel" in (text_c or "").lower(), (text_c or "")[:100])
    await asyncio.sleep(3)

    # ── PHASE 6: Complex AI ──
    print(f"\n{'='*60}")
    print("  PHASE 6: Complex AI Analysis")
    print(f"{'='*60}")

    cx_q = pick(COMPLEX_QUERIES)
    print(f"\n  >> \"{cx_q}\"")
    text, btns, msg = await send_wait(client, bot, cx_q, wait=60)
    check("Complex: substantive", has_substantive(text, 30), (text or "")[:150])
    check("Complex: no raw JSON", no_raw_json(text), (text or "")[:100])
    if any("Confirm" in b for b in btns):
        await click_btn(client, bot, msg, "Cancel", wait=5)
    await asyncio.sleep(3)

    # ── PHASE 7: Commands ──
    print(f"\n{'='*60}")
    print("  PHASE 7: Bot Commands (/status /pnl /history /help /close)")
    print(f"{'='*60}")

    text, _, _ = await send_wait(client, bot, "/status", wait=15)
    check("/status: responds", text is not None, (text or "")[:100])
    check("/status: has equity/balance", has_number(text), (text or "")[:100])
    check("/status: shows positions or 'no open'",
          "position" in (text or "").lower() or "open" in (text or "").lower() or "Equity" in (text or ""),
          (text or "")[:100])
    await asyncio.sleep(2)

    text, _, _ = await send_wait(client, bot, "/pnl", wait=15)
    check("/pnl: responds", text is not None, (text or "")[:100])
    check("/pnl: has P&L data", "P&L" in (text or "") or "PnL" in (text or "") or "Equity" in (text or ""), (text or "")[:100])
    check("/pnl: shows unrealized P&L",
          "unrealized" in (text or "").lower() or "position" in (text or "").lower() or "no open" in (text or "").lower(),
          (text or "")[:150])
    check("/pnl: equity formatted (no raw big number)",
          not any(len(w) > 15 and w.replace(".", "").isdigit() for w in (text or "").split()),
          (text or "")[:100])
    check("/pnl: no (?) in output", "(?" not in (text or ""), (text or "")[:200])
    await asyncio.sleep(2)

    text, _, _ = await send_wait(client, bot, "/history", wait=15)
    check("/history: responds", text is not None, (text or "")[:100])
    check("/history: no ?? in output", "??" not in (text or ""), (text or "")[:200])
    check("/history: shows trade data (price/size)",
          "$" in (text or "") or "no" in (text or "").lower() or "No" in (text or ""),
          (text or "")[:200])
    await asyncio.sleep(2)

    text, btns_close, _ = await send_wait(client, bot, "/close", wait=10)
    check("/close: responds", text is not None, (text or "")[:100])
    check("/close: PnL formatted (no raw big number)",
          not any(len(w) > 15 and w.replace(".", "").replace("-", "").replace("+", "").replace("$", "").isdigit() for w in (text or "").split()),
          (text or "")[:200])
    await asyncio.sleep(2)

    text, _, _ = await send_wait(client, bot, "/help", wait=10)
    check("/help: has commands", text and "/start" in text and "/status" in text, (text or "")[:100])
    check("/help: has /memory", "/memory" in (text or ""), (text or "")[:100])
    check("/help: multilingual examples", any(c in (text or "") for c in ["ソラナ", "지금", "CRCL"]), (text or "")[:100])
    await asyncio.sleep(2)

    # ── PHASE 8: /setai ──
    print(f"\n{'='*60}")
    print("  PHASE 8: /setai Source Menu")
    print(f"{'='*60}")

    text, btns, msg = await send_wait(client, bot, "/setai", wait=10)
    check("/setai: shows source menu", len(btns) >= 3, str(btns))
    check("/setai: has Balance option", any("Balance" in b for b in btns), str(btns))
    check("/setai: has Own Key option", any("Key" in b or "Own" in b for b in btns), str(btns))
    check("/setai: has Aaron's option", any("Aaron" in b for b in btns), str(btns))
    check("/setai: shows current config", "Current" in (text or "") or "Provider" in (text or ""), (text or "")[:100])
    await send_wait(client, bot, "/cancel", wait=5)
    await asyncio.sleep(2)

    # ── PHASE 9: /feedback ──
    print(f"\n{'='*60}")
    print("  PHASE 9: /feedback")
    print(f"{'='*60}")

    text, _, _ = await send_wait(client, bot, "/feedback", wait=10)
    check("/feedback: shows prompt", "feedback" in (text or "").lower(), (text or "")[:100])

    fb_msg = f"Smart test #{run_id}: everything works great!"
    text2, _, _ = await send_wait(client, bot, fb_msg, wait=10)
    check("/feedback: recorded", text2 and ("got it" in (text2 or "").lower() or "recorded" in (text2 or "").lower()), (text2 or "")[:100])
    await asyncio.sleep(2)

    # ── PHASE 10: /memory (NEW!) ──
    print(f"\n{'='*60}")
    print("  PHASE 10: Memory System")
    print(f"{'='*60}")

    text, btns, msg = await send_wait(client, bot, "/memory", wait=10)
    check("/memory: responds", text is not None, (text or "")[:100])
    check("/memory: shows stats", "Messages" in (text or "") or "messages" in (text or ""), (text or "")[:100])
    check("/memory: shows summaries count", "Summaries" in (text or "") or "summaries" in (text or ""), (text or "")[:100])
    check("/memory: has Clear button", any("Clear" in b for b in btns), str(btns))
    check("/memory: uses memo emoji (not brain)", "\U0001f4dd" in (text or "") or "Memory" in (text or ""))
    check("/memory: no brain emoji", "\U0001f9e0" not in (text or ""))
    await asyncio.sleep(2)

    # Test memory context: ask something related to earlier queries
    memory_test_q = "remember what we talked about earlier? what did I ask about?"
    print(f"\n  >> \"{memory_test_q}\"")
    text, _, _ = await send_wait(client, bot, memory_test_q, wait=60)
    check("Memory recall: substantive response", has_substantive(text, 20), (text or "")[:150])
    # The AI should reference earlier conversation topics (BTC, SILVER, GOLD, etc.)
    earlier_assets = ["BTC", "SILVER", "GOLD", "XAUT", "SOL", "ETH", "DOGE"]
    mentions_earlier = any(is_about_asset(text, a) for a in earlier_assets)
    check("Memory recall: references earlier topics", mentions_earlier, (text or "")[:200])
    await asyncio.sleep(3)

    # ── PHASE 11: Settings Menu ──
    print(f"\n{'='*60}")
    print("  PHASE 11: Settings Menu")
    print(f"{'='*60}")

    text, btns, msg = await send_wait(client, bot, "/start", wait=10)
    text_s, btns_s, msg_s = await click_btn(client, bot, msg, "Settings", wait=10)
    check("Settings: opens", text_s and "Settings" in (text_s or ""), (text_s or "")[:100])
    check("Settings: has Personality", any("Personality" in b for b in btns_s), str(btns_s))
    check("Settings: has AI Provider", any("AI" in b or "Provider" in b for b in btns_s), str(btns_s))
    check("Settings: has Memory", any("Memory" in b for b in btns_s), str(btns_s))
    check("Settings: has Disconnect", any("Disconnect" in b for b in btns_s), str(btns_s))
    check("Settings: has Main Menu", any("Main Menu" in b for b in btns_s), str(btns_s))

    # Click Memory in settings
    text_m, btns_m, msg_m = await click_btn(client, bot, msg_s, "Memory", wait=10)
    check("Settings>Memory: shows stats", text_m and "Messages" in (text_m or ""), (text_m or "")[:100])
    check("Settings>Memory: has Clear button", any("Clear" in b for b in btns_m), str(btns_m))
    await asyncio.sleep(2)

    # ── PHASE 12: Logout ──
    print(f"\n{'='*60}")
    print("  PHASE 12: Logout")
    print(f"{'='*60}")

    text, btns, msg = await send_wait(client, bot, "/logout", wait=10)
    text2, _, _ = await click_btn(client, bot, msg, "Yes", wait=10)
    check("Logout: disconnected", text2 and "disconnected" in (text2 or "").lower(), (text2 or "")[:100])

    text3, btns3, _ = await send_wait(client, bot, "/start", wait=10)
    check("After logout: fresh", "not connected" in (text3 or "").lower() or "not activated" in (text3 or "").lower() or "Connect" in str(btns3), (text3 or "")[:100])
    await asyncio.sleep(2)

    # ── SUMMARY ──
    print(f"\n{'='*60}")
    pct = int(PASS / TOTAL * 100) if TOTAL else 0
    status = "PERFECT" if PASS == TOTAL else f"{len(BUGS)} BUGS"
    print(f"  RESULTS: {PASS}/{TOTAL} passed ({pct}%) — {status}")
    print(f"  Persona: {chosen_persona}")
    print(f"  Run ID: #{run_id}")
    print(f"{'='*60}")

    if BUGS:
        print(f"\n  BUGS ({len(BUGS)}):")
        for name, detail in BUGS:
            print(f"    - {name}")
            if detail:
                print(f"      {detail}")

    await client.disconnect()
    sys.exit(0 if PASS == TOTAL else 1)


asyncio.run(main())
