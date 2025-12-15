import aiohttp, asyncio, os, structlog

BASE   = "https://data-api.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"  # Correct host for events endpoint
HEADERS = {
    "accept"     : "application/json",
    "user-agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "origin"     : "https://polymarket.com"
}

logger = structlog.get_logger()

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


async def fetch_trades_scanned(session, event_id: int, api_min_size_usd: float, pages: int = 5, limit: int = 100):
    """Scan multiple pages client-side and filter by size."""
    kept = []
    scanned = 0
    for offset in range(0, pages * limit, limit):
        url = f"{BASE}/trades"
        params = {"eventId": event_id, "limit": limit, "offset": offset}
        async with session.get(url, params=params, headers=HEADERS) as resp:
            if resp.status != 200:
                logger.warning("trades_fetch_failed", event_id=event_id, status=resp.status)
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
    logger.info("scan_summary", event_id=event_id, scanned=scanned, kept=len(kept), api_min_size_usd=api_min_size_usd, pages=pages)
    return kept


async def fetch_active_events(session, limit=20, offset=0):
    """Fetch active events - fallback to extracting from trades if /events endpoint unavailable."""
    # Try /events endpoint first (use gamma-api host)
    url = f"{GAMMA_BASE}/events"
    params = {
        "active": "true",
        "closed": "false",
        "limit": str(limit),
        "offset": str(offset),
        "order": "volume"
    }
    try:
        async with session.get(url, headers=HEADERS, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                logger.warning("events_endpoint_failed", status=resp.status)
    except Exception as e:
        logger.warning("events_endpoint_error", error=str(e))
    
    # Fallback: Extract unique events from recent trades
    logger.info("using_trades_fallback", message="Extracting events from trades endpoint")
    url = f"{BASE}/trades"
    params = {"limit": 200}  # Get more trades to find unique events
    async with session.get(url, headers=HEADERS, params=params) as resp:
        resp.raise_for_status()
        trades = await resp.json()
        
        # Extract unique events by conditionId
        seen_events = {}
        for trade in trades:
            condition_id = trade.get("conditionId")
            event_id = trade.get("eventId") or condition_id
            if condition_id and condition_id not in seen_events:
                seen_events[condition_id] = {
                    "id": event_id,
                    "conditionId": condition_id,
                    "title": trade.get("title", "Unknown"),
                    "slug": trade.get("slug", ""),
                    "eventSlug": trade.get("eventSlug", "")
                }
        
        # Return as list, limited to requested count
        events_list = list(seen_events.values())[offset:offset+limit]
        logger.info("extracted_events_from_trades", count=len(events_list))
        return events_list


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
