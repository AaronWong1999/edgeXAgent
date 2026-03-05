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
from config import CONTRACTS

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
    """Check if user hasn't exceeded their per-source max_per_hour."""
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


NEWS_ANALYSIS_PROMPT = """You are a financial news analyst for a crypto/stock trading platform.
Analyze this news article and determine:
1. Which tradeable asset(s) it affects (use EXACT symbols: BTC, ETH, SOL, TSLA, NVDA, XAUT, etc.)
2. Whether it's BULLISH or BEARISH for that asset
3. A suggested trading action

Available assets on edgeX: {assets}

Respond with ONLY a JSON object:
{{
  "asset": "BTC",
  "sentiment": "BULLISH" or "BEARISH" or "NEUTRAL",
  "confidence": "HIGH" or "MEDIUM" or "LOW",
  "action": "LONG" or "SHORT" or "NONE",
  "leverage": "2"
}}

If the news is not clearly related to any tradeable asset or has no clear directional signal, set action to "NONE".

News article:
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
            "/home/ubuntu/.local/bin/droid", "exec",
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

        # Validate: skip NONE actions, NEUTRAL sentiment, LOW confidence
        if analysis.get("action") == "NONE" or analysis.get("sentiment") == "NEUTRAL":
            return None
        if analysis.get("confidence") == "LOW":
            return None
        if not analysis.get("asset") or analysis["asset"] not in CONTRACTS:
            return None

        return analysis

    except asyncio.TimeoutError:
        logger.warning("AI news analysis timed out")
        return None
    except Exception as e:
        logger.warning(f"AI news analysis error: {e}")
        return None


def format_news_alert(article: dict, analysis: dict) -> tuple:
    """Format news alert — clean BWEnews-style with translation links.
    Returns (message_text, InlineKeyboardMarkup).
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    title = article.get("title", "Untitled")
    url = article.get("url", "")
    source = article.get("source", "Crypto News")
    asset = analysis.get("asset", "?")
    sentiment = analysis.get("sentiment", "?")
    action = analysis.get("action", "NONE")
    confidence = analysis.get("confidence", "MEDIUM")
    leverage = analysis.get("leverage", "2")

    sent_emoji = "\U0001f7e2" if sentiment == "BULLISH" else "\U0001f534"
    action_emoji = "\U0001f4c8" if action == "LONG" else "\U0001f4c9"
    conf_bar = {"HIGH": "\u2588\u2588\u2588", "MEDIUM": "\u2588\u2588\u2591", "LOW": "\u2588\u2591\u2591"}.get(confidence, "\u2591\u2591\u2591")

    ts = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    msg = f"*{source}: {title}*\n\n{sent_emoji} {asset} | {sentiment} | {conf_bar} {confidence}\n\n{'─' * 16}\n{ts}"

    buttons = []
    if action in ("LONG", "SHORT"):
        side = "BUY" if action == "LONG" else "SELL"
        buttons.append([
            InlineKeyboardButton(f"{action_emoji} {action} {asset} $50",
                callback_data=f"news_trade_{asset}_{side}_{leverage}_50"),
            InlineKeyboardButton(f"{action_emoji} {action} {asset} $150",
                callback_data=f"news_trade_{asset}_{side}_{leverage}_150"),
        ])

    # Translation buttons — one row: 中 日 韩 俄
    buttons.append([
        InlineKeyboardButton("\U0001f1e8\U0001f1f3 \u4e2d", callback_data="tl_zh"),
        InlineKeyboardButton("\U0001f1ef\U0001f1f5 \u65e5", callback_data="tl_ja"),
        InlineKeyboardButton("\U0001f1f0\U0001f1f7 \u97e9", callback_data="tl_ko"),
        InlineKeyboardButton("\U0001f1f7\U0001f1fa \u0420\u0443", callback_data="tl_ru"),
    ])

    bottom = []
    if url:
        bottom.append(InlineKeyboardButton("\U0001f517 Source", url=url))
    bottom.append(InlineKeyboardButton("\U0001f515 Mute", callback_data="news_mute_free_crypto_news"))
    bottom.append(InlineKeyboardButton("\u274c Dismiss", callback_data="news_dismiss"))
    buttons.append(bottom)

    return msg, InlineKeyboardMarkup(buttons)


async def poll_and_push():
    """Main poll loop: fetch news, analyze, push to subscribers."""
    if not _bot_instance:
        logger.warning("News push: bot not set, skipping")
        return

    sources = db.get_news_sources(enabled_only=True)
    for source in sources:
        source_id = source["id"]
        interval = source.get("poll_interval_sec", 120)
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
                    msg, keyboard = format_news_alert(article, analysis)
                    await _bot_instance.send_message(
                        chat_id=user_id,
                        text=msg,
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                        disable_web_page_preview=True,
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
        await asyncio.sleep(60)  # Check every 60 seconds (source-level intervals enforced inside)


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
