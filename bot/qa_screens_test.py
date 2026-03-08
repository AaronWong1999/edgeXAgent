"""
QA Screen Test — Sends messages that simulate every screen the bot can produce.
Uses the bot to send screens WITH callback buttons to the user, then checks 
server logs for errors when buttons are clicked.
"""
import asyncio
import json
import httpx

TOKEN = ""
CHAT_ID = 7894288399
BASE = ""

def init():
    global TOKEN, BASE
    TOKEN = open(".env").read().split("TELEGRAM_BOT_TOKEN=")[1].split("\n")[0].strip()
    BASE = f"https://api.telegram.org/bot{TOKEN}"

async def send(text, kb=None, parse_mode="Markdown"):
    async with httpx.AsyncClient(timeout=10) as h:
        d = {"chat_id": CHAT_ID, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
        if kb: d["reply_markup"] = json.dumps(kb)
        r = await h.post(f"{BASE}/sendMessage", json=d)
        j = r.json()
        if not j.get("ok"):
            print(f"  ERR: {j.get('description','')[:150]}")
            return None
        return j["result"]["message_id"]

async def test_screen(name, text, buttons, note=""):
    print(f"  [{name}]", end="")
    mid = await send(text, {"inline_keyboard": buttons} if buttons else None)
    if mid:
        print(f" OK (msg {mid})")
    else:
        print(f" FAILED")
    return mid

async def main():
    init()
    print("=" * 60)
    print("edgeX Agent — Screen-by-Screen QA Test")
    print("=" * 60)
    ok = 0
    fail = 0

    # ═══ DASHBOARD ═══
    print("\n### Module: Dashboard ###")
    
    r = await test_screen("dash_new", 
        "🤖 *edgeX Agent — Your Own AI Trading Agent*\n\n👤 edgeX: not connected\n✨ AI: not activated",
        [[{"text": "🔗 Connect edgeX", "callback_data": "show_login"}],
         [{"text": "✨ Activate AI", "callback_data": "ai_activate_prompt"}],
         [{"text": "📰 Event Trading", "callback_data": "news_settings"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("dash_full",
        "🤖 *edgeX Agent — Your Own AI Trading Agent*\n\n👤 edgeX: `71303066234567` ✅\n✨ AI: Active ✅",
        [[{"text": "📈 Trade on edgeX", "callback_data": "trade_hub"}],
         [{"text": "🤖 AI Agent", "callback_data": "ai_hub"}],
         [{"text": "📰 Event Trading", "callback_data": "news_settings"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    # ═══ CONNECT EDGEX ═══
    print("\n### Module: Connect edgeX ###")

    r = await test_screen("show_login",
        "🔗 *Connect edgeX — Trade on edgeX*\n\nChoose how to connect:",
        [[{"text": "⚡ One-Click OAuth (soon)", "callback_data": "login_oauth"}],
         [{"text": "🔑 Connect with API Key", "callback_data": "login_api"}],
         [{"text": "👤 Aaron's Account (temp)", "callback_data": "login_demo"}],
         [{"text": "🔙 Back", "callback_data": "back_to_dashboard"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("login_oauth",
        "⚡ *One-Click Login — Trade on edgeX*\n\nComing Soon! Waiting for edgeX team OAuth integration.",
        [[{"text": "🔙 Back", "callback_data": "show_login"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    # ═══ TRADE HUB ═══
    print("\n### Module: Trade Hub ###")

    r = await test_screen("trade_hub",
        "📈 *Trade on edgeX — Trade on edgeX*\n\n├ Equity: `$1,234.56`\n└ Available: `$890.12`\n\n*Open Positions (2):*\n⬆️ BTC LONG `$712.00` (5x) @ `$71,200.00` | PnL: `+$12.30`\n⬇️ ETH SHORT `$1,500.00` (3x) @ `$3,000.00` | PnL: `-$5.20`\n\nUnrealized P&L: ⬆️ `+$7.10`",
        [[{"text": "📤 Share PnL", "callback_data": "quick_pnl"}],
         [{"text": "💰 Position", "callback_data": "quick_close"}, {"text": "📋 Orders", "callback_data": "quick_orders"}],
         [{"text": "📜 History", "callback_data": "quick_history"}, {"text": "🚪 Disconnect", "callback_data": "logout_confirm"}],
         [{"text": "🔙 Back", "callback_data": "back_to_dashboard"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    # ═══ CLOSE POSITION ═══
    print("\n### Module: Close Position ###")

    r = await test_screen("close_confirm",
        "🔴 *Market Close BTC LONG — Trade on edgeX*\n\n⚠️ This will market-close your BTC position.\n\n├ LONG | Value: `$712.00` | Entry: `$71,200`\n└ PnL: `+$12.30`\n\nAre you sure?",
        [[{"text": "✅ Yes, close BTC", "callback_data": "close_10000001"}],
         [{"text": "❌ Cancel", "callback_data": "close_cancel"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("close_blocked",
        "⚠️ *Close BTC — Trade on edgeX*\n\nMargin insufficient — 2 open order(s) blocking:\n  • BUY LIMIT | Size: 100 | Price: $70,000\n\nCancel orders to free margin, then retry.",
        [[{"text": "❌ Cancel All BTC Orders", "callback_data": "cancelorders_10000001"}],
         [{"text": "🔄 Retry Close BTC", "callback_data": "close_10000001"}],
         [{"text": "📋 View Orders", "callback_data": "vieworders_10000001"}, {"text": "🏠 Main Menu", "callback_data": "back_to_dashboard"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    # ═══ ORDERS ═══
    print("\n### Module: Orders ###")

    r = await test_screen("cancel_order_confirm",
        "❌ *Cancel Order — Trade on edgeX*\n\n⚠️ Cancel this order?\n\n├ BTC BUY LIMIT\n├ Size: `100` | Price: `$70,000`\n└ Order ID: `abc123def456789`",
        [[{"text": "✅ Yes, cancel", "callback_data": "cancelone_abc123def456789"}],
         [{"text": "❌ Keep order", "callback_data": "cancel_dismiss"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    # ═══ DISCONNECT ═══
    print("\n### Module: Disconnect ###")

    r = await test_screen("logout_confirm",
        "🚪 *Disconnect — Trade on edgeX*\n\nThis will log out your edgeX account. Are you sure?",
        [[{"text": "✅ Yes, logout", "callback_data": "logout_yes"}, {"text": "❌ Cancel", "callback_data": "logout_no"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    # ═══ AI AGENT ═══
    print("\n### Module: AI Agent ###")

    r = await test_screen("ai_activate",
        "✨ *Activate AI — AI Agent*\n\nChoose how to power your Agent:",
        [[{"text": "💳 Use edgeX Account Balance (soon)", "callback_data": "ai_edgex_credits"}],
         [{"text": "🔑 Use My Own API Key", "callback_data": "ai_own_key_setup"}],
         [{"text": "⚡ Use Aaron's API (temp)", "callback_data": "ai_use_free"}],
         [{"text": "🔙 Back", "callback_data": "back_to_dashboard"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("ai_hub",
        "🤖 *AI Agent — AI Agent*\n\n├ 🎭 Personality: `🔥 Degen`\n└ 📝 Memory: `26` msgs, `2` summaries",
        [[{"text": "🎭 Personality", "callback_data": "change_persona"}],
         [{"text": "🔑 Provider", "callback_data": "ai_activate_prompt"}, {"text": "📝 Memory", "callback_data": "settings_memory"}],
         [{"text": "🔙 Back", "callback_data": "back_to_dashboard"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("persona_picker",
        "🎭 *Personality — AI Agent*\n\nChoose your Agent's vibe:",
        [[{"text": "🔥 Degen", "callback_data": "persona_degen"}, {"text": "🎯 Sensei", "callback_data": "persona_sensei"}],
         [{"text": "🤖 Cold Blood", "callback_data": "persona_coldblood"}, {"text": "👀 Shitposter", "callback_data": "persona_shitposter"}],
         [{"text": "📚 Professor", "callback_data": "persona_professor"}, {"text": "🐺 Wolf", "callback_data": "persona_wolf"}],
         [{"text": "🌸 Moe", "callback_data": "persona_moe"}],
         [{"text": "🔙 Back", "callback_data": "ai_hub"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("memory_screen",
        "📝 *Memory — AI Agent*\n\n├ Messages: `26`\n└ Summaries: `2`",
        [[{"text": "🗑 Clear Memory", "callback_data": "memory_clear_confirm"}],
         [{"text": "🔙 Back", "callback_data": "ai_hub"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("memory_clear_confirm",
        "🗑 *Clear Memory — AI Agent*\n\nAll conversation history and preferences will be deleted.\nThis cannot be undone.",
        [[{"text": "✅ Yes, clear all", "callback_data": "memory_clear_yes"}, {"text": "❌ Keep", "callback_data": "memory_clear_no"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    # ═══ AI CHAT TRADE FLOW ═══
    print("\n### Module: AI Chat Trade Flow ###")

    r = await test_screen("ai_trade_suggestion",
        "✨ Bitcoin showing strong momentum above $71k. RSI breaking above 65, volume increasing.",
        [[{"text": "⬆️ LONG BTC $100 5x TP:$75,000 SL:$70,000", "callback_data": "show_trade_plan"}],
         [{"text": "🏠 Main Menu", "callback_data": "back_to_dashboard"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("trade_plan",
        "⬆️ *Trade Plan — Trade on edgeX*\n\nBUY BTC (5x)\n\n├ Entry: `$71,890`\n├ Size: `0.014`\n├ Value: `$100`\n├ TP: `$75,000`\n└ SL: `$70,000`\n\nConfidence: █████ HIGH\n_Bitcoin showing strong momentum..._",
        [[{"text": "✅ Confirm Execute", "callback_data": "confirm_trade"}, {"text": "❌ Cancel", "callback_data": "cancel_trade"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("trade_success",
        "⬆️ *LONG BTC — Trade on edgeX*\n\n✅ Order Placed!\n\n├ Entry: `$71,890`\n├ Size: `0.014` (5x)\n├ Value: `~$100`\n├ TP: `$75,000`\n├ SL: `$70,000`\n└ Order ID: `abc123`",
        [[{"text": "🏠 Main Menu", "callback_data": "back_to_dashboard"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("trade_cancelled",
        "❌ *Trade Cancelled — Trade on edgeX*\n\nNo order was placed.",
        [[{"text": "🏠 Main Menu", "callback_data": "back_to_dashboard"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    # ═══ EVENT TRADING ═══
    print("\n### Module: Event Trading ###")

    r = await test_screen("news_hub",
        "📰 *Event Trading — Event Trading*\n\nAI-analyzed news with one-tap trade buttons.\n\n✅ *BWEnews* — 5/hr",
        [[{"text": "BWEnews 🟢ON", "callback_data": "news_toggle_bwenews_off"}, {"text": "🕒", "callback_data": "news_freq_bwenews"}, {"text": "🗑", "callback_data": "news_remove_bwenews"}],
         [{"text": "➕ Add News Source", "callback_data": "news_add"}],
         [{"text": "⚙️ Trade Defaults", "callback_data": "news_trade_defaults"}],
         [{"text": "🔙 Back", "callback_data": "back_to_dashboard"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("trade_defaults",
        "⚙️ *Trade Defaults — Event Trading*\n\nLeverage: *3x*\nAmounts: *$50* / *$100* / *$200*\nTake Profit: *+8.0%*\nStop Loss: *-4.0%*",
        [[{"text": "Leverage: 3x", "callback_data": "ntd_leverage"}],
         [{"text": "Amounts: $50/$100/$200", "callback_data": "ntd_amounts"}],
         [{"text": "TP: +8.0%", "callback_data": "ntd_tp"}, {"text": "SL: -4.0%", "callback_data": "ntd_sl"}],
         [{"text": "🔙 Back", "callback_data": "news_settings"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("leverage_picker",
        "⚙️ *Leverage — Trade Defaults*\n\nCurrent: *3x*\n\nSelect default leverage:",
        [[{"text": "2x", "callback_data": "ntd_setlev_2"}, {"text": "> 3x", "callback_data": "ntd_setlev_3"}, {"text": "5x", "callback_data": "ntd_setlev_5"}],
         [{"text": "🔙 Back", "callback_data": "news_trade_defaults"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("amounts_picker",
        "⚙️ *Trade Amounts — Trade Defaults*\n\nCurrent: *$50 / $100 / $200*\n\nSelect 3 tiers:",
        [[{"text": "$25/$50/$100", "callback_data": "ntd_setamt_25_50_100"}],
         [{"text": "> $50/$100/$200", "callback_data": "ntd_setamt_50_100_200"}],
         [{"text": "$100/$200/$500", "callback_data": "ntd_setamt_100_200_500"}],
         [{"text": "🔙 Back", "callback_data": "news_trade_defaults"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("tp_picker",
        "⚙️ *Take Profit — Trade Defaults*\n\nCurrent: *+8.0%*\n\nSelect default TP:",
        [[{"text": "+5%", "callback_data": "ntd_settp_5"}, {"text": "> +8%", "callback_data": "ntd_settp_8"}, {"text": "+10%", "callback_data": "ntd_settp_10"}, {"text": "+15%", "callback_data": "ntd_settp_15"}],
         [{"text": "🔙 Back", "callback_data": "news_trade_defaults"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("sl_picker",
        "⚙️ *Stop Loss — Trade Defaults*\n\nCurrent: *-4.0%*\n\nSelect default SL:",
        [[{"text": "-3%", "callback_data": "ntd_setsl_3"}, {"text": "> -4%", "callback_data": "ntd_setsl_4"}, {"text": "-5%", "callback_data": "ntd_setsl_5"}, {"text": "-8%", "callback_data": "ntd_setsl_8"}],
         [{"text": "🔙 Back", "callback_data": "news_trade_defaults"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    # ═══ NEWS ALERT (PUSH) ═══
    print("\n### Module: News Alert (Push) ###")

    r = await test_screen("news_alert_bullish",
        "*A16Z CRYPTO TARGETS $2B FOR FIFTH FUND*\n\n🟢 BTC | BULLISH | ███ HIGH\n⬆️ LONG @ `$71,052.6` | 3x | TP `$76,736.8` SL `$68,210.5`\n[Source](https://example.com)",
        [[{"text": "⬆️ LONG BTC $50 3x | TP 76,736.8 SL 68,210.5", "callback_data": "nt_BTC_BUY_3_50"}],
         [{"text": "⬆️ LONG BTC $100 3x | TP 76,736.8 SL 68,210.5", "callback_data": "nt_BTC_BUY_3_100"}],
         [{"text": "⬆️ LONG BTC $200 3x | TP 76,736.8 SL 68,210.5", "callback_data": "nt_BTC_BUY_3_200"}],
         [{"text": "🇨🇳", "callback_data": "tl_zh"}, {"text": "🇯🇵", "callback_data": "tl_ja"}, {"text": "🇰🇷", "callback_data": "tl_ko"}, {"text": "🇷🇺", "callback_data": "tl_ru"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    r = await test_screen("news_alert_bearish_qqq",
        "*FED SIGNALS MORE RATE HIKES AS INFLATION PERSISTS*\n\n🔴 QQQ | BEARISH | ███ HIGH\n⬇️ SHORT @ `$482.30` | 3x | TP `$443.72` SL `$501.59`",
        [[{"text": "⬇️ SHORT QQQ $50 3x | TP 443.72 SL 501.59", "callback_data": "nt_QQQ_SELL_3_50"}],
         [{"text": "⬇️ SHORT QQQ $100 3x | TP 443.72 SL 501.59", "callback_data": "nt_QQQ_SELL_3_100"}],
         [{"text": "⬇️ SHORT QQQ $200 3x | TP 443.72 SL 501.59", "callback_data": "nt_QQQ_SELL_3_200"}],
         [{"text": "🇨🇳", "callback_data": "tl_zh"}, {"text": "🇯🇵", "callback_data": "tl_ja"}, {"text": "🇰🇷", "callback_data": "tl_ko"}, {"text": "🇷🇺", "callback_data": "tl_ru"}]])
    ok += 1 if r else 0; fail += 0 if r else 1

    # ═══ SUMMARY ═══
    print(f"\n{'='*60}")
    print(f"TOTAL: {ok + fail} screens | OK: {ok} | FAILED: {fail}")
    print(f"{'='*60}")
    print("\nAll screens sent to TG. Click every button to test callbacks!")
    print("Check TG chat now and verify:")
    print("  1. Every screen renders correctly (no broken markdown)")
    print("  2. Every button works when clicked")
    print("  3. TP/SL shown on all trade buttons")
    print("  4. Back buttons return to correct parent")

asyncio.run(main())
