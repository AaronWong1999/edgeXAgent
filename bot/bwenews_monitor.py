"""BWEnews (@BWEnews) Telegram channel monitor.

Listens to the BWEnews channel for new posts, runs AI analysis,
and pushes formatted alerts to subscribers.

Requires Telethon for TG userbot (channel listening).
"""
import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Optional

from telethon import TelegramClient, events
import db
from config import CONTRACTS

logger = logging.getLogger(__name__)

FACTORY_API_KEY = os.environ.get("FACTORY_API_KEY", "")

TG_API_ID = int(os.environ.get("TG_API_ID", "0"))
TG_API_HASH = os.environ.get("TG_API_HASH", "")
BWENEWS_CHANNEL = "BWEnews"

_bot_instance = None
_telethon_client: Optional[TelegramClient] = None
_monitor_task = None

# Rate limiting per user per source
_user_push_times = {}

SOURCE_ID = "bwenews"
SOURCE_NAME = "BWEnews"

# Google Translate URL template
_TRANSLATE_URL = "https://translate.google.com/translate?sl=en&tl={lang}&u={url}"
_DEEPL_URL = "https://www.deepl.com/translator#en/{lang}/{text}"

# Language flags + codes for translation buttons
LANGUAGES = [
    ("\U0001f1e8\U0001f1f3", "zh", "\u4e2d"),
    ("\U0001f1ef\U0001f1f5", "ja", "\u65e5"),
    ("\U0001f1f0\U0001f1f7", "ko", "\u97e9"),
    ("\U0001f1f7\U0001f1fa", "ru", "\u0420\u0443"),
]


def set_bot(bot):
    global _bot_instance
    _bot_instance = bot


def _can_push_to_user(user_id: int) -> bool:
    """BWEnews has no rate limit — always push if subscribed."""
    sub = db.is_user_subscribed(user_id, SOURCE_ID)
    return sub


def _record_push(user_id: int):
    key = (user_id, SOURCE_ID)
    _user_push_times.setdefault(key, []).append(time.time())


def _news_hash(text: str) -> str:
    return hashlib.md5(text.strip()[:200].encode()).hexdigest()


# Asset keywords for quick matching
_ASSET_KEYWORDS = {
    "BTC": ["bitcoin", "btc", "$btc"],
    "ETH": ["ethereum", "eth", "$eth", "ether"],
    "SOL": ["solana", "sol", "$sol"],
    "XRP": ["xrp", "$xrp", "ripple"],
    "DOGE": ["dogecoin", "doge", "$doge"],
    "BNB": ["bnb", "$bnb", "binance coin"],
    "ADA": ["cardano", "ada", "$ada"],
    "AVAX": ["avalanche", "avax"],
    "DOT": ["polkadot", "dot"],
    "LINK": ["chainlink", "link", "$link"],
    "UNI": ["uniswap", "uni"],
    "AAVE": ["aave"],
    "SUI": ["sui", "$sui"],
    "NEAR": ["near protocol"],
    "ARB": ["arbitrum"],
    "OP": ["optimism"],
    "APT": ["aptos"],
    "PEPE": ["pepe", "$pepe"],
    "TRUMP": ["trump"],
    "TSLA": ["tesla", "tsla"],
    "AAPL": ["apple", "aapl"],
    "NVDA": ["nvidia", "nvda"],
    "GOOG": ["google", "alphabet", "goog"],
    "AMZN": ["amazon", "amzn"],
    "META": ["meta", "facebook", "zuckerberg"],
    "XAUT": ["gold", "xaut"],
    "SILVER": ["silver"],
    "CRCL": ["circle", "usdc"],
}


def _quick_asset_match(text: str) -> list:
    text_lower = text.lower()
    matched = []
    for asset, keywords in _ASSET_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                matched.append(asset)
                break
    return matched[:3]


NEWS_ANALYSIS_PROMPT = """You are a financial news analyst. Analyze this breaking news headline and determine:
1. Which tradeable asset it most affects (BTC, ETH, SOL, TSLA, NVDA, XAUT, etc.)
2. BULLISH or BEARISH sentiment
3. Suggested trade action

Available assets: {assets}

Respond with ONLY JSON:
{{
  "asset": "BTC",
  "sentiment": "BULLISH" or "BEARISH" or "NEUTRAL",
  "confidence": "HIGH" or "MEDIUM" or "LOW",
  "action": "LONG" or "SHORT" or "NONE",
  "leverage": "2"
}}

If not clearly related to any asset or no directional signal, set action to "NONE".

Headline: {headline}
"""


