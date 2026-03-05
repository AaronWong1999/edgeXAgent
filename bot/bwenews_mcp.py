"""BWEnews MCP Server — standalone service that monitors @BWEnews TG channel
and serves news via MCP JSON-RPC protocol.

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
from telethon import TelegramClient, events
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("bwenews_mcp")

TG_API_ID = int(os.environ.get("TG_API_ID", "0"))
TG_API_HASH = os.environ.get("TG_API_HASH", "")
BWENEWS_CHANNEL = "BWEnews"
MCP_PORT = int(os.environ.get("BWENEWS_MCP_PORT", "8788"))

# Store recent articles (last 100)
_articles = deque(maxlen=100)
_telethon_client = None


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
    return headline


def _extract_url(text: str) -> str:
    urls = re.findall(r'https?://\S+', text or "")
    return urls[0] if urls else ""


async def handle_new_post(event):
    text = event.message.text or event.message.message or ""
    if not text or len(text) < 10:
        return

    headline = _extract_headline(text)
    if not headline or len(headline) < 15:
        return

    url = _extract_url(text)
    post_time = event.message.date.timestamp() if event.message.date else time.time()

    article = {
        "title": headline,
        "url": url,
        "body": "",
        "source": "BWEnews",
        "categories": "crypto,finance,breaking",
        "published_at": post_time,
    }
    _articles.appendleft(article)
    logger.info(f"New article: {headline[:80]}")


async def mcp_handler(request):
    """Handle MCP JSON-RPC requests."""
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


async def start_telethon():
    global _telethon_client
    if not TG_API_ID or not TG_API_HASH:
        logger.error("TG_API_ID/TG_API_HASH not set")
        return

    session_path = os.path.join(os.path.dirname(__file__), "bwenews_session")
    _telethon_client = TelegramClient(session_path, TG_API_ID, TG_API_HASH)
    await _telethon_client.start()

    channel = await _telethon_client.get_entity(BWENEWS_CHANNEL)
    logger.info(f"Connected to @{BWENEWS_CHANNEL} (id={channel.id})")

    @_telethon_client.on(events.NewMessage(chats=channel))
    async def handler(event):
        try:
            await handle_new_post(event)
        except Exception as e:
            logger.error(f"Handler error: {e}")

    logger.info("Telethon listener started")


async def on_startup(app):
    await start_telethon()


async def on_cleanup(app):
    if _telethon_client:
        await _telethon_client.disconnect()


def main():
    app = web.Application()
    app.router.add_post("/mcp", mcp_handler)
    app.router.add_get("/health", health_handler)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    logger.info(f"BWEnews MCP server starting on port {MCP_PORT}")
    web.run_app(app, host="127.0.0.1", port=MCP_PORT, print=None)


if __name__ == "__main__":
    main()
