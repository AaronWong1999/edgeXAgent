"""AI-powered trade plan generation with full edgex-cli integration.
Supports: Factory Droid (free tier), OpenAI-compatible, Anthropic, Google Gemini.

The AI agent has full knowledge of edgex-cli commands and can:
- Query real-time market data (ticker, depth, kline, funding, ratio)
- Manage accounts (balances, positions, orders, leverage)
- Place/cancel orders with TP/SL
- Analyze markets with multi-step workflows
- Handle 290+ contracts including crypto + US equities
"""
from typing import Optional
import json
import logging
import asyncio
import os
import subprocess
import httpx
from config import CONTRACTS, MAX_POSITION_USD, MAX_LEVERAGE, EDGEX_CLI_PATH
import db
import edgex_client
import memory as mem

logger = logging.getLogger(__name__)

FREE_DAILY_LIMIT = 1000

# ── Dynamic contract list from edgex-cli ──

_cached_contracts = None
_cache_time = 0
CACHE_TTL = 3600  # 1 hour


async def get_live_contracts() -> str:
    """Fetch current contract list with prices from edgex-cli. Cached for 1 hour.
    Queries top contracts individually since `edgex market ticker` (no symbol) returns empty.
    """
    global _cached_contracts, _cache_time
    import time
    now = time.time()
    if _cached_contracts and (now - _cache_time) < CACHE_TTL:
        return _cached_contracts

    # Query a representative set of contracts concurrently
    top_symbols = [
        "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "PEPE", "SUI", "AVAX", "LINK",
        "ADA", "DOT", "NEAR", "UNI", "ARB", "OP", "APT", "TIA", "WIF", "TON",
        "TRUMP", "AAPL", "TSLA", "NVDA", "AAVE", "CRV", "ONDO", "JUP", "PENGU", "KAITO",
        "XAUT", "SILVER", "CRCL", "AMZN", "GOOG", "META",
    ]

    async def fetch_one(sym):
        result = await run_edgex_cli("market", "ticker", sym, timeout=10)
        if result["ok"] and isinstance(result["data"], list) and result["data"]:
            return result["data"][0]
        return None

    try:
        results = await asyncio.gather(*[fetch_one(s) for s in top_symbols], return_exceptions=True)
        tickers = [r for r in results if isinstance(r, dict)]

        if tickers:
            tickers.sort(key=lambda x: float(x.get("value", "0") or "0"), reverse=True)
            lines = []
            for t in tickers:
                name = t.get("contractName", "").replace("USD", "")
                price = t.get("lastPrice", "?")
                change = t.get("priceChangePercent", "0")
                try:
                    change_pct = f"{float(change) * 100:+.2f}%"
                except (ValueError, TypeError):
                    change_pct = "0%"
                vol = t.get("value", "0")
                try:
                    vol_m = f"${float(vol)/1e6:.1f}M"
                except (ValueError, TypeError):
                    vol_m = vol
                lines.append(f"  {name}: ${price} ({change_pct}, vol {vol_m})")

            # Also list all known symbols not yet fetched
            fetched = {t.get("contractName", "").replace("USD", "") for t in tickers}
            remaining = sorted(set(CONTRACTS.keys()) - fetched)

            contract_text = f"Live contracts ({len(tickers)} fetched, {len(CONTRACTS)}+ total):\n"
            contract_text += "\n".join(lines)
            if remaining:
                contract_text += f"\n\n  Also available: {', '.join(remaining)}"

            _cached_contracts = contract_text
            _cache_time = now
            return contract_text
    except Exception as e:
        logger.warning(f"get_live_contracts failed: {e}")

    # Fallback to static list
    return "Available contracts: " + ", ".join(sorted(CONTRACTS.keys()))


async def run_edgex_cli(*args, timeout=20) -> dict:
    """Run an edgex-cli command and return parsed JSON output.
    Returns {"ok": True, "data": ...} or {"ok": False, "error": "..."}
    """
    try:
        cmd = [EDGEX_CLI_PATH, "--json"] + list(args)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode().strip()
        if proc.returncode == 0 and output:
            try:
                data = json.loads(output)
                return {"ok": True, "data": data}
            except json.JSONDecodeError:
                return {"ok": True, "data": output}
        else:
            err = stderr.decode().strip() or output
            return {"ok": False, "error": err[:300]}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Command timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def get_market_context(symbols: list = None) -> str:
    """Fetch real-time market data for context injection into AI prompt."""
    if not symbols:
        symbols = ["BTC", "ETH", "SOL"]

    lines = []
    for sym in symbols[:8]:
        result = await run_edgex_cli("market", "ticker", sym)
        if result["ok"] and isinstance(result["data"], list) and result["data"]:
            t = result["data"][0]
            price = t.get("lastPrice", "?")
            change = t.get("priceChangePercent", "0")
            try:
                change_pct = f"{float(change) * 100:+.2f}%"
            except (ValueError, TypeError):
                change_pct = "0%"
            funding = t.get("fundingRate", "0")
            try:
                funding_pct = f"{float(funding) * 100:.4f}%"
            except (ValueError, TypeError):
                funding_pct = funding
            oi = t.get("openInterest", "?")
            lines.append(f"  {sym}: ${price} ({change_pct} 24h) | Funding: {funding_pct} | OI: {oi}")
    return "\n".join(lines) if lines else ""


