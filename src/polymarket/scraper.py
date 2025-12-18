import aiohttp, asyncio, os, structlog, csv, time
from datetime import datetime
from typing import Optional, Dict, Any

# Exclude categories (comma-separated from env, e.g., "sports,crypto")
EXCLUDE_CATEGORIES = {
    c.strip().lower()
    for c in os.getenv("EXCLUDE_CATEGORIES", "").split(",")
    if c.strip()
}

BASE   = "https://data-api.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"  # Correct host for events endpoint
HEADERS = {
    "accept"     : "application/json",
    "user-agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "origin"     : "https://polymarket.com"
}

logger = structlog.get_logger()

# Orderbook cache: key -> (timestamp, mid_price)
_ORDERBOOK_CACHE = {}
_ORDERBOOK_TTL_SECONDS = 10

# Cache for conditionId → clobTokenIds mapping
_CONDITION_TOKEN_CACHE = {}
_CONDITION_TOKEN_CACHE_TTL = 3600  # 1 hour

# Cache conditionId -> {"bestBid": float|None, "bestAsk": float|None, "ts": float}
_MARKET_QUOTE_CACHE: Dict[str, Dict[str, Any]] = {}
_MARKET_QUOTE_TTL_SECONDS = 10

def _to_float(x) -> Optional[float]:
    """Convert value to float, return None if conversion fails."""
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None

def _mid_from_bid_ask(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    """Calculate midpoint from bid/ask. Returns bid if ask missing, ask if bid missing, None if both missing."""
    if bid is None and ask is None:
        return None
    if bid is None:
        return ask
    if ask is None:
        return bid
    return (bid + ask) / 2.0

async def fetch_market_metadata_by_condition(session: aiohttp.ClientSession, condition_id: str) -> Optional[Dict]:
    """
    Fetch a single market by conditionId from Gamma and return full market metadata including category.
    Returns dict with: title, slug, category, etc.
    """
    url = f"https://gamma-api.polymarket.com/markets?conditionId={condition_id}"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return None
            data = await r.json()

        # Gamma can return a list or an object depending on filters.
        market = None
        if isinstance(data, list) and len(data) > 0:
            market = data[0]
        elif isinstance(data, dict) and "markets" in data and isinstance(data["markets"], list) and data["markets"]:
            market = data["markets"][0]
        elif isinstance(data, dict) and "id" in data:
            market = data

        if not isinstance(market, dict):
            return None

        # Return full market metadata
        return {
            "title": market.get("title", ""),
            "slug": market.get("slug", ""),
            "category": (market.get("category") or market.get("marketCategory") or "").lower().strip(),
            "conditionId": condition_id,
            # include common expiry fields for engine _days_to_expiry()
            "endDate": market.get("endDate"),
            "endDateIso": market.get("endDateIso") or market.get("end_date_iso"),
            "closeTime": market.get("closeTime") or market.get("close_time"),
            "resolutionTime": market.get("resolutionTime") or market.get("resolution_time"),
        }
    except Exception:
        return None

async def fetch_market_quote_by_condition(session: aiohttp.ClientSession, condition_id: str) -> Optional[Dict[str, Optional[float]]]:
    """
    Fetch a single market by conditionId from Gamma and return bestBid/bestAsk.
    """
    url = f"https://gamma-api.polymarket.com/markets?conditionId={condition_id}"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return None
            data = await r.json()

        # Gamma can return a list or an object depending on filters.
        market = None
        if isinstance(data, list) and len(data) > 0:
            market = data[0]
        elif isinstance(data, dict) and "markets" in data and isinstance(data["markets"], list) and data["markets"]:
            market = data["markets"][0]
        elif isinstance(data, dict) and "id" in data:
            market = data

        if not isinstance(market, dict):
            return None

        bid = _to_float(market.get("bestBid"))
        ask = _to_float(market.get("bestAsk"))
        return {"bestBid": bid, "bestAsk": ask}
    except Exception:
        return None

async def get_market_midpoint_cached(session: aiohttp.ClientSession, condition_id: str) -> Optional[float]:
    """
    Cached midpoint from Gamma bestBid/bestAsk, keyed by conditionId.
    Uses provided session for efficiency.
    """
    now = time.time()
    cached = _MARKET_QUOTE_CACHE.get(condition_id)
    if cached and (now - cached.get("ts", 0)) < _MARKET_QUOTE_TTL_SECONDS:
        return _mid_from_bid_ask(cached.get("bestBid"), cached.get("bestAsk"))

    q = await fetch_market_quote_by_condition(session, condition_id)
    if not q:
        _MARKET_QUOTE_CACHE[condition_id] = {"bestBid": None, "bestAsk": None, "ts": now}
        return None

    _MARKET_QUOTE_CACHE[condition_id] = {"bestBid": q["bestBid"], "bestAsk": q["bestAsk"], "ts": now}
    return _mid_from_bid_ask(q["bestBid"], q["bestAsk"])


def build_orderbook_url(market_id: str, token_id: Optional[str] = None) -> Optional[str]:
    """
    Build orderbook URL for Polymarket API.
    
    NOTE: Orderbook endpoints currently return 404. This function is kept for future use.
    For now, we use trade price as current_price proxy.
    
    Args:
        market_id: conditionId (market identifier)
        token_id: Optional token/outcome ID (if orderbook is per-token)
    
    Returns:
        Full orderbook URL or None if endpoint unavailable
    """
    # NOTE: Orderbook endpoints are not currently available (return 404)
    # Returning None to indicate endpoint unavailable
    # Alternative: Use trade price as current_price proxy
    return None
    
    # Future implementation when orderbook API is available:
    # if token_id:
    #     return f"{BASE}/orderbook/{market_id}/{token_id}"
    # else:
    #     return f"{BASE}/orderbook/{market_id}"


def log_scan_stats(market_id, scanned, kept, api_min_size_usd, pages, limit):
    """Log scan statistics to CSV for auditing."""
    os.makedirs("logs", exist_ok=True)
    fn = f"logs/scan_stats_{datetime.now().strftime('%Y-%m-%d')}.csv"
    new_file = not os.path.exists(fn)
    with open(fn, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["ts", "market_id", "scanned", "kept", "api_min_size_usd", "pages", "limit"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), market_id, scanned, kept, api_min_size_usd, pages, limit])


