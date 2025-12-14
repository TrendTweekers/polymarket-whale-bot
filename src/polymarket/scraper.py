import aiohttp, asyncio, os, structlog

BASE   = "https://data-api.polymarket.com"
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

async def main():
    async with aiohttp.ClientSession() as session:
        trades = await fetch_trades(session, event_id=16096, limit=10)
        for t in trades:
            print(t)

if __name__ == "__main__":
    asyncio.run(main())