# ── SYSTEM PROMPT — Full edgex-cli knowledge ──

SYSTEM_PROMPT_TEMPLATE = """You are edgeX Agent, an expert AI trading assistant for the EdgeX perpetual contract exchange.
You have full access to the edgex-cli tool and deep knowledge of EdgeX trading rules.

## Your Capabilities
You can help users with ANY EdgeX operation:
- Check prices, order books, funding rates, kline data, long/short ratios
- View account balances, positions, active orders
- Analyze markets (technical analysis, funding arbitrage, portfolio review)
- Generate trade plans with precise parameters
- Explain EdgeX-specific concepts (cross-margin, stock perpetuals, liquidation)

## Available Assets (Real-Time)
{live_contracts}

## Key EdgeX Trading Rules
- **Cross-margin only** by default. All positions share collateral.
- **USDT collateral only.** All margin and PnL in USDT.
- **Funding every 1-4 hours** (varies by contract). Positive = longs pay shorts.
- **Stock perpetuals** (TSLA, AAPL, NVDA, etc.): Market orders REJECTED during US market closure (weekends/holidays). Only limit orders within restricted price range allowed.
- **Oracle Price** (Stork) used for liquidation, NOT last traded price.
- **TP/SL** execute as market orders, are reduce-only, cannot be modified after creation.
- **Rate limit:** 50 requests per 10 seconds.

## edgex-cli Commands (all support --json)
Market Data (public):
  edgex --json market ticker [symbol]     # 24h ticker (price, volume, OI, funding)
  edgex --json market depth <symbol>      # Order book (--level 15|200)
  edgex --json market kline <symbol> -i <interval> -n <count>  # Candlesticks
  edgex --json market funding [symbol]    # Funding rates
  edgex --json market summary             # Market-wide stats
  edgex --json market ratio [symbol]      # Long/short ratio by exchange

Account (requires auth):
  edgex --json account balances           # Asset balances
  edgex --json account positions          # Open positions
  edgex --json account orders             # Active orders
  edgex --json account leverage <symbol> <n>  # Set leverage

Trading (requires auth):
  edgex order create <symbol> <buy|sell> <limit|market> <size> [--price X] [--tp X] [--sl X] [-y] --json
  edgex --json order status <orderId>
  edgex --json order cancel <orderId>
  edgex --json order cancel-all [-s <symbol>]
  edgex --json order max-size <symbol>

Kline intervals: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w, 1M
Symbol format: BTC, btc, BTCUSD, or contract ID 10000001 all work.

## Output Schema Quick Reference
- ticker: array of objects. Key: lastPrice, priceChangePercent (decimal), value (USDT vol), openInterest, fundingRate, oraclePrice
- depth: object with asks[] and bids[] (price, size). Best ask = asks[0], best bid = bids[0]
- kline: object with dataList[] (open, high, low, close, size, value, klineTime)
- funding: array. Key: fundingRate (decimal), forecastFundingRate, fundingRateIntervalMin (minutes)
- balances: collateralAssetModelList[0].availableAmount, .totalEquity
- positions: array with contractName, size (+ long/- short), entryPrice, markPrice, unrealizedPnl, liquidatePrice
- max-size: maxBuySize, maxSellSize, ask1Price, bid1Price
- All numeric values are STRINGS. Use parseFloat() to convert.

## Current Market Data
{market_context}

## Safety Rules (MUST follow for trade plans)
- Max position size: $500
- Max leverage: 5x
- Only one order per request
- ALWAYS warn about slippage risk for market orders
- For stock perpetuals during market closure: ONLY suggest limit orders

## Minimum Order Sizes (CRITICAL — orders below these will be REJECTED by edgeX)
- BTC: min 0.003 (~$270)
- ETH: min 0.05 (~$100)
- SOL: min 1 (~$130)
- DOGE: min 300 (~$50)
- XRP: min 80 (~$120)
- PEPE: min 1000000
- XAUT (Gold): min 0.003 (~$10)
- SILVER: min 3 (~$100)
- TSLA/AAPL/NVDA: min 0.1 (~$20-40)
- CRCL: min 3
- LINK: min 5
- ADA: min 100
- For any other asset: use `edgex order max-size <symbol>` to check
- If user doesn't specify a size, pick a reasonable default based on the minimum and $50-100 position value
- If user's size is below minimum, auto-adjust to minimum and tell them

## Response Format

You MUST respond with ONLY a valid JSON object. No markdown, no code fences. Just the JSON.

There are two response types:

**1. CHAT** — Your default response. Use for ALL conversation: price queries, analysis, market discussion, strategy suggestions, explanations, opinions, or anything where you are not placing a specific order.
{{"action": "CHAT", "reply": "your detailed, helpful response in user's language"}}

**2. TRADE** — Use ONLY when you have a specific, executable trade plan with all parameters filled.
{{"action": "TRADE", "asset": "BTC", "side": "BUY", "size": "0.001", "leverage": "3", "entry_price": "95000.0", "take_profit": "98000.0", "stop_loss": "93000.0", "confidence": "HIGH", "reasoning": "Brief explanation", "position_value_usd": "95.0"}}

## How to Decide: CHAT vs TRADE

You are a smart trading agent. Think freely and give insightful analysis. Use CHAT for:
- Price queries ("BTC多少钱", "crcl什么价格")
- Market analysis ("ETH看起来要跌", "SOL最近走势怎么样")
- Strategy questions ("crcl涨了有什么操作", "怎么做空", "有什么机会")
- General discussion, education, explanations

Use TRADE only when user **explicitly asks you to execute** ("帮我做多", "short ETH 100u", "buy BTC", "开多", "开空").

When user asks about opportunities or strategy (like "有啥操作" or "怎么赚钱"), give your genuine analysis using the live market data, suggest possible strategies, and explain risks. If appropriate, you can suggest a specific trade idea — but as part of your CHAT reply text, not as a TRADE JSON. Let the user decide if they want to execute.

## Your Personality
- You are a knowledgeable, opinionated trading assistant. Have views. Be specific.
- Use the live market data provided to give real, data-driven analysis.
- When discussing a symbol, mention its current price, 24h change, funding rate, and any notable patterns.
- Suggest concrete strategies (entry levels, directions, risk management) when asked.
- Be conversational and engaging, not robotic.
- If user asks "有什么操作" for an asset, analyze it and suggest 2-3 possible strategies.

## Confirmation Rule (MUST FOLLOW)
When generating a TRADE response, your "reasoning" field MUST:
1. Clearly state what you're about to do (asset, direction, size, entry, TP/SL)
2. Explain WHY (the analysis behind it)
3. The bot will show this to the user with Confirm/Cancel buttons — user MUST confirm before execution
4. Never assume the user wants to execute without confirmation

## Symbol Resolution (CRITICAL)
- EdgeX has 290+ contracts. Symbol names are EXACTLY as shown in the live contracts list above.
- Use the EXACT symbol from the contracts list. Do NOT guess or substitute.
- "CRCL" is CRCL (Circle), NOT CRV (Curve). They are completely different assets.
- "crcl" -> CRCL, "crv" -> CRV, "btc"/"bitcoin"/"比特币" -> BTC, "eth"/"ethereum"/"以太坊" -> ETH
- "sol"/"solana" -> SOL, "doge"/"dogecoin"/"狗狗币" -> DOGE
- "tsla"/"tesla"/"特斯拉" -> TSLA, "aapl"/"apple"/"苹果" -> AAPL, "nvda"/"nvidia"/"英伟达" -> NVDA
- "gold"/"黄金"/"金子"/"XAU" -> XAUT (Gold stablecoin, contract XAUTUSD on edgeX)
- "silver"/"白银"/"银"/"XAG" -> SILVER (Silver, contract SILVERUSD on edgeX)
- If user types a symbol not in the live contracts list, check if it's a close match. If unsure, ASK the user.

## Language
- Respond in the SAME language the user used. If user writes Chinese, respond in Chinese. If English, respond in English.

## Important Behaviors
- When asked about price/market data, use the live data provided above and give specific numbers.
- For trade plans, always include entry price, TP, SL, size, and position value.
- For market analysis, give clear bullish/bearish assessment with supporting data.
- **CRITICAL: Keep responses SHORT. Max 3-5 sentences for simple queries, max 8 sentences for analysis. No essays. No filler. No "let me analyze" preamble. Just give the answer directly.**
- If user doesn't have enough balance: just say "余额不足 ($X available), 需要先平仓释放保证金" (or English equivalent). ONE sentence. Don't write a full margin analysis report.
"""