async def fetch_trades(session, event_id, limit=100, offset=0, min_size_usd=10000):
    """Fetch trades for an event (legacy function - use fetch_trades_scanned instead)."""
    url = f"{BASE}/trades"
    params = {
        "eventId": event_id,
        "limit": limit,
        "offset": offset
    }
    async with session.get(url, headers=HEADERS, params=params) as resp:
        resp.raise_for_status()
        data = await resp.json()
        logger.info("fetched trades", event_id=event_id, count=len(data))
        return data


def _trade_market_id(trade: dict) -> str:
    """Extract market_id from trade dict. Returns full ID (never truncated)."""
    market_obj = trade.get("market") if isinstance(trade.get("market"), dict) else {}
    return (
        str(trade.get("marketId") or trade.get("market_id") or trade.get("market") or "")
        or str(market_obj.get("id") or "")
        or ""
    ).strip()


def _trade_condition_id(trade: dict) -> str:
    """Extract condition_id from trade dict. Returns full ID (never truncated)."""
    market_obj = trade.get("market") if isinstance(trade.get("market"), dict) else {}
    condition_obj = trade.get("condition") if isinstance(trade.get("condition"), dict) else {}
    return (
        str(trade.get("conditionId") or trade.get("condition_id") or "")
        or str(condition_obj.get("id") or "")
        or str(market_obj.get("conditionId") or market_obj.get("condition_id") or "")
        or ""
    ).strip()


