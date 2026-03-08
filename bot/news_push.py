"""News push system — fetches news via MCP, analyzes with AI, pushes to subscribers.

Architecture:
  1. Poll MCP news sources on interval
  2. Deduplicate (hash-based)
  3. AI analyzes: relevant asset, bullish/bearish, suggested trade
  4. Push to subscribed users with trade action buttons

Uses Factory Droid API for AI analysis (shared cost, not user's API).
"""
import asyncio
import json
import logging
import hashlib
import time
import os
from typing import Optional

import httpx
import db
from config import CONTRACTS, EDGEX_CLI_PATH, DROID_CLI_PATH

logger = logging.getLogger(__name__)

# AI analysis via Factory droid exec
FACTORY_API_KEY = os.environ.get("FACTORY_API_KEY", "")

# Track last poll time per source
_last_poll = {}
# Per-user per-source push count tracking: {(user_id, source_id): [timestamp, ...]}
_user_push_times = {}
# Store bot instance for sending messages
_bot_instance = None
_news_loop_task = None


def set_bot(bot):
    """Set the Telegram bot instance for sending push notifications."""
    global _bot_instance
    _bot_instance = bot


def _can_push_to_user(user_id: int, source_id: str) -> bool:
    """Check if user hasn't exceeded their per-source max_per_hour.
    BWEnews has no rate limit — trusted source.
    """
    if source_id == "bwenews":
        return True
    max_per_hour = db.get_user_news_frequency(user_id, source_id)
    if max_per_hour <= 0:
        return False
    now = time.time()
    cutoff = now - 3600
    key = (user_id, source_id)
    times = _user_push_times.get(key, [])
    times = [t for t in times if t > cutoff]
    _user_push_times[key] = times
    return len(times) < max_per_hour


def _record_push(user_id: int, source_id: str):
    """Record a push event for rate limiting."""
    key = (user_id, source_id)
    _user_push_times.setdefault(key, []).append(time.time())


async def fetch_mcp_news(mcp_url: str, tool: str, limit: int = 5) -> list:
    """Fetch news from an MCP server endpoint."""
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": {"limit": limit}},
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(mcp_url, json=payload, headers={"Content-Type": "application/json"})
            resp.raise_for_status()
            data = resp.json()

        result = data.get("result", {})
        content = result.get("content", [])
        if not content:
            return []

        text = content[0].get("text", "")
        articles = json.loads(text)
        if isinstance(articles, list):
            return articles
        return []
    except Exception as e:
        logger.warning(f"MCP news fetch failed ({mcp_url}): {e}")
        return []


def _news_hash(article: dict) -> str:
    """Generate unique hash for deduplication."""
    key = (article.get("title", "") + article.get("url", "")).strip()
    return hashlib.md5(key.encode()).hexdigest()


def _is_relevant(article: dict) -> bool:
    """Quick filter: skip obvious spam/ads."""
    title = (article.get("title", "") or "").lower()
    skip_words = ["airdrop", "giveaway", "earn carnival", "referral", "bonus code"]
    return not any(w in title for w in skip_words)