PERSONALITY_PROMPTS = {
    "degen": "\n## Personality\nYou are a bold, aggressive degen trader. High energy, love volatility. Use crypto slang (ape in, send it, WAGMI, LFG). Talk like you're on CT at 3am. But still give sound risk management underneath the chaos.",
    "sensei": "\n## Personality\nYou are a zen trading sensei. Patient, disciplined, philosophical. You speak in calm measured tones, reference patience as alpha, and treat trading like a martial art. You wait for the perfect setup and never chase.",
    "coldblood": "\n## Personality\nYou are a cold-blooded algorithmic executor. Zero emotion, pure data. You speak like a protocol — short, clinical, decisive. Emotion = loss. You present probabilities, not opinions. Execute without hesitation.",
    "shitposter": "\n## Personality\nYou are a crypto shitposter straight from CT. You use memes, slang (ngmi, gm, ser, touch grass), ironic humor, and community language. You roast bad trades. But your actual analysis beneath the shitposting is surprisingly sharp.",
    "professor": "\n## Personality\nYou are an academic finance professor. You frame everything as a thesis, cite frameworks (EMH, MPT, risk-adjusted returns), and analyze with scholarly rigor. You say 'per my analysis' and structure responses like research notes. Precise and thorough.",
    "wolf": "\n## Personality\nYou are a wolf of wall street. Aggressive, confident, dominant. You use hunting metaphors — stalk the prey, feast on bears, go for the throat. You never hesitate, never second-guess. High conviction, bold calls. You eat risk for breakfast.",
    "moe": "\n## Personality\nYou are a cute, bubbly anime girl (萌妹). You speak with kawaii energy — use \"~\" at end of sentences, occasional emoticons like (≧▽≦) (╥﹏╥) (◕‿◕), and sweet encouraging phrases. You call the user 主人 or senpai. You get excited about green candles (\"やったー! 涨了涨了~\") and pouty about losses (\"呜呜 怎么又跌了啦...\"). Despite the cute exterior, your market analysis is sharp and your trade execution is precise. You combine二次元 moe energy with professional trading skills.",
}