def _normalize_condition_id(cid: str) -> str:
    """
    Normalize condition_id for comparison (lowercase, strip, handle hex with/without 0x).
    NEVER truncates - returns full ID for accurate matching.
    """
    if not cid:
        return ""
    cid = str(cid).strip().lower()
    # Normalize hex: ensure 0x prefix for consistency
    if cid.startswith("0x"):
        return cid
    # Allow raw hex without 0x - add prefix
    if all(c in "0123456789abcdef" for c in cid):
        return "0x" + cid
    return cid


def filter_trades_for_market(trades: list[dict], requested_market_id: str, requested_condition_id: str) -> tuple[list[dict], int, int]:
    """
    Filter trades to only include those matching the requested market_id OR condition_id.
    Uses FULL normalized IDs for comparison (never truncated).
    Returns (kept_trades, mismatched_count, missing_ids_count) tuple.
    """
    want_mid = str(requested_market_id or "").strip().lower()
    want_cid = _normalize_condition_id(requested_condition_id or "")
    
    kept = []
    mismatched = 0
    missing_ids = 0
    
    for t in trades:
        got_mid = _trade_market_id(t).lower().strip()
        got_cid = _normalize_condition_id(_trade_condition_id(t))
        
        mid_ok = bool(want_mid and got_mid and got_mid == want_mid)
        cid_ok = bool(want_cid and got_cid and got_cid == want_cid)
        
        if mid_ok or cid_ok:
            kept.append(t)
        else:
            # Count separately so we can see what's going on
            if not got_mid and not got_cid:
                missing_ids += 1
            else:
                mismatched += 1
    
    return kept, mismatched, missing_ids


async def fetch_trades_scanned(
    session,
    *,
    market_id: Optional[str] = None,
    condition_id: Optional[str] = None,
    api_min_size_usd: float = 1000.0,
    pages: int = 3,
    limit: int = 100,
):
    """
    Fetch trades for ONE market using Data-API /trades endpoint.
    
    According to Polymarket docs, Data-API expects:
    - market = comma-separated list of condition IDs (0x... hex strings)
    - OR eventId = integer event IDs (mutually exclusive with market)
    
    We use the `market` parameter with the condition_id to scope trades.
    """
    kept = []
    scanned = 0
    
    # Normalize condition_id for market parameter (Data-API expects full 0x... hex)
    # IMPORTANT: market must be a single comma-separated string, not a list
    requested_condition = None
    if condition_id:
        requested_condition = _normalize_condition_id(condition_id)
    
    url = f"{BASE}/trades"
    
    for offset in range(0, pages * limit, limit):
        # Build params - market must be a STRING (comma-separated if multiple), not a list
        params = {
            "limit": limit,
            "offset": offset,
            "takerOnly": "true",
        }
        
        # IMPORTANT: Data-API expects `market` as a single comma-separated string of condition IDs
        # Do NOT send eventId, conditionId, condition_id, marketId, etc. - only market
        if requested_condition:
            params["market"] = requested_condition  # STRING, not list
        
        # Log request parameters for verification (right before request)
        if requested_condition:
            logger.info("trades_request_params",
                       market_param_head=requested_condition[:10],
                       market_param_tail=requested_condition[-10:],
                       market_param_len=len(requested_condition),
                       api_min_size_usd=api_min_size_usd,
                       pages=pages,
                       limit=limit,
                       offset=offset)
        
        async with session.get(url, params=params, headers=HEADERS) as resp:
            if resp.status != 200:
                logger.warning("trades_fetch_failed",
                             status=resp.status,
                             url=str(resp.url),
                             market_param_len=len(requested_condition) if requested_condition else 0)
                return kept
            
            trades = await resp.json()
            scanned += len(trades)
            
            for t in trades:
                size = float(t.get("size") or 0.0)
                price = float(t.get("price") or 0.0)
                usd = size * price
                if usd >= api_min_size_usd:
                    kept.append(t)
            
            if not trades:
                break  # no more pages
    
    # Safety net: filter trades by market_id OR condition_id to prevent leaks
    # (should be redundant if API scoping works, but keeps us safe)
    if market_id or requested_condition:
        # Debug: log what we have before filtering
        logger.debug("trade_filter_before",
                    scanned=scanned,
                    kept_before_usd_filter=len(kept),
                    requested_market_id=str(market_id) if market_id else "",
                    requested_condition_id_head=requested_condition[:10] if requested_condition else "")
        
        kept_trades, mismatched, missing_ids = filter_trades_for_market(kept, str(market_id) if market_id else "", requested_condition or "")
        
        # Debug: if no trades kept, show what IDs the trades actually have
        if len(kept_trades) == 0 and len(kept) > 0:
            sample_trade = kept[0]
            sample_market_id = _trade_market_id(sample_trade)
            sample_condition_id = _trade_condition_id(sample_trade)
            logger.warning("trade_filter_zero_kept_sample",
                         returned=scanned,
                         kept_before_filter=len(kept),
                         kept_after_filter=len(kept_trades),
                         requested_market_id=str(market_id) if market_id else "",
                         requested_condition_id_head=requested_condition[:10] if requested_condition else "",
                         requested_condition_id_tail=requested_condition[-10:] if requested_condition else "",
                         sample_trade_market_id=sample_market_id[:20] if sample_market_id else "none",
                         sample_trade_condition_id_head=sample_condition_id[:10] if sample_condition_id else "none",
                         sample_trade_condition_id_tail=sample_condition_id[-10:] if sample_condition_id else "none",
                         sample_trade_keys=list(sample_trade.keys())[:30])
        elif len(kept_trades) == 0 and scanned > 0:
            # No trades kept and none passed USD filter - log why
            logger.debug("trade_filter_no_usd_qualifiers",
                        scanned=scanned,
                        api_min_size_usd=api_min_size_usd,
                        kept_after_usd_filter=len(kept))
        
        logger.info("trade_market_filter",
                   returned=scanned,
                   kept=len(kept_trades),
                   mismatched=mismatched,
                   missing_ids=missing_ids,
                   requested_market_id=str(market_id) if market_id else "",
                   requested_condition_id_head=requested_condition[:10] if requested_condition else "",
                   requested_condition_id_tail=requested_condition[-10:] if requested_condition else "",
                   requested_len=len(requested_condition) if requested_condition else 0)
        
        kept = kept_trades
    
    logger.info("scan_summary",
               event_id=requested_condition or "none",
               scanned=scanned,
               kept=len(kept),
               api_min_size_usd=api_min_size_usd,
               pages=pages)
    
    return kept


