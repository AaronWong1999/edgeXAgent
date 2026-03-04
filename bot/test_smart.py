"""Smart test: AI-driven, randomized testing of @edgeXAgentBot.

Each run generates different messages, picks random paths, and intelligently
judges whether bot responses are correct. Covers the same verification points
as the static test but with human-like variation.

Run: TG_API_ID=xxx TG_API_HASH=xxx python3 test_smart.py
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


# ──────────────────────────────────────────
# Randomized input generators
# ──────────────────────────────────────────

PERSONAS = ["Degen", "Sensei", "Cold Blood", "Shitposter", "Professor", "Wolf", "Moe"]

BTC_QUERIES = [
    "What's BTC at right now?",
    "BTC price?",
    "how much is bitcoin",
    "比特币现在多少钱",
    "BTCの価格は？",
    "BTC 지금 얼마?",
    "Сколько стоит BTC?",
    "gimme that BTC price fam",
]

SILVER_QUERIES = [
    "白银现在什么价格？",
    "SILVER价格查一下",
    "银子多少钱一盎司",
    "how's silver doing?",
    "show me SILVER price",
    "SILVERの現在の価格は?",
]

GOLD_QUERIES = [
    "黄金多少钱",
    "GOLD price please",
    "what's gold trading at",
    "金子现在怎么样",
    "金の相場は？",
]

MULTI_LANG_QUERIES = [
    ("ETHどう思う？買い？", "ETH", "Japanese ETH query"),
    ("SOL 지금 사도 될까?", "SOL", "Korean SOL query"),
    ("DOGE到底能不能买", "DOGE", "Chinese DOGE query"),
    ("Стоит ли покупать ETH?", "ETH", "Russian ETH query"),
    ("Je devrais acheter BTC?", "BTC", "French BTC query"),
]

TRADE_REQUESTS = [
    "Long 1 SOL at market price",
    "买0.01个ETH吧",
    "short 0.001 BTC",
    "做多1个SOL",
    "I wanna ape into SOL, just 1",
    "帮我做空0.01个ETH",
]

PORTFOLIO_QUERIES = [
    "Show me my portfolio",
    "What positions do I have?",
    "我的持仓怎么样",
    "check my bags",
    "how's my account looking",
    "ポジションを見せて",
]

COMPLEX_QUERIES = [
    "Compare BTC and ETH: which has better momentum?",
    "If SOL is above 80, should I go long?",
    "What's the risk if BTC drops 10% from here?",
    "帮我分析一下现在应该做多还是做空",
    "给我看看哪个币种最有潜力",
    "Which is better right now, going long or short on ETH?",
]


def pick(choices):
    return random.choice(choices)


# ──────────────────────────────────────────
# Response validators (intelligent checks)
# ──────────────────────────────────────────

def has_number(text):
    return any(c.isdigit() for c in (text or ""))

def has_price_info(text):
    t = (text or "").lower()
    return has_number(text) and any(w in t for w in ["$", "price", "usd", "usdt", "价格", "价", "円", "달러"])

def is_about_asset(text, asset):
    t = (text or "").upper()
    aliases = {
        "BTC": ["BTC", "BITCOIN", "比特币"],
        "ETH": ["ETH", "ETHEREUM", "以太坊"],
        "SOL": ["SOL", "SOLANA", "索拉纳"],
        "DOGE": ["DOGE", "DOGECOIN", "狗狗币"],
        "GOLD": ["GOLD", "XAUT", "黄金", "金"],
        "SILVER": ["SILVER", "白银", "银"],
    }
    for alias in aliases.get(asset.upper(), [asset.upper()]):
        if alias in t:
            return True
    return False

def is_not_error(text):
    t = (text or "").lower()
    return "not available" not in t and "error" not in t and "temporarily unavailable" not in t

def has_trade_plan(text, btns):
    return any("Confirm" in b for b in btns) or any(w in (text or "").lower() for w in ["buy", "sell", "long", "short", "做多", "做空"])

def has_substantive_response(text, min_len=30):
    return text is not None and len(text or "") >= min_len


# ──────────────────────────────────────────
# Telegram helpers
# ──────────────────────────────────────────

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
    print(f"\n{'='*60}")
    print(f"  SMART TEST (run #{run_id})")
    print(f"  Random seed: {run_id}")
    print(f"{'='*60}")
    random.seed(run_id)

    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    bot = await client.get_entity(BOT)
    print(f"Testing as: {me.first_name} (ID: {me.id})\n")

    chosen_persona = pick(PERSONAS)
    print(f"  [INFO] Random persona: {chosen_persona}")

    # ──────────────────────────────────────
    # PHASE 1: Fresh start
    # ──────────────────────────────────────
    print(f"\n{'='*60}")
    print("  PHASE 1: Fresh /start — Dashboard")
    print(f"{'='*60}")

    text, btns, msg = await send_wait(client, bot, "/start", wait=10)
    check("Dashboard loads", text is not None and "edgeX Agent" in (text or ""), (text or "")[:100])
    check("Shows edgeX status", "edgeX" in (text or ""))
    check("Shows AI status", "AI" in (text or ""))
    check("No 临时 anywhere", "临时" not in (text or ""))
    check("No brain emoji", "\U0001f9e0" not in (text or ""))
    check("Has action buttons", len(btns) >= 2, str(btns))
    await asyncio.sleep(2)

    # ──────────────────────────────────────
    # PHASE 2: Connect edgeX (demo one-click)
    # ──────────────────────────────────────
    print(f"\n{'='*60}")
    print("  PHASE 2: Connect edgeX")
    print(f"{'='*60}")

    text2, btns2, msg2 = await click_btn(client, bot, msg, "Connect", wait=10)
    check("Login menu appears", btns2 and len(btns2) >= 2, str(btns2))

    text3, btns3, msg3 = await click_btn(client, bot, msg2, "Aaron", wait=10)
    check("Demo connected", text3 and ("connected" in text3.lower() or "activate" in text3.lower()), (text3 or "")[:100])
    check("Says 'temp' not '临时'", "临时" not in (text3 or ""))
    await asyncio.sleep(2)

    # ──────────────────────────────────────
    # PHASE 3: Activate AI + pick random persona
    # ──────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  PHASE 3: Activate AI + Personality ({chosen_persona})")
    print(f"{'='*60}")

    # If we got AI activation buttons from demo connect, click Aaron's API
    if any("Aaron" in b and "API" in b for b in btns3):
        text4, btns4, msg4 = await click_btn(client, bot, msg3, "Aaron", wait=10)
    else:
        # Need to trigger AI activation
        text_t, btns_t, msg_t = await send_wait(client, bot, "hi", wait=15)
        if any("Aaron" in b for b in btns_t):
            text4, btns4, msg4 = await click_btn(client, bot, msg_t, "Aaron", wait=10)
        else:
            text4, btns4, msg4 = text_t, btns_t, msg_t

    check("AI activated", text4 and ("activated" in (text4 or "").lower() or "personality" in (text4 or "").lower()), (text4 or "")[:100])

    all_personas_found = sum(1 for p in PERSONAS if any(p in b for b in btns4))
    check(f"All 7 personas shown", all_personas_found == 7, f"found {all_personas_found}: {btns4}")
    check("No brain emoji in buttons", all("\U0001f9e0" not in b for b in btns4))

    text5, btns5, msg5 = await click_btn(client, bot, msg4, chosen_persona, wait=10)
    check(f"Persona '{chosen_persona}' set", text5 and ("unlocked" in (text5 or "").lower() or chosen_persona.lower() in (text5 or "").lower()), (text5 or "")[:100])
    check("No English annotations", "(Long" not in (text5 or "") and "(How's" not in (text5 or ""))
    await asyncio.sleep(3)

    # ──────────────────────────────────────
    # PHASE 4: Price queries (random language)
    # ──────────────────────────────────────
    print(f"\n{'='*60}")
    print("  PHASE 4: Price Queries (randomized)")
    print(f"{'='*60}")

    # BTC
    btc_q = pick(BTC_QUERIES)
    print(f"\n  >> \"{btc_q}\"")
    text, _, _ = await send_wait(client, bot, btc_q, wait=60)
    check("BTC: responds substantively", has_substantive_response(text), (text or "")[:100])
    check("BTC: has real price data", has_number(text), (text or "")[:100])
    check("BTC: mentions BTC", is_about_asset(text, "BTC"), (text or "")[:100])
    await asyncio.sleep(3)

    # SILVER
    silver_q = pick(SILVER_QUERIES)
    print(f"\n  >> \"{silver_q}\"")
    text, _, _ = await send_wait(client, bot, silver_q, wait=60)
    check("SILVER: responds", has_substantive_response(text, 20), (text or "")[:100])
    check("SILVER: knows the asset", is_about_asset(text, "SILVER"), (text or "")[:100])
    await asyncio.sleep(3)

    # GOLD → XAUT
    gold_q = pick(GOLD_QUERIES)
    print(f"\n  >> \"{gold_q}\"")
    text, _, _ = await send_wait(client, bot, gold_q, wait=60)
    check("GOLD: responds", has_substantive_response(text, 20), (text or "")[:100])
    check("GOLD: maps to XAUT (not unavailable)", is_not_error(text), (text or "")[:100])
    await asyncio.sleep(3)

    # Random multilingual
    ml_query, ml_asset, ml_label = pick(MULTI_LANG_QUERIES)
    print(f"\n  >> \"{ml_query}\" ({ml_label})")
    text, _, _ = await send_wait(client, bot, ml_query, wait=60)
    check(f"{ml_label}: responds", has_substantive_response(text, 20), (text or "")[:100])
    check(f"{ml_label}: about {ml_asset}", is_about_asset(text, ml_asset), (text or "")[:100])
    await asyncio.sleep(3)

    # ──────────────────────────────────────
    # PHASE 5: Trade flow (random asset)
    # ──────────────────────────────────────
    print(f"\n{'='*60}")
    print("  PHASE 5: Trade Flow (randomized)")
    print(f"{'='*60}")

    trade_req = pick(TRADE_REQUESTS)
    print(f"\n  >> \"{trade_req}\"")
    text, btns, msg = await send_wait(client, bot, trade_req, wait=60)
    has_plan = has_trade_plan(text, btns)
    check("Trade: AI generates plan or response", text is not None and len(text or "") > 15, (text or "")[:150])
    check("Trade: has Confirm/Cancel or trade info", has_plan or has_substantive_response(text), (text or "")[:100])

    # Cancel if confirm buttons shown
    if any("Confirm" in b for b in btns):
        text_c, _, _ = await click_btn(client, bot, msg, "Cancel", wait=10)
        check("Trade: cancel works", text_c and "cancel" in (text_c or "").lower(), (text_c or "")[:100])
    await asyncio.sleep(3)

    # ──────────────────────────────────────
    # PHASE 6: Complex AI queries
    # ──────────────────────────────────────
    print(f"\n{'='*60}")
    print("  PHASE 6: Complex AI Operations")
    print(f"{'='*60}")

    # Portfolio
    pf_q = pick(PORTFOLIO_QUERIES)
    print(f"\n  >> \"{pf_q}\"")
    text, _, _ = await send_wait(client, bot, pf_q, wait=60)
    avail = "temporarily unavailable" not in (text or "")
    check("Portfolio: responds", has_substantive_response(text, 15), (text or "")[:100])
    check("Portfolio: relevant content",
        not avail or any(w in (text or "").lower() for w in ["equity", "balance", "position", "usdt", "pnl", "持仓", "仓位"]),
        (text or "")[:150])
    await asyncio.sleep(3)

    # Complex analysis
    cx_q = pick(COMPLEX_QUERIES)
    print(f"\n  >> \"{cx_q}\"")
    text, btns, msg = await send_wait(client, bot, cx_q, wait=60)
    check("Complex: responds substantively", has_substantive_response(text, 30), (text or "")[:150])
    # Cancel if trade plan generated
    if any("Confirm" in b for b in btns):
        await click_btn(client, bot, msg, "Cancel", wait=5)
    await asyncio.sleep(3)

    # ──────────────────────────────────────
    # PHASE 7: Commands
    # ──────────────────────────────────────
    print(f"\n{'='*60}")
    print("  PHASE 7: Commands")
    print(f"{'='*60}")

    # /status
    text, _, _ = await send_wait(client, bot, "/status", wait=15)
    check("/status: responds", text is not None, (text or "")[:100])
    check("/status: has account data", has_number(text), (text or "")[:100])

    # /pnl
    text, _, _ = await send_wait(client, bot, "/pnl", wait=15)
    check("/pnl: responds", text is not None, (text or "")[:100])
    await asyncio.sleep(2)

    # /help
    text, _, _ = await send_wait(client, bot, "/help", wait=10)
    check("/help: has commands", text and "/start" in text and "/status" in text, (text or "")[:100])
    check("/help: multilingual examples", text and any(c in text for c in ["ソラナ", "지금", "涨的"]), (text or "")[:100])
    check("/help: SILVER not GOLD", "SILVER" in (text or ""))
    check("/help: no annotations", "(Long" not in (text or "") and "(How's" not in (text or ""))
    await asyncio.sleep(2)

    # ──────────────────────────────────────
    # PHASE 8: /setai source menu
    # ──────────────────────────────────────
    print(f"\n{'='*60}")
    print("  PHASE 8: /setai AI Source Menu")
    print(f"{'='*60}")

    text, btns, msg = await send_wait(client, bot, "/setai", wait=10)
    check("/setai: shows source menu", any("Aaron" in b for b in btns) and any("Own" in b or "Key" in b for b in btns), str(btns))
    check("/setai: has Balance option", any("Balance" in b for b in btns), str(btns))
    text_c, _, _ = await send_wait(client, bot, "/cancel", wait=5)
    await asyncio.sleep(2)

    # ──────────────────────────────────────
    # PHASE 9: /feedback
    # ──────────────────────────────────────
    print(f"\n{'='*60}")
    print("  PHASE 9: /feedback")
    print(f"{'='*60}")

    feedback_msgs = [
        "Please add support for trailing stop-loss orders",
        "I'd love to see a leaderboard of top traders",
        "希望可以加一个自动定投的功能",
        "The chart display could use some improvement",
        f"Test feedback from smart test run #{run_id}",
    ]
    text, _, _ = await send_wait(client, bot, "/feedback", wait=10)
    check("Feedback: shows prompt", "feedback" in (text or "").lower(), (text or "")[:100])

    fb_msg = pick(feedback_msgs)
    text2, _, _ = await send_wait(client, bot, fb_msg, wait=10)
    check("Feedback: recorded", text2 and ("got it" in (text2 or "").lower() or "recorded" in (text2 or "").lower()), (text2 or "")[:100])
    await asyncio.sleep(2)

    # ──────────────────────────────────────
    # PHASE 10: Logout + clean state
    # ──────────────────────────────────────
    print(f"\n{'='*60}")
    print("  PHASE 10: Logout")
    print(f"{'='*60}")

    text, btns, msg = await send_wait(client, bot, "/logout", wait=10)
    text2, _, _ = await click_btn(client, bot, msg, "Yes", wait=10)
    check("Logout: disconnected", text2 and "disconnected" in (text2 or "").lower(), (text2 or "")[:100])

    text3, btns3, _ = await send_wait(client, bot, "/start", wait=10)
    check("After logout: fresh state", "not connected" in (text3 or "").lower() or "not activated" in (text3 or "").lower(), (text3 or "")[:100])
    await asyncio.sleep(2)

    # ──────────────────────────────────────
    # SUMMARY
    # ──────────────────────────────────────
    print(f"\n{'='*60}")
    pct = int(PASS / TOTAL * 100) if TOTAL else 0
    print(f"  RESULTS: {PASS}/{TOTAL} passed ({pct}%)")
    print(f"  Persona tested: {chosen_persona}")
    print(f"  Run ID: #{run_id}")
    print(f"{'='*60}")

    if BUGS:
        print(f"\n  BUGS FOUND ({len(BUGS)}):")
        for name, detail in BUGS:
            print(f"    - {name}")
            if detail:
                print(f"      {detail}")
    elif PASS == TOTAL:
        print("\n  PERFECT SCORE!")

    await client.disconnect()
    sys.exit(0 if PASS == TOTAL else 1)

asyncio.run(main())
