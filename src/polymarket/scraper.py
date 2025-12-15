import aiohttp, asyncio, os, structlog

BASE   = "https://data-api.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"  # Correct host for events endpoint
HEADERS = {
    "accept"     : "application/json",
    "user-agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "origin"     : "https://polymarket.com"
}

logger = structlog.get_logger()

async def fetch_trades(session, event_id, limit=100, offset=0):
    url = f"{BASE}/trades"
    params = {
        "eventId" : event_id,
        "limit"   : limit,
        "offset"  : offset,
        "takerOnly": "true",
        "side"    : "BUY"
    }
    async with session.get(url, headers=HEADERS, params=params) as resp:
        resp.raise_for_status()
        data = await resp.json()
        logger.info("fetched trades", event_id=event_id, count=len(data))
        return data


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
        "takerOnly": "true",
        "side": "BUY"
    }
    
    async with session.get(url, headers=HEADERS, params=params) as resp:
        resp.raise_for_status()
        all_trades = await resp.json()
        
        # Filter by size (size * price gives USD value)
        filtered_trades = []
        for trade in all_trades:
            size = trade.get("size", 0)
            price = trade.get("price", 0)
            trade_value_usd = size * price
            
            if trade_value_usd >= min_size_usd:
                filtered_trades.append(trade)
        
        logger.info("fetched recent trades", 
                   total=len(all_trades), 
                   filtered=len(filtered_trades),
                   min_size_usd=min_size_usd)
        return filtered_trades

async def main():
    async with aiohttp.ClientSession() as session:
        # Test fetch_active_events
        events = await fetch_active_events(session, limit=5, offset=0)
        for e in events:
            print(e.get("id", "N/A"), e.get("title", "N/A"), e.get("volume24hr", "N/A"))

if __name__ == "__main__":
    asyncio.run(main())