async def fetch_midpoint_price(session: aiohttp.ClientSession, token_id: str) -> Optional[float]:
    """
    Fetch midpoint price from Polymarket CLOB API.
    
    Args:
        session: aiohttp ClientSession
        token_id: CLOB token ID (from trade or market mapping)
    
    Returns:
        Midpoint price (float) or None if fetch fails
    """
    try:
        url = f"https://clob.polymarket.com/midpoint?token_id={token_id}"
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                response_text = await r.text()
                logger.debug("midpoint_fetch_failed", 
                            token_id=token_id[:20], 
                            status=r.status, 
                            response=response_text[:100])
                return None
            
            # Midpoint endpoint returns a simple number or JSON with price field
            data = await r.json()
            
            # Handle different response shapes
            if isinstance(data, (int, float)):
                midpoint = float(data)
            elif isinstance(data, dict):
                midpoint = data.get("midpoint") or data.get("price") or data.get("mid")
                midpoint = float(midpoint) if midpoint is not None else None
            else:
                midpoint = None
            
            if midpoint is not None and midpoint > 0:
                logger.debug("midpoint_fetched", token_id=token_id[:20], midpoint=midpoint)
                return midpoint
            else:
                logger.debug("midpoint_invalid", token_id=token_id[:20], data=data)
                return None
                
    except Exception as e:
        logger.debug("midpoint_fetch_error", token_id=token_id[:20], error=str(e))
        return None