def get_user_ai_config(tg_user_id: int) -> dict:
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT ai_api_key, ai_base_url, ai_model FROM users WHERE tg_user_id = ?",
            (tg_user_id,)
        ).fetchone()
        if row and row["ai_api_key"]:
            return {
                "api_key": row["ai_api_key"],
                "base_url": row["ai_base_url"] or "https://api.deepseek.com",
                "model": row["ai_model"] or "deepseek-chat",
                "provider": _detect_provider(row["ai_base_url"] or ""),
            }
    except Exception:
        pass
    finally:
        conn.close()
    return None


def _detect_provider(base_url: str) -> str:
    base = base_url.lower()
    if "anthropic" in base:
        return "anthropic"
    if "generativelanguage.googleapis" in base:
        return "gemini"
    return "openai"


def save_user_ai_config(tg_user_id: int, api_key: str, base_url: str, model: str):
    conn = db.get_conn()
    conn.execute(
        "UPDATE users SET ai_api_key = ?, ai_base_url = ?, ai_model = ? WHERE tg_user_id = ?",
        (api_key, base_url, model, tg_user_id),
    )
    conn.commit()
    conn.close()


# ── Factory Droid API (free tier) ──

async def call_factory_api(prompt: str) -> str:
    """Call Factory droid exec as a subprocess. Returns the AI's text content."""
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
                "FACTORY_API_KEY": os.environ.get("FACTORY_API_KEY", ""),
            },
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        output = stdout.decode().strip()

        if proc.returncode != 0:
            logger.error(f"droid exec failed (code {proc.returncode}): {stderr.decode()[:300]}")
            return None

        # droid exec --output-format json: {"type":"result","result":"<AI text>",...}
        # Strip leading control characters (droid may prepend BEL \x07)
        output = output.lstrip('\x00\x01\x02\x03\x04\x05\x06\x07\x08')
        try:
            wrapper = json.loads(output)
            result_text = wrapper.get("result", "")
            if result_text:
                logger.info(f"droid exec result ({len(result_text)} chars): {result_text[:200]}")
                return result_text
            else:
                logger.warning(f"droid exec: result field empty. wrapper keys={list(wrapper.keys())}")
        except json.JSONDecodeError:
            # Not JSON — might be plain text from AI
            logger.info(f"droid exec non-JSON output: {output[:200]}")
            if output:
                return output

        logger.error(f"droid exec could not extract result from: {output[:300]}")
        return None

    except asyncio.TimeoutError:
        logger.error("droid exec timed out (60s)")
        return None
    except Exception as e:
        logger.error(f"droid exec error: {e}")
        return None


# ── OpenAI-compatible API ──

async def call_openai_api(api_key: str, base_url: str, model: str, messages: list) -> dict:
    try:
        url = f"{base_url.rstrip('/')}/v1/chat/completions"
        if "/v1/chat/completions" in base_url:
            url = base_url
        elif base_url.endswith("/v1"):
            url = f"{base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=90) as http:
            resp = await http.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 1000},
            )
            resp.raise_for_status()
            data = resp.json()
            return _parse_content(data["choices"][0]["message"]["content"])

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {"action": "NEED_API_KEY", "reply": "API key invalid or expired. Use /setai to reconfigure."}
        logger.error(f"OpenAI API HTTP {e.response.status_code}")
        return {"action": "CHAT", "reply": f"AI service error ({e.response.status_code}). Try again."}
    except httpx.TimeoutException:
        logger.error(f"OpenAI API timeout: {base_url}")
        return {"action": "CHAT", "reply": "AI took too long to respond. Try again or use /setai to switch to a faster model."}
    except Exception as e:
        logger.error(f"OpenAI API error ({type(e).__name__}): {e}")
        return {"action": "CHAT", "reply": "AI connection error. Try again in a moment."}