# Known edgeX assets for matching
_ASSET_KEYWORDS = {}
def _build_asset_keywords():
    global _ASSET_KEYWORDS
    if _ASSET_KEYWORDS:
        return
    _ASSET_KEYWORDS = {
        "BTC": ["bitcoin", "btc", "비트코인"],
        "ETH": ["ethereum", "eth", "ether", "以太坊"],
        "SOL": ["solana", "sol"],
        "XRP": ["xrp", "ripple"],
        "DOGE": ["dogecoin", "doge", "狗狗币"],
        "BNB": ["bnb", "binance coin"],
        "ADA": ["cardano", "ada"],
        "AVAX": ["avalanche", "avax"],
        "DOT": ["polkadot", "dot"],
        "LINK": ["chainlink", "link"],
        "UNI": ["uniswap", "uni"],
        "AAVE": ["aave"],
        "SUI": ["sui"],
        "NEAR": ["near protocol", "near"],
        "ARB": ["arbitrum", "arb"],
        "OP": ["optimism"],
        "APT": ["aptos", "apt"],
        "PEPE": ["pepe"],
        "TRUMP": ["trump", "特朗普"],
        "TSLA": ["tesla", "tsla", "特斯拉"],
        "AAPL": ["apple", "aapl", "苹果"],
        "NVDA": ["nvidia", "nvda", "英伟达"],
        "GOOG": ["google", "goog", "alphabet"],
        "AMZN": ["amazon", "amzn"],
        "META": ["meta", "facebook"],
        "XAUT": ["gold", "黄金", "xaut", "金"],
        "SILVER": ["silver", "白银", "银"],
        "CRCL": ["circle", "crcl", "usdc issuer"],
        "CRV": ["curve", "crv"],
        "QQQ": ["nasdaq", "纳指", "fed ", "fomc", "interest rate", "加息", "降息",
                 "cpi ", "ppi ", "gdp ", "employment", "jobs report", "nonfarm",
                 "inflation", "recession", "tariff", "treasury", "bond yield",
                 "macro", "economy", "economic"],
    }

def _quick_asset_match(text: str) -> list:
    """Fast keyword-based asset matching from news text."""
    _build_asset_keywords()
    text_lower = text.lower()
    matched = []
    for asset, keywords in _ASSET_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                matched.append(asset)
                break
    return matched[:3]


# Min order sizes per asset (in asset units, from edgeX contract metadata)
MIN_ORDER_SIZES = {
    "BTC": 0.003, "ETH": 0.05, "SOL": 1, "BNB": 0.1, "LTC": 0.5,
    "LINK": 5, "AVAX": 2, "MATIC": 100, "XRP": 80, "DOGE": 300,
    "PEPE": 1000000, "AAVE": 0.2, "TRX": 200, "SUI": 20, "WIF": 30,
    "TIA": 5, "TON": 10, "LDO": 20, "ARB": 30, "OP": 20,
    "ORDI": 0.5, "JTO": 10, "JUP": 30, "UNI": 5, "ATOM": 5,
    "NEAR": 10, "SATS": 10000000, "ONDO": 30, "APE": 20, "CRV": 50,
    "AEVO": 30, "ENS": 1, "DOT": 10, "FET": 20, "WLD": 20,
    "ENA": 50, "DYDX": 20, "APT": 5, "ADA": 100, "SEI": 50,
    "MEME": 5000, "PNUT": 50, "MOVE": 50, "TRUMP": 2, "MELANIA": 20,
    "PENGU": 200, "VIRTUAL": 5, "KAITO": 10,
    "TSLA": 0.1, "AAPL": 0.1, "NVDA": 0.1, "GOOG": 0.1, "AMZN": 0.1, "META": 0.1,
    "XAUT": 0.003, "SILVER": 3, "CRCL": 3, "QQQ": 0.1,
}

# Default news trade presets
NEWS_TRADE_DEFAULTS = {
    "leverage": 3,
    "amounts": [50, 100, 200],
    "tp_pct": 8.0,
    "sl_pct": 4.0,
}


async def get_min_notional_usd(symbol: str, leverage: int = 3) -> float:
    """Calculate minimum notional USD for a symbol given leverage.
    Returns min USD needed as margin (notional/leverage) with 20% buffer.
    """
    min_size = MIN_ORDER_SIZES.get(symbol, 0)
    if min_size <= 0:
        return 0
    price = await _get_price_fast(symbol)
    if price <= 0:
        return 0
    min_notional = min_size * price  # total position value
    min_margin = min_notional / leverage  # margin needed
    return min_margin * 1.2  # 20% buffer