async def analyze_headline(headline: str) -> Optional[dict]:
    quick_assets = _quick_asset_match(headline)
    if not quick_assets:
        # Check for broad crypto/market keywords
        lower = headline.lower()
        broad = ["crypto", "bitcoin", "market", "fed ", "rate", "tariff",
                 "etf", "sec ", "regulation", "hack", "exchange"]
        if not any(w in lower for w in broad):
            return None

    assets_str = ", ".join(sorted(CONTRACTS.keys()))
    prompt = NEWS_ANALYSIS_PROMPT.format(assets=assets_str, headline=headline)

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
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode().strip().lstrip('\x00\x01\x02\x03\x04\x05\x06\x07\x08')

        if proc.returncode != 0:
            logger.warning(f"AI analysis failed: {stderr.decode()[:200]}")
            return None

        try:
            wrapper = json.loads(output)
            result_text = wrapper.get("result", output)
        except json.JSONDecodeError:
            result_text = output

        result_text = str(result_text).strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1] if "\n" in result_text else result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]

        first = result_text.find("{")
        last = result_text.rfind("}")
        if first != -1 and last > first:
            result_text = result_text[first:last + 1]

        analysis = json.loads(result_text)
        if analysis.get("action") == "NONE" or analysis.get("sentiment") == "NEUTRAL":
            return None
        if analysis.get("confidence") == "LOW":
            return None
        if not analysis.get("asset") or analysis["asset"] not in CONTRACTS:
            return None
        return analysis

    except Exception as e:
        logger.warning(f"AI headline analysis error: {e}")
        return None


def _extract_headline(text: str) -> str:
    """Extract the main English headline from a BWEnews post.
    BWEnews format: 'BWENEWS: headline\\n\\nChinese translation\\n───\\ntimestamp'
    Sometimes just a plain headline.
    """
    if not text:
        return ""
    lines = text.strip().split("\n")
    # First non-empty line is usually the headline
    headline = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("───") or line.startswith("___"):
            break
        # Skip lines that are purely CJK (Chinese translation)
        if headline and _is_cjk_heavy(line):
            break
        if headline:
            headline += " " + line
        else:
            headline = line
    # Remove "BWENEWS: " prefix if present
    for prefix in ["BWENEWS:", "BWE NEWS:", "bwenews:"]:
        if headline.upper().startswith(prefix.upper()):
            headline = headline[len(prefix):].strip()
            break
    return headline


def _is_cjk_heavy(text: str) -> bool:
    """Check if text is primarily CJK characters."""
    if not text:
        return False
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or
                    '\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' or
                    '\uac00' <= c <= '\ud7a3')
    return cjk_count > len(text) * 0.3


def _extract_url(text: str) -> str:
    """Extract URL from post text if any."""
    import re
    urls = re.findall(r'https?://\S+', text or "")
    return urls[0] if urls else ""


