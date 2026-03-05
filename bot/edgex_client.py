"""Wrapper around edgeX Python SDK for bot operations."""
import asyncio
import json
import logging
from edgex_sdk import Client, OrderSide
from config import EDGEX_BASE_URL, EDGEX_WS_URL, MAX_POSITION_USD, MAX_LEVERAGE, CONTRACTS, SYMBOL_BY_CONTRACT, EDGEX_CLI_PATH

logger = logging.getLogger(__name__)

# Dynamic contract ID cache (refreshed from edgex-cli)
_live_contract_cache = {}
_live_cache_time = 0
LIVE_CACHE_TTL = 3600

# Contract metadata cache (minOrderSize, stepSize per contract)
_metadata_cache = {}
_metadata_cache_time = 0
METADATA_CACHE_TTL = 3600


async def resolve_contract_id(symbol: str) -> str:
    """Resolve symbol to contract ID using edgex-cli (live), fallback to static map."""
    global _live_contract_cache, _live_cache_time
    import time

    sym = symbol.upper().replace("-PERP", "").replace("USD", "")

    # Commodity aliases
    _aliases = {"GOLD": "XAUT", "XAU": "XAUT", "XAG": "SILVER"}
    sym = _aliases.get(sym, sym)

    # Check live cache first
    if sym in _live_contract_cache and (time.time() - _live_cache_time) < LIVE_CACHE_TTL:
        return _live_contract_cache[sym]

    # Query edgex-cli for live contract info
    try:
        proc = await asyncio.create_subprocess_exec(
            EDGEX_CLI_PATH, "--json", "market", "ticker", sym,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0:
            data = json.loads(stdout.decode().strip())
            if isinstance(data, list) and data:
                cid = data[0].get("contractId", "")
                if cid:
                    _live_contract_cache[sym] = cid
                    _live_cache_time = time.time()
                    logger.info(f"Resolved {sym} -> contractId {cid}")
                    return cid
    except Exception as e:
        logger.warning(f"Live contract resolution failed for {sym}: {e}")

    # Fallback to static map
    return CONTRACTS.get(sym, "")


async def get_market_price(symbol: str) -> str:
    """Get last traded price for a symbol using edgex-cli."""
    sym = symbol.upper().replace("-PERP", "").replace("USD", "")
    _aliases = {"GOLD": "XAUT", "XAU": "XAUT", "XAG": "SILVER"}
    sym = _aliases.get(sym, sym)
    try:
        proc = await asyncio.create_subprocess_exec(
            EDGEX_CLI_PATH, "--json", "market", "ticker", sym,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0:
            data = json.loads(stdout.decode().strip())
            if isinstance(data, list) and data:
                price = data[0].get("lastPrice", "")
                if price:
                    return str(price)
    except Exception as e:
        logger.warning(f"get_market_price failed for {sym}: {e}")
    return ""


async def create_client(account_id: str, stark_private_key: str) -> Client:
    client = Client(
        base_url=EDGEX_BASE_URL,
        account_id=int(account_id),
        stark_private_key=stark_private_key,
    )
    return client


async def get_account_summary(client: Client) -> dict:
    """Get account balance and positions summary."""
    try:
        assets_resp = await client.get_account_asset()
        positions_resp = await client.get_account_positions()

        # Proactively populate metadata cache for symbol resolution
        if not _metadata_cache:
            try:
                await get_contract_specs(client, "0")
            except Exception:
                pass

        # positions_resp.data is a dict with positionList, positionAssetList, collateralAssetModelList
        pos_raw = positions_resp.get("data", {})
        if isinstance(pos_raw, list):
            pos_raw = {}

        raw = assets_resp.get("data", {})
        if isinstance(raw, list):
            raw = {}

        # Collateral / equity
        collateral_list = pos_raw.get("collateralAssetModelList", []) or raw.get("collateralAssetModelList", [])
        collateral = collateral_list[0] if collateral_list else {}
        total_equity = collateral.get("totalEquity", "0")
        available = collateral.get("availableAmount", "0")

        # Merge positionList + positionAssetList into usable position objects
        pos_list = pos_raw.get("positionList", []) or raw.get("positionList", [])
        pos_assets = pos_raw.get("positionAssetList", []) or raw.get("positionAssetList", [])

        # Build a contractId -> positionAsset map for unrealized PnL, avgEntryPrice etc.
        asset_by_contract = {}
        for pa in pos_assets:
            if isinstance(pa, dict):
                asset_by_contract[pa.get("contractId", "")] = pa

        positions = []
        for p in pos_list:
            if not isinstance(p, dict):
                continue
            cid = p.get("contractId", "")
            open_size = p.get("openSize", "0")
            try:
                if float(open_size) == 0:
                    continue
            except (ValueError, TypeError):
                continue
            pa = asset_by_contract.get(cid, {})
            positions.append({
                "contractId": cid,
                "size": open_size,
                "side": "LONG" if float(open_size) > 0 else "SHORT",
                "entryPrice": pa.get("avgEntryPrice", "0"),
                "unrealizedPnl": pa.get("unrealizePnl", "0"),
                "liquidatePrice": pa.get("liquidatePrice", "0"),
                "positionValue": pa.get("positionValue", "0"),
                "maxLeverage": pa.get("maxLeverage", "0"),
            })

        return {
            "assets": {
                "totalEquityValue": total_equity,
                "availableBalance": available,
            },
            "positions": positions,
            "raw": pos_raw,
        }
    except Exception as e:
        logger.error(f"get_account_summary error: {e}")
        return {"error": str(e)}


def resolve_symbol(contract_id: str) -> str:
    """Resolve contract ID to human symbol. Uses static map + metadata cache."""
    cid = str(contract_id)
    # Static map first
    sym = SYMBOL_BY_CONTRACT.get(cid)
    if sym:
        return sym
    # Dynamic metadata cache (populated by get_contract_specs)
    if _metadata_cache:
        meta = _metadata_cache.get(cid, {})
        name = meta.get("contractName", "")
        if name:
            return name.replace("USD", "").replace("-PERP", "")
    return cid


def _extract_quote(raw_data) -> dict:
    """Extract quote from API response data (can be dict or list)."""
    if isinstance(raw_data, list) and len(raw_data) > 0:
        return raw_data[0]
    if isinstance(raw_data, dict):
        return raw_data
    return {}


async def get_price(client: Client, contract_id: str) -> dict:
    """Get current price for a contract."""
    try:
        quote = await client.get_24_hour_quote(contract_id)
        data = _extract_quote(quote.get("data"))
        return {
            "last_price": data.get("lastPrice", "0"),
            "price_change_pct": data.get("priceChangePercent", "0"),
            "high_24h": data.get("high", "0"),
            "low_24h": data.get("low", "0"),
            "volume_24h": data.get("value", "0"),
        }
    except Exception as e:
        logger.error(f"get_price error: {e}")
        return {"error": str(e)}


async def get_prices_for_all(client: Client) -> dict:
    """Get prices for all tracked contracts."""
    results = {}
    for symbol, cid in CONTRACTS.items():
        try:
            quote = await client.get_24_hour_quote(cid)
            data = _extract_quote(quote.get("data"))
            pct = data.get("priceChangePercent", "0")
            try:
                pct = f"{float(pct) * 100:.2f}"
            except (ValueError, TypeError):
                pass
            results[symbol] = {
                "price": data.get("lastPrice", "N/A"),
                "change": pct,
            }
        except Exception:
            results[symbol] = {"price": "N/A", "change": "0"}
    return results


async def get_contract_specs(client: Client, contract_id: str) -> dict:
    """Get minOrderSize and stepSize for a contract. Cached 1 hour."""
    global _metadata_cache, _metadata_cache_time
    import time
    now = time.time()

    if _metadata_cache and (now - _metadata_cache_time) < METADATA_CACHE_TTL:
        return _metadata_cache.get(contract_id, {})

    try:
        meta = await client.get_metadata()
        contracts = meta.get("data", {}).get("contractList", [])
        _metadata_cache = {}
        for c in contracts:
            cid = str(c.get("contractId", ""))
            _metadata_cache[cid] = {
                "minOrderSize": c.get("minOrderSize", "0"),
                "stepSize": c.get("stepSize", "0"),
                "tickSize": c.get("tickSize", "0.01"),
                "contractName": c.get("contractName", ""),
            }
        _metadata_cache_time = now
        return _metadata_cache.get(contract_id, {})
    except Exception as e:
        logger.warning(f"get_contract_specs failed: {e}")
        return {}


async def pre_trade_check(client: Client, contract_id: str, side: str, size: str) -> dict:
    """Check if trade is feasible before placing. Returns {ok, error, suggestion}."""
    try:
        size_f = float(size)
    except (ValueError, TypeError):
        return {"ok": False, "error": "Invalid order size."}

    # 1. Check min order size from contract metadata
    specs = await get_contract_specs(client, contract_id)
    if specs:
        try:
            min_size = float(specs.get("minOrderSize", "0"))
            if min_size > 0 and size_f < min_size:
                name = specs.get("contractName", "").replace("USD", "")
                return {
                    "ok": False,
                    "error": f"Order size {size} is below the minimum for {name}.",
                    "suggestion": f"Minimum order size: **{specs['minOrderSize']}**. Try at least {specs['minOrderSize']}.",
                }
        except (ValueError, TypeError):
            pass

    # 2. Check max order size (balance check)
    try:
        max_info = await client.get_max_order_size(contract_id)
        data = max_info.get("data", max_info) if isinstance(max_info, dict) else {}
        max_buy = float(data.get("maxBuySize", "999999"))
        max_sell = float(data.get("maxSellSize", "999999"))
        max_allowed = max_buy if side.upper() == "BUY" else max_sell
        if size_f > max_allowed:
            return {
                "ok": False,
                "error": "Not enough balance for this trade.",
                "suggestion": f"Max available: **{max_allowed:.4f}**. Reduce size or deposit more USDT.",
            }
    except Exception as e:
        logger.warning(f"max-size check failed: {e}")

    return {"ok": True}


async def _run_cli(account_id: str, stark_key: str, args: list, timeout: int = 30) -> dict:
    """Run edgex-cli with credentials and return parsed JSON or error dict."""
    import os
    env = os.environ.copy()
    env["EDGEX_ACCOUNT_ID"] = str(account_id)
    env["EDGEX_STARK_PRIVATE_KEY"] = f"0x{stark_key}" if not stark_key.startswith("0x") else stark_key
    try:
        proc = await asyncio.create_subprocess_exec(
            EDGEX_CLI_PATH, "--json", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        out = stdout.decode().strip()
        err = stderr.decode().strip()
        if proc.returncode == 0 and out:
            try:
                data = json.loads(out)
                if isinstance(data, dict):
                    data["code"] = "SUCCESS"
                return data
            except json.JSONDecodeError:
                return {"code": "SUCCESS", "raw": out}
        error_msg = err or out or "Unknown CLI error"
        # Extract bracketed error code if present
        if "[" in error_msg and "]" in error_msg:
            error_msg = error_msg.split("]", 1)[-1].strip()
        return {"code": "ERROR", "error": error_msg}
    except asyncio.TimeoutError:
        return {"code": "ERROR", "error": "CLI command timed out"}
    except Exception as e:
        return {"code": "ERROR", "error": str(e)}


async def place_order(client: Client, contract_id: str, side: str, size: str, price: str) -> dict:
    """Place a limit order via edgex-cli."""
    try:
        symbol = resolve_symbol(contract_id)
        side_word = "buy" if side.upper() == "BUY" else "sell"
        account_id = ""
        stark_key = ""
        try:
            account_id = str(client.internal_client.account_id)
            stark_key = client.internal_client.stark_pri_key
        except Exception:
            pass
        if not account_id or not stark_key:
            # Fallback to SDK
            order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
            return await client.create_limit_order(contract_id=contract_id, size=size, price=price, side=order_side)

        result = await _run_cli(account_id, stark_key, [
            "order", "create", symbol, side_word, "limit", size, "--price", price, "-y"
        ])
        return result
    except Exception as e:
        logger.error(f"place_order error: {e}")
        return {"code": "ERROR", "error": str(e)}


async def cancel_order(client: Client, account_id: str, order_id: str) -> dict:
    """Cancel an order."""
    try:
        from edgex_sdk import CancelOrderParams
        params = CancelOrderParams(order_id=order_id)
        result = await client.cancel_order(params)
        return result
    except Exception as e:
        logger.error(f"cancel_order error: {e}")
        return {"code": "ERROR", "error": str(e)}


async def close_position(client: Client, contract_id: str, position: dict) -> dict:
    """Close a position via edgex-cli market order. Auto-batches if margin insufficient."""
    try:
        symbol = resolve_symbol(contract_id)
        current_side = position.get("side", "")
        side_word = "sell" if current_side == "LONG" else "buy"
        total_size = abs(float(position.get("size", "0")))

        account_id = ""
        stark_key = ""
        try:
            account_id = str(client.internal_client.account_id)
            stark_key = client.internal_client.stark_pri_key
        except Exception as e:
            logger.warning(f"close_position: could not extract creds: {e}")
        logger.info(f"close_position: symbol={symbol}, side={side_word}, size={total_size}, has_creds={bool(account_id and stark_key)}")
        if not account_id or not stark_key:
            logger.warning("close_position: falling back to SDK (no CLI creds)")
            close_side = OrderSide.SELL if current_side == "LONG" else OrderSide.BUY
            return await client.create_market_order(contract_id=contract_id, size=str(total_size), side=close_side)

        # Get min order size for this contract
        specs = await get_contract_specs(client, contract_id)
        min_size = float(specs.get("minOrderSize", "300")) if specs else 300
        batch_size = max(min_size, total_size / 4)  # Close in up to 4 batches

        remaining = total_size
        closed = 0
        last_result = {}
        max_batches = 10

        logger.info(f"close_position: starting batch close, min_size={min_size}, batch_size={batch_size}")
        while remaining >= min_size and max_batches > 0:
            chunk = min(batch_size, remaining)
            if remaining - chunk < min_size and remaining - chunk > 0:
                chunk = remaining
            size_str = str(int(chunk)) if chunk == int(chunk) else str(chunk)
            cli_args = ["order", "create", symbol, side_word, "market", size_str, "-y"]
            logger.info(f"close_position: CLI args: {cli_args}")
            result = await _run_cli(account_id, stark_key, cli_args)
            logger.info(f"close_position: CLI result: {result}")
            last_result = result
            if result.get("code") == "SUCCESS":
                closed += chunk
                remaining -= chunk
                logger.info(f"Closed {chunk} {symbol}, remaining: {remaining}")
                if remaining > 0:
                    await asyncio.sleep(1)  # Let margin settle
            else:
                error = result.get("error", "")
                if "MARGIN" in error.upper() and batch_size > min_size:
                    batch_size = max(min_size, batch_size / 2)  # Reduce batch size
                    logger.warning(f"Margin error, reducing batch to {batch_size}")
                    continue
                break
            max_batches -= 1

        if closed > 0:
            return {"code": "SUCCESS", "data": {"closedSize": closed, "remaining": remaining, **last_result}}
        return last_result
    except Exception as e:
        logger.error(f"close_position error: {e}")
        return {"code": "ERROR", "error": str(e)}


async def get_order_history(client: Client, limit: int = 20) -> list:
    """Get recent order fill transactions."""
    try:
        from edgex_sdk.order.types import OrderFillTransactionParams
        params = OrderFillTransactionParams(size=str(limit))
        result = await client.get_order_fill_transactions(params)
        return result.get("data", {}).get("dataList", [])
    except Exception as e:
        logger.error(f"get_order_history error: {e}")
        try:
            from edgex_sdk.order.types import GetActiveOrderParams
            params = GetActiveOrderParams(size=str(limit))
            result = await client.get_active_orders(params)
            return result.get("data", {}).get("dataList", [])
        except Exception:
            return []


async def validate_credentials(account_id: str, stark_private_key: str) -> dict:
    """Validate edgeX credentials. Returns {valid: bool, error: str|None, data: dict|None}."""
    try:
        client = await create_client(account_id, stark_private_key)
        result = await client.get_account_asset()
        if result.get("code") == "SUCCESS":
            return {"valid": True, "error": None, "data": result.get("data")}
        else:
            msg = result.get("msg", "Unknown error")
            code = result.get("code", "")
            return {"valid": False, "error": f"{code}: {msg}"}
    except ValueError as e:
        error_str = str(e)
        if "ACCOUNT_ID_WHITELIST_ERROR" in error_str:
            return {"valid": False, "error": "This Account ID is not in the API whitelist. Please go to edgeX API Management and enable API access, or try your Main Account ID."}
        if "401" in error_str:
            return {"valid": False, "error": "Authentication failed. Please check your Account ID and L2 privateKey."}
        return {"valid": False, "error": f"Validation error: {error_str[:200]}"}
    except Exception as e:
        logger.error(f"validate_credentials error: {type(e).__name__}: {e}")
        return {"valid": False, "error": f"Connection error: {type(e).__name__}: {str(e)[:200]}"}