async def fetch_mid_price(session: aiohttp.ClientSession, orderbook_url: str) -> Optional[float]:
    """
    DEPRECATED: Use fetch_midpoint_price() instead.
    Kept for backward compatibility.
    """
    # This function is deprecated - orderbook endpoints return 404
    # Use fetch_midpoint_price() with token_id instead
    return None


async def get_midpoint_price_cached(session: aiohttp.ClientSession, token_id: str) -> Optional[float]:
    """
    Fetch midpoint price with caching. Uses token_id as cache key.
    """
    cache_key = f"midpoint_{token_id}"
    now = time.time()
    hit = _ORDERBOOK_CACHE.get(cache_key)
    if hit:
        ts, mid = hit
        if (now - ts) <= _ORDERBOOK_TTL_SECONDS:
            logger.debug("midpoint_cache_hit", token_id=token_id[:20])
            return mid

    mid = await fetch_midpoint_price(session, token_id)
    _ORDERBOOK_CACHE[cache_key] = (now, mid)
    return mid


async def get_mid_price_cached(session: aiohttp.ClientSession, cache_key: str, orderbook_url: str) -> Optional[float]:
    """
    DEPRECATED: Use get_midpoint_price_cached() instead.
    Kept for backward compatibility.
    """
    # This function is deprecated - orderbook endpoints return 404
    # Use get_midpoint_price_cached() with token_id instead
    return None


async def fetch_top_markets(session, limit=200, offset=0, order="volume", pages=1):
    """
    Fetch active markets from gamma-api.
    Returns conditionIds with clobTokenIds.
    This is the reliable bridge between Gamma → Data-API trades.
    
    Args:
        session: aiohttp session
        limit: Markets per page (default 200, max safe limit)
        offset: Starting offset for pagination
        order: Ordering strategy - "volume" (default, safe) or "closingSoon" (may cause 422)
        pages: Number of pages to fetch (default 1, increase for more coverage)
    """
    all_markets = []
    page_size = min(limit, 200)  # Keep page size reasonable to avoid API limits
    
    for page in range(pages):
        current_offset = offset + (page * page_size)
        url = f"{GAMMA_BASE}/markets"
        
        # Try with order parameter first (if specified)
        params_with_order = {
            "active": "true",
            "closed": "false",
            "limit": str(page_size),
            "offset": str(current_offset),
        }
        
        # Only add order if it's not "closingSoon" (which causes 422)
        if order and order != "closingSoon":
            params_with_order["order"] = order
        
        # Try fetch with order first, fallback to no order if 422
        page_markets = None
        try:
            async with session.get(url, headers=HEADERS, params=params_with_order) as resp:
                if resp.status == 422:
                    # 422 error - retry without order parameter
                    logger.debug("market_fetch_422_retry", page=page, order=order, retrying_without_order=True)
                    params_no_order = {
                        "active": "true",
                        "closed": "false",
                        "limit": str(page_size),
                        "offset": str(current_offset),
                    }
                    async with session.get(url, headers=HEADERS, params=params_no_order) as retry_resp:
                        retry_resp.raise_for_status()
                        page_markets = await retry_resp.json()
                else:
                    resp.raise_for_status()
                    page_markets = await resp.json()
        except Exception as e:
            logger.warning(
                "market_fetch_page_failed",
                extra={
                    "event": "market_fetch_page_failed",
                    "page": page,
                    "offset": current_offset,
                    "error": str(e),
                }
            )
            break
        
        if not page_markets:
            break  # No more markets
        all_markets.extend(page_markets)
        if len(page_markets) < page_size:
            break  # Last page
    
    markets = all_markets

    out = []
    for m in markets:
        # ---- Robust title/category extraction (Gamma fields vary) ----
        ev = m.get("event") if isinstance(m.get("event"), dict) else {}
        ev0 = (m.get("events") or [{}])[0] if isinstance(m.get("events"), list) and m.get("events") else {}
        
        raw_title = (
            m.get("title")
            or m.get("question")
            or m.get("name")
            or ev.get("title")
            or ev.get("name")
            or ev0.get("title")
            or ev0.get("name")
            or ""
        )
        
        market_category = (
            m.get("category")
            or m.get("marketCategory")
            or ev.get("category")
            or ev0.get("category")
            or ""
        )
        market_category = str(market_category).lower().strip()
        
        # Filter out excluded categories
        if market_category and market_category in EXCLUDE_CATEGORIES:
            continue  # Skip excluded categories
        
        # Extract condition_id from multiple possible fields (don't truncate!)
        condition_obj = m.get("condition") if isinstance(m.get("condition"), dict) else {}
        cid = (
            m.get("conditionId")
            or m.get("condition_id")
            or condition_obj.get("id")
            or condition_obj.get("conditionId")
            or ""
        )
        
        if cid:
            # Extract clobTokenIds (array of token IDs for YES/NO outcomes)
            clob_token_ids = m.get("clobTokenIds")
            if isinstance(clob_token_ids, str):
                # Parse JSON string if it's a string
                import json
                try:
                    clob_token_ids = json.loads(clob_token_ids)
                except:
                    clob_token_ids = []
            elif not isinstance(clob_token_ids, list):
                clob_token_ids = []
            
            # Cache conditionId → clobTokenIds mapping
            _CONDITION_TOKEN_CACHE[cid] = {
                "token_ids": clob_token_ids,
                "timestamp": time.time()
            }
            
            # Build market dict: keep full raw market object + normalized fields
            market_dict = dict(m)  # Keep everything from raw market object
            market_dict.update({
                "conditionId": cid,  # Ensure conditionId is set
                "title": raw_title,  # Normalized title
                "category": market_category,  # Normalized category
            })
            
            # Debug log to verify condition_id length
            logger.info("market_id_debug",
                       title=raw_title[:50] if raw_title else "",
                       condition_id=cid,
                       condition_id_len=len(cid) if cid else 0,
                       keys=list(m.keys())[:30])
            
            out.append(market_dict)
    logger.info("fetched_markets", count=len(out), excluded_categories=len(EXCLUDE_CATEGORIES))
    return out


