import aiohttp, asyncio, os, structlog, csv
from datetime import datetime

BASE   = "https://data-api.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"  # Correct host for events endpoint
HEADERS = {
    "accept"     : "application/json",
    "user-agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "origin"     : "https://polymarket.com"
}

logger = structlog.get_logger()


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
    log_scan_stats(event_id, scanned, len(kept), api_min_size_usd, pages, limit)
    return kept


async def fetch_top_markets(session, limit=20, offset=0):
    """
    Fetch top active markets from gamma-api and return conditionIds.
    This is the reliable bridge between Gamma → Data-API trades.
    """
    url = f"{GAMMA_BASE}/markets"
    params = {
        "active": "true",
        "closed": "false",
        "limit": str(limit),
        "offset": str(offset),
        "order": "volume"
    }
    async with session.get(url, headers=HEADERS, params=params) as resp:
        resp.raise_for_status()
        markets = await resp.json()

    out = []
    for m in markets:
        cid = m.get("conditionId") or m.get("condition_id")
        if cid:
            out.append({"conditionId": cid, "title": m.get("title", ""), "slug": m.get("slug", "")})
    logger.info("fetched_markets", count=len(out))
    return out


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