def format_bwenews_alert(headline: str, analysis: Optional[dict],
                         original_text: str, post_time: Optional[float] = None) -> tuple:
    """Format a BWEnews-style alert.
    Returns (message_text, InlineKeyboardMarkup).
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    url = _extract_url(original_text)
    ts = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(post_time)) if post_time else ""

    # Main message: bold headline + source + timestamp
    msg = f"*BWEnews: {headline}*"
    if ts:
        msg += f"\n\n{'─' * 16}\n{ts}"

    buttons = []

    # Trade buttons if analysis found actionable signal
    if analysis and analysis.get("action") in ("LONG", "SHORT"):
        asset = analysis["asset"]
        sentiment = analysis["sentiment"]
        confidence = analysis.get("confidence", "MEDIUM")
        action = analysis["action"]
        leverage = analysis.get("leverage", "2")
        side = "BUY" if action == "LONG" else "SELL"

        sent_emoji = "\U0001f7e2" if sentiment == "BULLISH" else "\U0001f534"
        action_emoji = "\U0001f4c8" if action == "LONG" else "\U0001f4c9"
        conf_bar = {"HIGH": "\u2588\u2588\u2588", "MEDIUM": "\u2588\u2588\u2591", "LOW": "\u2588\u2591\u2591"}.get(confidence, "\u2591\u2591\u2591")

        msg += f"\n\n{sent_emoji} {asset} | {sentiment} | {conf_bar} {confidence}"

        # Truncate asset to stay within Telegram's 64-byte callback_data limit
        cb_asset = asset[:20]
        buttons.append([
            InlineKeyboardButton(
                f"{action_emoji} {action} {asset} $50",
                callback_data=f"news_trade_{cb_asset}_{side}_{leverage}_50"),
            InlineKeyboardButton(
                f"{action_emoji} {action} {asset} $150",
                callback_data=f"news_trade_{cb_asset}_{side}_{leverage}_150"),
        ])

    # Translation buttons — one row: 中 日 韩 俄
    buttons.append([
        InlineKeyboardButton(f"{flag} {label}", callback_data=f"tl_{lang_code}")
        for flag, lang_code, label in LANGUAGES
    ])

    # Source link + dismiss
    bottom = []
    if url:
        bottom.append(InlineKeyboardButton("\U0001f517 Source", url=url))
    bottom.append(InlineKeyboardButton("\U0001f515 Mute", callback_data=f"news_mute_{SOURCE_ID}"))
    bottom.append(InlineKeyboardButton("\u274c Dismiss", callback_data="news_dismiss"))
    buttons.append(bottom)

    return msg, InlineKeyboardMarkup(buttons)


async def _handle_new_post(event):
    """Handle a new post from @BWEnews channel."""
    if not _bot_instance:
        return

    text = event.message.text or event.message.message or ""
    if not text or len(text) < 10:
        return

    headline = _extract_headline(text)
    if not headline or len(headline) < 15:
        return

    nhash = _news_hash(headline)
    post_time = event.message.date.timestamp() if event.message.date else time.time()

    # Get subscribers
    subscribers = db.get_subscribed_users(SOURCE_ID)
    if not subscribers:
        logger.debug("BWEnews: no subscribers")
        return

    # Analyze headline
    analysis = await analyze_headline(headline)

    # Push to all subscribers
    for user_id in subscribers:
        if db.is_news_delivered(nhash, user_id):
            continue
        if not _can_push_to_user(user_id):
            continue

        try:
            msg, keyboard = format_bwenews_alert(headline, analysis, text, post_time)
            await _bot_instance.send_message(
                chat_id=user_id,
                text=msg,
                parse_mode="Markdown",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            analysis_json = json.dumps(analysis) if analysis else ""
            db.mark_news_delivered(nhash, user_id, headline[:200], SOURCE_ID, analysis_json)
            _record_push(user_id)
            logger.info(f"BWEnews pushed to {user_id}: {headline[:60]}")
        except Exception as e:
            logger.warning(f"BWEnews push to {user_id} failed: {e}")
            db.mark_news_delivered(nhash, user_id, headline[:200], SOURCE_ID, "")


async def start_monitor(bot):
    """Start monitoring @BWEnews channel. Call from bot startup."""
    global _bot_instance, _telethon_client, _monitor_task
    _bot_instance = bot

    if not TG_API_ID or not TG_API_HASH:
        logger.warning("BWEnews monitor: TG_API_ID/TG_API_HASH not set, skipping")
        return

    # Ensure BWEnews source exists in DB
    db.add_news_source(
        source_id=SOURCE_ID,
        name=SOURCE_NAME,
        mcp_url="",
        mcp_tool="",
        category="crypto",
        is_default=True,
        poll_interval_sec=0,
    )

    try:
        session_path = os.path.join(os.path.dirname(__file__), "bwenews_session")
        _telethon_client = TelegramClient(session_path, TG_API_ID, TG_API_HASH)
        await _telethon_client.start()

        # Resolve channel
        channel = await _telethon_client.get_entity(BWENEWS_CHANNEL)
        logger.info(f"BWEnews monitor: connected to @{BWENEWS_CHANNEL} (id={channel.id})")

        @_telethon_client.on(events.NewMessage(chats=channel))
        async def handler(event):
            try:
                await _handle_new_post(event)
            except Exception as e:
                logger.error(f"BWEnews handler error: {e}")

        logger.info("BWEnews monitor started")
    except Exception as e:
        logger.error(f"BWEnews monitor failed to start: {e}")


async def stop_monitor():
    global _telethon_client
    if _telethon_client:
        await _telethon_client.disconnect()
        _telethon_client = None