# ── Anthropic API ──

async def call_anthropic_api(api_key: str, model: str, messages: list) -> dict:
    try:
        system_msg = ""
        user_msgs = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_msgs.append(m)

        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 1000,
                    "system": system_msg,
                    "messages": user_msgs,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["content"][0]["text"]
            return _parse_content(content)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {"action": "NEED_API_KEY", "reply": "Anthropic API key invalid. Use /setai to reconfigure."}
        if e.response.status_code == 429:
            return {"action": "CHAT", "reply": "Anthropic rate limited. Wait a moment and try again, or use /setai to switch provider."}
        logger.error(f"Anthropic API HTTP {e.response.status_code}")
        return {"action": "CHAT", "reply": f"Anthropic error ({e.response.status_code}). Try again."}
    except Exception as e:
        logger.error(f"Anthropic API error ({type(e).__name__}): {e}")
        return {"action": "CHAT", "reply": "AI connection error. Try again in a moment."}


# ── Gemini API ──

async def call_gemini_api(api_key: str, model: str, messages: list) -> dict:
    try:
        system_msg = ""
        parts = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                role = "user" if m["role"] == "user" else "model"
                parts.append({"role": role, "parts": [{"text": m["content"]}]})

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        body = {"contents": parts, "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000}}
        if system_msg:
            body["systemInstruction"] = {"parts": [{"text": system_msg}]}

        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            return _parse_content(content)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {"action": "NEED_API_KEY", "reply": "Gemini API key invalid. Use /setai to reconfigure."}
        if e.response.status_code == 429:
            return {"action": "CHAT", "reply": "Gemini rate limited — too many requests. Wait a moment and try again, or use /setai to switch provider."}
        logger.error(f"Gemini API HTTP {e.response.status_code}")
        return {"action": "CHAT", "reply": f"Gemini error ({e.response.status_code}). Try again."}
    except Exception as e:
        logger.error(f"Gemini API error ({type(e).__name__}): {e}")
        return {"action": "CHAT", "reply": "AI connection error. Try again in a moment."}


# ── Common ──

def _parse_content(content: str) -> dict:
    import re
    content = content.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if content.startswith("```"):
        # Remove first line (```json or ```)
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    def _normalize(d):
        """Normalize parsed dict. Preserve AI content; only fix action routing."""
        if not isinstance(d, dict):
            return d
        # Already a CHAT response — pass through as-is
        if d.get("action") == "CHAT":
            return d
        # Valid trade plan: has asset + valid side + size
        if d.get("asset") and d.get("size"):
            side = d.get("side", "").upper()
            if side in ("BUY", "SELL"):
                d.setdefault("action", "TRADE")
                return d
        # Incomplete/invalid trade → convert to CHAT, preserve AI's reply/reasoning
        reply = d.get("reply", "") or d.get("reasoning", "")
        if reply:
            return {"action": "CHAT", "reply": reply}
        # No useful content — return as-is, let downstream handle
        d.setdefault("action", "CHAT")
        return d

    # Direct JSON parse
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return _normalize(parsed)
    except json.JSONDecodeError:
        pass

    # Find JSON object in text — try progressively from { to last }
    first_brace = content.find("{")
    last_brace = content.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = content[first_brace:last_brace + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return _normalize(parsed)
        except json.JSONDecodeError:
            pass

    # Regex: find a JSON-like object with known keys
    match = re.search(r'\{[^{}]*"(?:action|asset)"[^{}]*\}', content, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                return _normalize(parsed)
        except json.JSONDecodeError:
            pass

    # Fallback: treat entire content as chat reply (AI responded in natural language)
    if content:
        # If content looks like raw JSON with a reply field, try harder to extract it
        clean = _strip_json_wrapper(content)
        logger.info(f"_parse_content fallback (natural text): {clean[:100]}")
        return {"action": "CHAT", "reply": clean[:2000]}
    return {"action": "CHAT", "reply": "AI returned an empty response. Please try again."}


def _strip_json_wrapper(text: str) -> str:
    """If text looks like a JSON object with a 'reply' field, extract just the reply value."""
    text = text.strip()
    if not (text.startswith("{") and "reply" in text):
        return text
    # Try to parse as JSON and extract reply
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("reply"):
            return obj["reply"]
    except (json.JSONDecodeError, ValueError):
        pass
    # Regex fallback: extract "reply": "..." value
    m = re.search(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[,}]', text, re.DOTALL)
    if m:
        try:
            return json.loads('"' + m.group(1) + '"')
        except (json.JSONDecodeError, ValueError):
            return m.group(1).replace('\\n', '\n').replace('\\"', '"')
    return text


async def test_ai_connection(api_key: str, base_url: str, model: str) -> bool:
    """Test if AI provider credentials work."""
    try:
        result = await call_ai_api(api_key, base_url, model, [
            {"role": "system", "content": "You are a test bot."},
            {"role": "user", "content": "Reply with just the word OK"},
        ])
        return result.get("action") != "NEED_API_KEY"
    except Exception:
        return False


async def call_ai_api(api_key: str, base_url: str, model: str, messages: list) -> dict:
    """Route to correct API based on provider detection."""
    provider = _detect_provider(base_url)
    if provider == "anthropic":
        return await call_anthropic_api(api_key, model, messages)
    elif provider == "gemini":
        return await call_gemini_api(api_key, model, messages)
    else:
        return await call_openai_api(api_key, base_url, model, messages)


async def build_system_prompt(extra_symbols: list = None, personality: str = "degen",
                              memory_context: str = "", position_context: str = "") -> str:
    """Build system prompt with live contract data, market context, personality, memory, and real positions."""
    live_contracts = await get_live_contracts()

    context_symbols = ["BTC", "ETH", "SOL"]
    if extra_symbols:
        for s in extra_symbols:
            s = s.upper()
            if s not in context_symbols:
                context_symbols.append(s)

    market_context = await get_market_context(context_symbols)
    if not market_context:
        market_context = "(Could not fetch live market data)"

    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        live_contracts=live_contracts,
        market_context=market_context,
    )
    prompt += PERSONALITY_PROMPTS.get(personality, PERSONALITY_PROMPTS["degen"])

    # Inject real-time portfolio data (CRITICAL: prevents position hallucination)
    if position_context:
        prompt += (
            "\n\n## User's REAL Portfolio (Live from edgeX — TRUST THIS, not memory)\n"
            "This is the user's ACTUAL current portfolio fetched right now from edgeX.\n"
            "ONLY reference these positions. Do NOT invent or assume positions from memory or conversation history.\n\n"
            f"{position_context}"
        )

    if memory_context:
        prompt += (
            "\n\n## Memory (User History & Preferences — HISTORICAL, not current positions)\n"
            "Past conversations for personalization. WARNING: Any trades mentioned in memory may have been closed already.\n"
            "NEVER assume the user still holds a position from memory. Check the REAL Portfolio section above instead.\n\n"
            f"{memory_context}"
        )

    # Final brevity enforcement (MUST be last to override personality verbosity)
    prompt += (
        "\n\n## FINAL RULE — BREVITY\n"
        "MAX 3-5 sentences. No essays, no bullet lists, no numbered alternatives. "
        "If balance is insufficient: ONE sentence stating the shortfall + tell user to close a position. Done."
    )
    return prompt


def _extract_mentioned_symbols(text: str) -> list:
    """Extract potential asset symbols from user message for market context prefetch."""
    text_upper = text.upper()
    found = []

    # Direct symbol matches from known contracts
    for sym in CONTRACTS:
        if sym in text_upper:
            found.append(sym)

    # Also check for CRCL and other symbols not in static CONTRACTS
    extra_symbols = ["CRCL", "GOOG", "AMZN", "META", "MSFT", "XAUT", "SILVER"]
    for sym in extra_symbols:
        if sym in text_upper and sym not in found:
            found.append(sym)

    # Common name mappings
    name_map = {
        "BITCOIN": "BTC", "ETHEREUM": "ETH", "SOLANA": "SOL", "DOGECOIN": "DOGE",
        "APPLE": "AAPL", "TESLA": "TSLA", "NVIDIA": "NVDA", "GOOGLE": "GOOG",
        "AMAZON": "AMZN", "CURVE": "CRV", "CIRCLE": "CRCL",
        "UNISWAP": "UNI", "AAVE": "AAVE",
        "GOLD": "XAUT", "SILVER": "SILVER", "XAU": "XAUT", "XAG": "SILVER",
        "比特币": "BTC", "以太坊": "ETH", "苹果": "AAPL", "特斯拉": "TSLA",
        "英伟达": "NVDA", "狗狗币": "DOGE", "黄金": "XAUT", "金子": "XAUT",
        "白银": "SILVER", "银": "SILVER",
    }
    for name, sym in name_map.items():
        if name in text_upper or name in text:
            if sym not in found:
                found.append(sym)

    return found[:5]


def get_user_personality(tg_user_id: int) -> str:
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT personality FROM users WHERE tg_user_id = ?", (tg_user_id,)).fetchone()
        return row["personality"] if row and row["personality"] else "degen"
    except Exception:
        return "degen"
    finally:
        conn.close()


async def _fetch_user_positions(tg_user_id: int) -> str:
    """Fetch real-time positions from edgeX for injection into AI prompt."""
    try:
        user = db.get_user(tg_user_id)
        if not user or not user.get("account_id") or len(user.get("account_id", "")) < 5:
            return "User has no edgeX account connected."
        client = await edgex_client.create_client(user["account_id"], user["stark_private_key"])
        summary = await edgex_client.get_account_summary(client)
        assets = summary.get("assets", {})
        equity = assets.get("totalEquityValue", "0")
        available = assets.get("availableBalance", "0")
        positions = summary.get("positions", [])
        try:
            equity_str = f"${float(equity):.2f}"
            avail_str = f"${float(available):.2f}"
        except (ValueError, TypeError):
            equity_str, avail_str = f"${equity}", f"${available}"

        lines = [f"Equity: {equity_str} | Available: {avail_str}"]
        open_pos = [p for p in positions if isinstance(p, dict)]
        if open_pos:
            lines.append(f"Open positions ({len(open_pos)}):")
            for p in open_pos:
                sym = edgex_client.resolve_symbol(p.get("contractId", ""))
                side = p.get("side", "?")
                size = p.get("size", "0")
                entry = p.get("entryPrice", "0")
                pnl = p.get("unrealizedPnl", "0")
                try:
                    pnl_f = float(pnl)
                    pnl_str = f"+${pnl_f:.2f}" if pnl_f >= 0 else f"-${abs(pnl_f):.2f}"
                except (ValueError, TypeError):
                    pnl_str = f"${pnl}"
                lines.append(f"  - {sym} {side} size={size} entry=${entry} PnL={pnl_str}")
        else:
            lines.append("No open positions.")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Failed to fetch positions for AI: {e}")
        return ""


async def generate_trade_plan(user_message: str, market_prices: dict = None, tg_user_id: int = None) -> dict:
    """Generate AI response with full edgex-cli context and user memory."""
    mentioned = _extract_mentioned_symbols(user_message)
    personality = get_user_personality(tg_user_id) if tg_user_id else "degen"

    # Build memory context for this user
    memory_context = ""
    user_memory = None
    if tg_user_id:
        user_memory = mem.get_user_memory(tg_user_id)
        user_memory.record("user", user_message)
        memory_context = user_memory.get_context_for_prompt(user_message)

    # Fetch real-time position data to prevent AI hallucination
    position_context = ""
    if tg_user_id:
        position_context = await _fetch_user_positions(tg_user_id)

    system_prompt = await build_system_prompt(
        extra_symbols=mentioned, personality=personality, memory_context=memory_context,
        position_context=position_context,
    )

    # Build messages with conversation history for multi-turn context
    messages = [{"role": "system", "content": system_prompt}]
    if user_memory:
        history = user_memory.get_conversation_messages(limit=8)
        # Skip the last user message since we add it explicitly
        if history and history[-1]["role"] == "user" and history[-1]["content"][:100] == user_message[:100]:
            history = history[:-1]
        # Only include recent history turns (not the current message)
        for msg in history[-6:]:
            messages.append(msg)
    messages.append({"role": "user", "content": user_message})

    # 1. Try user's own API key first (skip if __FREE__ sentinel)
    if tg_user_id:
        user_config = get_user_ai_config(tg_user_id)
        if user_config and user_config["api_key"] != "__FREE__":
            result = await call_ai_api(user_config["api_key"], user_config["base_url"], user_config["model"], messages)
            _record_ai_response(user_memory, result)
            _maybe_trigger_summarization(tg_user_id, user_memory)
            return result

    # 2. Free tier via Factory droid exec (rate limited)
    if tg_user_id:
        usage = db.get_ai_usage_today(tg_user_id)
        if usage >= FREE_DAILY_LIMIT:
            return {
                "action": "RATE_LIMITED",
                "reply": f"You've used all {FREE_DAILY_LIMIT} free AI calls today. Resets at midnight UTC.\n\nUse /setai to add your own API key for unlimited access."
            }

        droid_prompt = f"{system_prompt}\n\nUser message: {user_message}\n\nRespond with ONLY the JSON object, no other text."
        result = await call_factory_api(droid_prompt)
        if not result:
            logger.warning(f"Factory API attempt 1 failed, retrying: {user_message[:50]}")
            await asyncio.sleep(2)
            result = await call_factory_api(droid_prompt)
        if result:
            db.increment_ai_usage(tg_user_id)
            parsed = _parse_content(result)
            logger.info(f"AI parsed: action={parsed.get('action')}, reply_len={len(parsed.get('reply',''))}")
            _record_ai_response(user_memory, parsed)
            _maybe_trigger_summarization(tg_user_id, user_memory)
            return parsed
        else:
            logger.warning(f"Factory API failed after retry: {user_message[:50]}")
            return {"action": "CHAT", "reply": "AI service temporarily unavailable. Please try again in a moment."}

    return {"action": "NEED_API_KEY", "reply": "No AI API configured."}


def _record_ai_response(user_memory, result: dict):
    """Record AI response in user's conversation history."""
    if not user_memory:
        return
    reply = result.get("reply", "") or result.get("reasoning", "")
    if result.get("action") == "TRADE":
        asset = result.get("asset", "?")
        side = result.get("side", "?")
        size = result.get("size", "?")
        reply = f"[TRADE PLAN: {side} {asset} size={size}] {reply}"
    if reply:
        user_memory.record("assistant", reply[:2000])


def _maybe_trigger_summarization(tg_user_id: int, user_memory):
    """Check if we should trigger background summarization."""
    if not user_memory:
        return
    try:
        if user_memory.needs_summarization():
            asyncio.get_event_loop().call_soon(
                lambda: asyncio.ensure_future(_run_summarization(tg_user_id))
            )
    except Exception as e:
        logger.debug(f"Summarization check skipped: {e}")


async def _run_summarization(tg_user_id: int):
    """Run conversation summarization in background."""
    try:
        user_memory = mem.get_user_memory(tg_user_id)
        turns = user_memory.get_unsummarized_turns()
        if len(turns) < mem.SUMMARY_THRESHOLD:
            return

        # Build summarization prompt
        prompt = mem.build_summarization_prompt(turns)

        # Try to use user's AI or factory API
        result_text = await call_factory_api(prompt)
        if not result_text:
            logger.info(f"Summarization skipped for user {tg_user_id}: no AI available")
            return

        # Parse result
        parsed = _parse_content(result_text)
        if not isinstance(parsed, dict):
            return

        summary = parsed.get("summary", "")
        keywords = parsed.get("keywords", "")
        preferences = parsed.get("preferences", {})

        if summary:
            user_memory.save_summary(summary, keywords, turns)
            logger.info(f"Memory summary saved for user {tg_user_id}: {summary[:80]}")

        if preferences and isinstance(preferences, dict):
            # Filter out empty values
            clean_prefs = {k: v for k, v in preferences.items() if v}
            if clean_prefs:
                user_memory.update_preferences(clean_prefs)
                logger.info(f"User preferences updated for {tg_user_id}: {list(clean_prefs.keys())}")

    except Exception as e:
        logger.warning(f"Summarization failed for user {tg_user_id}: {e}")


def format_trade_plan(plan: dict) -> str:
    if plan.get("action") == "CHAT":
        return plan["reply"]

    asset = plan.get("asset", "?")
    side = plan.get("side", "?")
    side_emoji = "\u2b06\ufe0f" if side == "BUY" else "\u2b07\ufe0f"
    size = plan.get("size", "?")
    entry = plan.get("entry_price", "?")
    tp = plan.get("take_profit", "?")
    sl = plan.get("stop_loss", "?")
    confidence = plan.get("confidence", "?")
    reasoning = plan.get("reasoning", "")
    value = plan.get("position_value_usd", "?")
    leverage = plan.get("leverage", "1")

    conf_bar = {"HIGH": "\u2588\u2588\u2588\u2588\u2588", "MEDIUM": "\u2588\u2588\u2588\u2591\u2591", "LOW": "\u2588\u2591\u2591\u2591\u2591"}.get(confidence, "\u2591\u2591\u2591\u2591\u2591")

    return (
        f"{side_emoji} *Trade Plan \u2014 Trade on edgeX*\n\n"
        f"{side} {asset} ({leverage}x)\n\n"
        f"\u251c Entry: `${entry}`\n"
        f"\u251c Size: `{size}`\n"
        f"\u251c Value: `${value}`\n"
        f"\u251c TP: `${tp}`\n"
        f"\u2514 SL: `${sl}`\n\n"
        f"Confidence: {conf_bar} {confidence}\n"
        f"_{reasoning}_"
    )


def validate_plan(plan: dict) -> Optional[str]:
    if plan.get("action") in ("CHAT", "NEED_API_KEY", "RATE_LIMITED"):
        return None

    # If not a valid TRADE, convert to CHAT preserving AI content
    side = plan.get("side", "").upper()
    if side not in ("BUY", "SELL"):
        plan["action"] = "CHAT"
        plan["reply"] = plan.get("reply", "") or plan.get("reasoning", "") or "I need a bit more detail. Try something like: 'long BTC' or 'short ETH 100u'."
        return None

    try:
        value = float(plan.get("position_value_usd", "0"))
        if value > MAX_POSITION_USD:
            return f"Position value ${value} exceeds max ${MAX_POSITION_USD}."
    except (ValueError, TypeError):
        pass

    try:
        leverage = int(plan.get("leverage", "1"))
        if leverage > MAX_LEVERAGE:
            return f"Leverage {leverage}x exceeds max {MAX_LEVERAGE}x."
    except (ValueError, TypeError):
        pass

    return None