def adjust_amounts_for_min(amounts: list, min_usd: float) -> list:
    """Adjust button amounts so the smallest is >= min_usd.
    Returns new amounts list, all rounded to nice numbers.
    """
    if min_usd <= 0 or amounts[0] >= min_usd:
        return amounts

    # Round min_usd up to nearest nice number
    nice = [10, 15, 20, 25, 30, 40, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 750, 1000]
    base = next((n for n in nice if n >= min_usd), int(min_usd) + 10)
    # Generate 3 tiers: base, base*2, base*4
    return [base, base * 2, base * 4]


def get_user_news_trade_defaults(tg_user_id: int) -> dict:
    prefs = db.get_user_preferences(tg_user_id)
    d = prefs.get("news_trade", {})
    return {
        "leverage": d.get("leverage", NEWS_TRADE_DEFAULTS["leverage"]),
        "amounts": d.get("amounts", NEWS_TRADE_DEFAULTS["amounts"]),
        "tp_pct": d.get("tp_pct", NEWS_TRADE_DEFAULTS["tp_pct"]),
        "sl_pct": d.get("sl_pct", NEWS_TRADE_DEFAULTS["sl_pct"]),
    }


def save_user_news_trade_defaults(tg_user_id: int, key: str, value):
    prefs = db.get_user_preferences(tg_user_id)
    ntd = prefs.get("news_trade", {})
    ntd[key] = value
    prefs["news_trade"] = ntd
    db.save_user_preferences(tg_user_id, prefs)


async def _get_price_fast(symbol: str) -> float:
    """Get latest price for a symbol via edgex-cli (no auth needed)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            EDGEX_CLI_PATH, "--json", "market", "ticker", symbol,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        data = json.loads(stdout.decode().strip())
        if isinstance(data, list) and data:
            d = data[0]
            p = float(d.get("lastPrice", 0))
            if p <= 0:
                p = float(d.get("markPrice", 0))
            if p <= 0:
                p = float(d.get("indexPrice", 0))
            return p
        if isinstance(data, dict):
            p = float(data.get("lastPrice", 0))
            if p <= 0:
                p = float(data.get("markPrice", 0))
            return p
    except Exception:
        pass
    return 0.0


async def _is_tradable(symbol: str) -> bool:
    """Check if a symbol has real liquidity on edgeX (lastPrice > 0 or openInterest > 0)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            EDGEX_CLI_PATH, "--json", "market", "ticker", symbol,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        data = json.loads(stdout.decode().strip())
        d = data[0] if isinstance(data, list) and data else data if isinstance(data, dict) else {}
        last = float(d.get("lastPrice", 0))
        oi = float(d.get("openInterest", 0))
        return last > 0 or oi > 0
    except Exception:
        return False


