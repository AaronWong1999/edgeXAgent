"""BWEnews MCP Server — standalone service that monitors @BWEnews TG channel
and serves news via MCP JSON-RPC protocol.

Architecture: polls recent messages from @BWEnews every 30s using Telethon
get_messages (reliable, no event listener dependency).

Run as: python3 bwenews_mcp.py
Listens on http://localhost:8788/mcp
"""
import asyncio
import json
import logging
import os
import re
import time
from collections import deque

from aiohttp import web
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("bwenews_mcp")

TG_API_ID = int(os.environ.get("TG_API_ID", "0"))
TG_API_HASH = os.environ.get("TG_API_HASH", "")
BWENEWS_CHANNEL = "BWEnews"
MCP_PORT = int(os.environ.get("BWENEWS_MCP_PORT", "8788"))

_articles = deque(maxlen=100)
_seen_ids = set()
_telethon_client = None
_channel_entity = None
_last_poll_time = 0
POLL_INTERVAL = 30


def _is_cjk_heavy(text: str) -> bool:
    if not text:
        return False
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or
              '\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' or
              '\uac00' <= c <= '\ud7a3')
    return cjk > len(text) * 0.3


def _extract_headline(text: str) -> str:
    if not text:
        return ""
    lines = text.strip().split("\n")
    headline = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("───") or line.startswith("___"):
            break
        if headline and _is_cjk_heavy(line):
            break
        if headline:
            headline += " " + line
        else:
            headline = line
    for prefix in ["BWENEWS:", "BWE NEWS:", "bwenews:"]:
        if headline.upper().startswith(prefix.upper()):
            headline = headline[len(prefix):].strip()
            break
    # Strip markdown bold markers that break TG Markdown parsing
    headline = headline.replace("**", "").replace("__", "")
    headline = headline.strip("*").strip()
    return headline


def _extract_url(text: str) -> str:
    urls = re.findall(r'https?://\S+', text or "")
    return urls[0] if urls else ""


async def _poll_channel():
    """Poll @BWEnews for recent messages and add to articles deque."""
    global _last_poll_time
    if not _telethon_client or not _channel_entity:
        return

    now = time.time()
    if now - _last_poll_time < POLL_INTERVAL:
        return
    _last_poll_time = now

    try:
        msgs = await _telethon_client.get_messages(_channel_entity, limit=10)
        new_count = 0
        for m in reversed(msgs):
            if m.id in _seen_ids:
                continue
            _seen_ids.add(m.id)

            text = m.text or m.message or ""
            if not text or len(text) < 10:
                continue

            headline = _extract_headline(text)
            if not headline or len(headline) < 15:
                continue

            url = _extract_url(text)
            post_time = m.date.timestamp() if m.date else time.time()

            article = {
                "title": headline,
                "url": url,
                "body": "",
                "source": "BWEnews",
                "categories": "crypto,finance,breaking",
                "published_at": post_time,
            }
            _articles.appendleft(article)
            new_count += 1
            logger.info(f"New article: {headline[:80]}")

        if new_count:
            logger.info(f"Polled {new_count} new articles from @BWEnews")
    except Exception as e:
        logger.error(f"Poll error: {e}")
        # Try to reconnect if session/connection error
        if "AuthKey" in str(e) or "connection" in str(e).lower() or "disconnect" in str(e).lower():
            logger.info("Attempting reconnect...")
            try:
                await _telethon_client.disconnect()
                await _telethon_client.connect()
                logger.info("Reconnected successfully")
            except Exception as re:
                logger.error(f"Reconnect failed: {re}")


async def mcp_handler(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    method = body.get("method", "")
    req_id = body.get("id", 1)
    params = body.get("params", {})

    if method == "tools/list":
        return web.json_response({
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": [{
                "name": "get_bwenews",
                "description": "Get latest breaking news from BWEnews (@BWEnews)",
                "inputSchema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 10}},
                },
            }]},
        })

    if method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})
        limit = args.get("limit", 10)

        if tool_name == "get_bwenews":
            await _poll_channel()
            articles = list(_articles)[:limit]
            return web.json_response({
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(articles)}]},
            })

        return web.json_response({
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
        })

    return web.json_response({
        "jsonrpc": "2.0", "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    })


async def health_handler(request):
    return web.json_response({
        "status": "ok",
        "articles": len(_articles),
        "channel": BWENEWS_CHANNEL,
    })


async def poll_loop():
    """Background loop: poll channel every POLL_INTERVAL seconds."""
    while True:
        try:
            await _poll_channel()
        except Exception as e:
            logger.error(f"Poll loop error: {e}")
        await asyncio.sleep(POLL_INTERVAL)


async def start_telethon(app):
    global _telethon_client, _channel_entity
    if not TG_API_ID or not TG_API_HASH:
        logger.error("TG_API_ID/TG_API_HASH not set — BWEnews will not work")
        return

    session_path = os.path.join(os.path.dirname(__file__), "bwenews_session")
    _telethon_client = TelegramClient(session_path, TG_API_ID, TG_API_HASH)
    await _telethon_client.start()

    _channel_entity = await _telethon_client.get_entity(BWENEWS_CHANNEL)
    logger.info(f"Connected to @{BWENEWS_CHANNEL} (id={_channel_entity.id})")

    # Initial load: fetch last 10 messages
    await _poll_channel()
    logger.info(f"Initial load: {len(_articles)} articles")

    # Start background poll loop
    asyncio.ensure_future(poll_loop())


async def on_cleanup(app):
    if _telethon_client:
        await _telethon_client.disconnect()


def main():
    app = web.Application()
    app.router.add_post("/mcp", mcp_handler)
    app.router.add_get("/health", health_handler)
    app.on_startup.append(start_telethon)
    app.on_cleanup.append(on_cleanup)

    logger.info(f"BWEnews MCP server starting on port {MCP_PORT}")
    web.run_app(app, host="127.0.0.1", port=MCP_PORT, print=None)


if __name__ == "__main__":
    main()