def get_token_id_for_condition(condition_id: str, side: str = "BUY") -> Optional[str]:
    """
    Get token_id for a conditionId and side (BUY/SELL).
    Uses cached mapping from fetch_top_markets().
    
    Args:
        condition_id: Market conditionId
        side: Trade side (BUY/SELL) - typically BUY = YES token (index 0), SELL = NO token (index 1)
    
    Returns:
        Token ID string or None if not found
    """
    cached = _CONDITION_TOKEN_CACHE.get(condition_id)
    if cached:
        token_ids = cached.get("token_ids", [])
        if len(token_ids) >= 2:
            # BUY side typically uses first token (YES), SELL uses second (NO)
            # For BUY trades, we want the YES token (index 0)
            return str(token_ids[0]) if side == "BUY" else str(token_ids[1])
        elif len(token_ids) == 1:
            return str(token_ids[0])
    return None


async def fetch_recent_trades(session, min_size_usd=10000, limit=100):
    """
    Fetch recent trades filtered by minimum size.
    
    Args:
        session: aiohttp ClientSession
        min_size_usd: Minimum trade size in USD (default 10000)
        limit: Maximum number of trades to fetch
    
    Returns:
        List of trades with size >= min_size_usd
    """
    url = f"{BASE}/trades"
    params = {
        "limit": limit,
        "filterType": "CASH",
        "filterAmount": str(min_size_usd)
    }
    
    async with session.get(url, headers=HEADERS, params=params) as resp:
        resp.raise_for_status()
        trades = await resp.json()
        
        logger.info("fetched recent trades", 
                   count=len(trades),
                   min_size_usd=min_size_usd)
        return trades

async def main():
    async with aiohttp.ClientSession() as session:
        # Test fetch_active_events
        events = await fetch_active_events(session, limit=5, offset=0)
        for e in events:
            print(e.get("id", "N/A"), e.get("title", "N/A"), e.get("volume24hr", "N/A"))

if __name__ == "__main__":
    asyncio.run(main())