NEWS_ANALYSIS_PROMPT = """You are an expert financial news analyst for a crypto/stock perpetual contract trading platform.

## Asset Resolution Rules (CRITICAL — MUST always pick a tradable asset)
1. **Macroeconomic news** (Fed, CPI, GDP, interest rates, tariffs, trade war, recession, employment, inflation, treasury yields) → asset = "QQQ" (Nasdaq ETF perpetual)
2. **Generic crypto/blockchain news** (crypto regulation, bitcoin ETF, crypto adoption, stablecoin, DeFi regulation) → asset = "BTC"
3. **Specific asset mentioned** (ETH, SOL, NVDA, TSLA, CRCL, etc.) → use that EXACT symbol
4. If BOTH macro + specific crypto mentioned, prioritize the specific asset
5. If news mentions a crypto exchange (OKX, Binance, Coinbase listing) → asset = "BTC" unless a specific altcoin is the subject
6. **Platform/infra news**: Polymarket runs on Polygon → asset = "MATIC". Ethereum ecosystem news → "ETH". Solana ecosystem → "SOL". Always find the closest tradable asset.
7. **Company fundraising/valuation news**: find the most related tradable asset. E.g. Polymarket $20B valuation → "MATIC" (Polygon); Coinbase earnings → "BTC"; Tesla AI news → "TSLA".
8. **NEVER return action=NONE**. Every news has some market impact — find the best tradable proxy.

## Sentiment Rules
- BULLISH: positive for the asset (adoption, ETF approval, investment, partnership, price surge, high valuation)
- BEARISH: negative (hack, ban, lawsuit, crash, sell-off, rate hike)
- Be decisive. Most breaking news has a clear direction.

## Confidence Rules
- HIGH: news directly about the asset or its core ecosystem
- MEDIUM: news indirectly related (e.g. platform valuation → underlying chain token)
- LOW: weak/tangential connection, but still the best available proxy

Available tradable assets (ONLY use these exact symbols): {assets}
Note: Use QQQ for macro/stock market news. Use XAUT for gold news. For Polygon/Polymarket news, use MATIC if available, otherwise BTC as crypto proxy.

Respond with ONLY valid JSON:
{{"asset": "MATIC", "sentiment": "BULLISH", "confidence": "MEDIUM", "action": "LONG", "reason": "Polymarket $20B valuation validates Polygon ecosystem demand"}}

"reason" = one short sentence explaining WHY this asset is affected and in which direction. This will be shown to users.
action = "LONG" if BULLISH, "SHORT" if BEARISH.

News:
Title: {title}
Body: {body}
Categories: {categories}
"""


async def analyze_news_with_ai(article: dict) -> Optional[dict]:
    """Use Factory Droid API to analyze a news article."""
    title = article.get("title", "")
    body = article.get("body", "") or ""
    categories = article.get("categories", "")

    # Quick pre-filter: skip if no asset can be matched at all
    full_text = f"{title} {body} {categories}"
    quick_assets = _quick_asset_match(full_text)
    if not quick_assets and "crypto" not in categories.lower():
        return None

    assets_str = ", ".join(sorted(CONTRACTS.keys()))
    prompt = NEWS_ANALYSIS_PROMPT.format(
        assets=assets_str, title=title, body=body[:500], categories=categories,
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            DROID_CLI_PATH, "exec",
            "-m", "claude-sonnet-4-5-20250929",
            "--output-format", "json",
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={
                "PATH": "/home/ubuntu/.local/bin:/usr/local/bin:/usr/bin:/bin",
                "HOME": "/home/ubuntu",
                "FACTORY_API_KEY": FACTORY_API_KEY,
            },
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45)
        output = stdout.decode().strip().lstrip('\x00\x01\x02\x03\x04\x05\x06\x07\x08')

        if proc.returncode != 0:
            logger.warning(f"AI news analysis failed: {stderr.decode()[:200]}")
            return None

        # Parse droid output
        try:
            wrapper = json.loads(output)
            result_text = wrapper.get("result", output)
        except json.JSONDecodeError:
            result_text = output

        # Extract JSON from result
        result_text = result_text.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1] if "\n" in result_text else result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()

        first = result_text.find("{")
        last = result_text.rfind("}")
        if first != -1 and last > first:
            result_text = result_text[first:last + 1]

        analysis = json.loads(result_text)
        if not isinstance(analysis, dict):
            return None

        # Validate asset exists in our contract list; try aliases if not
        asset = analysis.get("asset", "")
        ASSET_ALIASES = {
            "POL": "MATIC", "POLYGON": "MATIC", "GOLD": "XAUT", "XAU": "XAUT",
            "XAG": "SILVER", "BITCOIN": "BTC", "ETHEREUM": "ETH", "SOLANA": "SOL",
            "NASDAQ": "QQQ", "SPY": "QQQ", "SP500": "QQQ", "S&P": "QQQ",
        }
        if asset and asset not in CONTRACTS:
            asset = ASSET_ALIASES.get(asset.upper(), asset)
            analysis["asset"] = asset
        if not asset or asset not in CONTRACTS:
            return None

        # Check if asset actually has liquidity on edgeX
        if not await _is_tradable(asset):
            logger.info(f"Asset {asset} not tradable (no liquidity), falling back to BTC")
            original_asset = asset
            analysis["asset"] = "BTC"
            # Adjust reason to mention the fallback
            reason = analysis.get("reason", "")
            if reason and original_asset not in ("BTC",):
                analysis["reason"] = reason + f" (trading BTC as proxy — {original_asset} has no liquidity)"
            analysis["confidence"] = "MEDIUM"

        # Ensure action is always LONG or SHORT (never NONE)
        if analysis.get("action") not in ("LONG", "SHORT"):
            analysis["action"] = "LONG"
            analysis["sentiment"] = analysis.get("sentiment", "BULLISH")

        return analysis

    except asyncio.TimeoutError:
        logger.warning("AI news analysis timed out")
        return None
    except Exception as e:
        logger.warning(f"AI news analysis error: {e}")
        return None


async def format_news_alert(article: dict, analysis: dict, tg_user_id: int) -> tuple:
    """Format news alert with 3-tier trade buttons based on user defaults.
    Returns (message_text, InlineKeyboardMarkup).
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    raw_title = article.get("title", "Untitled").replace("**", "").replace("__", "").strip()
    title = raw_title
    for ch in ('_', '*', '[', ']', '`'):
        title = title.replace(ch, '\\' + ch)
    url = article.get("url", "")
    asset = analysis.get("asset", "?")
    sentiment = analysis.get("sentiment", "?")
    action = analysis.get("action", "NONE")
    confidence = analysis.get("confidence", "MEDIUM")

    # Get user defaults
    defaults = get_user_news_trade_defaults(tg_user_id)
    leverage = defaults["leverage"]
    amounts = list(defaults["amounts"])
    tp_pct = defaults["tp_pct"]
    sl_pct = defaults["sl_pct"]

    # Fetch real-time price
    price = await _get_price_fast(asset)

    # Adjust amounts for min order size
    min_usd = await get_min_notional_usd(asset, leverage)
    if min_usd > 0:
        amounts = adjust_amounts_for_min(amounts, min_usd)

    # Calculate TP/SL from price
    if price > 0:
        if action == "LONG":
            tp = round(price * (1 + tp_pct / 100), _price_decimals(price))
            sl = round(price * (1 - sl_pct / 100), _price_decimals(price))
        else:
            tp = round(price * (1 - tp_pct / 100), _price_decimals(price))
            sl = round(price * (1 + sl_pct / 100), _price_decimals(price))
        price_str = _format_price(price)
        tp_str = _format_price(tp)
        sl_str = _format_price(sl)
    else:
        tp_str = "?"
        sl_str = "?"
        price_str = "?"

    side_word = "LONG" if action == "LONG" else "SHORT"
    side_emoji = "\u2b06\ufe0f" if action == "LONG" else "\u2b07\ufe0f"
    sent_emoji = "\U0001f7e2" if sentiment == "BULLISH" else "\U0001f534"

    reason = analysis.get("reason", "")
    for ch in ('_', '*', '[', ']', '`'):
        reason = reason.replace(ch, '\\' + ch)

    msg = (
        f"*{title}*\n\n"
        f"{sent_emoji} {reason}"
    )
    if url:
        msg += f"\n[Source]({url})"

    buttons = []
    if action in ("LONG", "SHORT"):
        side = "BUY" if action == "LONG" else "SELL"
        cb_asset = asset[:10]
        for amt in amounts:
            label = f"{side_emoji} {side_word} {asset} ${amt} {leverage}x | TP {tp_str} SL {sl_str}"
            buttons.append([InlineKeyboardButton(label,
                callback_data=f"nt_{cb_asset}_{side}_{leverage}_{amt}")])

    buttons.append([
        InlineKeyboardButton("\U0001f1e8\U0001f1f3", callback_data="tl_zh"),
        InlineKeyboardButton("\U0001f1ef\U0001f1f5", callback_data="tl_ja"),
        InlineKeyboardButton("\U0001f1f0\U0001f1f7", callback_data="tl_ko"),
        InlineKeyboardButton("\U0001f1f7\U0001f1fa", callback_data="tl_ru"),
    ])

    return msg, InlineKeyboardMarkup(buttons)


def _price_decimals(price: float) -> int:
    if price >= 1000: return 1
    if price >= 10: return 2
    if price >= 1: return 3
    if price >= 0.01: return 5
    return 6


def _format_price(price: float) -> str:
    if price >= 1000:
        return f"{price:,.1f}"
    if price >= 1:
        return f"{price:.2f}"
    return f"{price:.5f}"


async def poll_and_push():
    """Main poll loop: fetch news, analyze, push to subscribers."""
    if not _bot_instance:
        logger.warning("News push: bot not set, skipping")
        return

    sources = db.get_news_sources(enabled_only=True)
    for source in sources:
        source_id = source["id"]
        interval = source.get("poll_interval_sec", 10)
        now = time.time()

        # Check poll interval
        last = _last_poll.get(source_id, 0)
        if now - last < interval:
            continue
        _last_poll[source_id] = now

        # Fetch news
        articles = await fetch_mcp_news(source["mcp_url"], source["mcp_tool"], limit=5)
        if not articles:
            continue

        # Get subscribers
        subscribers = db.get_subscribed_users(source_id)
        if not subscribers:
            continue

        # Process each article
        for article in articles:
            if not _is_relevant(article):
                continue

            nhash = _news_hash(article)

            # Check if already analyzed and pushed (to any user)
            # We analyze once, push to all
            analysis = None
            analysis_json = None

            for user_id in subscribers:
                if db.is_news_delivered(nhash, user_id):
                    continue
                if not _can_push_to_user(user_id, source_id):
                    continue

                # Analyze only once (lazy)
                if analysis is None:
                    analysis = await analyze_news_with_ai(article)
                    if analysis is None:
                        # Mark as delivered (skip) for all users
                        for uid in subscribers:
                            db.mark_news_delivered(nhash, uid, article.get("title", ""), source_id, "")
                        break
                    analysis_json = json.dumps(analysis)

                # Push to this user
                try:
                    msg, keyboard = await format_news_alert(article, analysis, user_id)
                    await _bot_instance.send_message(
                        chat_id=user_id,
                        text=msg,
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                        disable_web_page_preview=True,
                        disable_notification=True,  # silent push — don't interrupt active conversation
                    )
                    db.mark_news_delivered(nhash, user_id, article.get("title", ""), source_id, analysis_json)
                    _record_push(user_id, source_id)
                    logger.info(f"News pushed to {user_id}: {article.get('title', '')[:60]}")
                except Exception as e:
                    logger.warning(f"Failed to push news to {user_id}: {e}")
                    db.mark_news_delivered(nhash, user_id, article.get("title", ""), source_id, analysis_json or "")

            # Rate limit: don't spam AI too fast
            await asyncio.sleep(2)

    # Periodic cleanup
    if int(time.time()) % 3600 < 130:
        db.cleanup_old_news(days=7)


async def news_loop():
    """Background loop that polls news sources periodically."""
    logger.info("News push loop started")
    while True:
        try:
            await poll_and_push()
        except Exception as e:
            logger.error(f"News loop error: {e}")
        await asyncio.sleep(10)  # Check every 10 seconds for fast news delivery


def start_news_loop(bot):
    """Start the news push background loop. Call this from bot startup."""
    global _news_loop_task
    set_bot(bot)
    _news_loop_task = asyncio.ensure_future(news_loop())
    return _news_loop_task


def stop_news_loop():
    """Stop the news push loop."""
    global _news_loop_task
    if _news_loop_task:
        _news_loop_task.cancel()
        _news_loop_task = None
