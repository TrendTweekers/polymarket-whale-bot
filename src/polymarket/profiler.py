import aiohttp
import asyncio
import structlog
import time
from typing import Dict, Optional

BASE = "https://data-api.polymarket.com"
HEADERS = {
    "accept": "application/json",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "origin": "https://polymarket.com"
}

logger = structlog.get_logger()

# Simple in-memory cache: {user_id: (data, timestamp)}
_cache: Dict[str, tuple] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour


async def get_whale_stats(user_id: str, session: Optional[aiohttp.ClientSession] = None) -> Dict:
    """
    Fetch whale stats for a given user_id.
    Caches responses for 1 hour to avoid re-fetching.
    
    Returns dict with:
    - total_profit
    - win_rate
    - max_drawdown
    - avg_hold_time_hours
    - trades_count
    - segmented_win_rate (elections / sports / crypto / geo)
    """
    # Check cache first
    if user_id in _cache:
        data, timestamp = _cache[user_id]
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            logger.info("cache hit", user_id=user_id)
            return data
    
    # Try multiple endpoint patterns (common REST API patterns)
    endpoints = [
        f"{BASE}/user-stats/{user_id}",
        f"{BASE}/users/{user_id}/stats",
        f"{BASE}/profile/{user_id}",
        f"{BASE}/account/{user_id}/stats",
    ]
    
    # Create session if not provided
    should_close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        should_close_session = True
    
    try:
        for url in endpoints:
            try:
                async with session.get(url, headers=HEADERS) as resp:
                    if resp.status == 200:
                        raw_data = await resp.json()
                        logger.info("fetched user stats", user_id=user_id, url=url, status=resp.status)
                        
                        # Parse and structure the response
                        stats = _parse_stats(raw_data)
                        
                        # Cache the result
                        _cache[user_id] = (stats, time.time())
                        
                        return stats
                    elif resp.status == 404:
                        continue  # Try next endpoint
                    else:
                        resp.raise_for_status()
            except aiohttp.ClientResponseError as e:
                if e.status == 404:
                    continue  # Try next endpoint
                raise
        
        # If all endpoints failed (404s), return empty stats structure for graceful degradation
        logger.debug("all endpoints returned 404", user_id=user_id, 
                     message="User stats endpoint not found. Using empty stats structure.")
        # Return empty stats structure for graceful degradation
        stats = {
            "total_profit": 0.0,
            "win_rate": 0.0,
            "max_drawdown": 0.0,
            "avg_hold_time_hours": 0.0,
            "trades_count": 0,
            "segmented_win_rate": {
                "elections": 0.0,
                "sports": 0.0,
                "crypto": 0.0,
                "geo": 0.0,
            }
        }
        # Cache empty result to avoid repeated failed requests
        _cache[user_id] = (stats, time.time())
        return stats
    finally:
        if should_close_session:
            await session.close()


def _parse_stats(raw_data: dict) -> Dict:
    """
    Parse raw API response into structured stats dict.
    Adapts to actual API response structure.
    """
    stats = {
        "total_profit": raw_data.get("totalProfit", raw_data.get("total_profit", 0.0)),
        "win_rate": raw_data.get("winRate", raw_data.get("win_rate", 0.0)),
        "max_drawdown": raw_data.get("maxDrawdown", raw_data.get("max_drawdown", 0.0)),
        "avg_hold_time_hours": raw_data.get("avgHoldTimeHours", raw_data.get("avg_hold_time_hours", 0.0)),
        "trades_count": raw_data.get("tradesCount", raw_data.get("trades_count", 0)),
        "segmented_win_rate": {
            "elections": raw_data.get("segmentedWinRate", {}).get("elections", 0.0) if isinstance(raw_data.get("segmentedWinRate"), dict) else 0.0,
            "sports": raw_data.get("segmentedWinRate", {}).get("sports", 0.0) if isinstance(raw_data.get("segmentedWinRate"), dict) else 0.0,
            "crypto": raw_data.get("segmentedWinRate", {}).get("crypto", 0.0) if isinstance(raw_data.get("segmentedWinRate"), dict) else 0.0,
            "geo": raw_data.get("segmentedWinRate", {}).get("geo", 0.0) if isinstance(raw_data.get("segmentedWinRate"), dict) else 0.0,
        }
    }
    
    # Fallback: try to extract from nested structures
    if "segmentedWinRate" not in raw_data and "segmented_win_rate" not in raw_data:
        # Try alternative structures
        if "categoryStats" in raw_data:
            cat_stats = raw_data["categoryStats"]
            stats["segmented_win_rate"] = {
                "elections": cat_stats.get("elections", {}).get("winRate", 0.0),
                "sports": cat_stats.get("sports", {}).get("winRate", 0.0),
                "crypto": cat_stats.get("crypto", {}).get("winRate", 0.0),
                "geo": cat_stats.get("geo", {}).get("winRate", 0.0),
            }
    
    return stats


async def demo():
    """Demo function that prints stats for a sample wallet."""
    # Using a sample wallet address from the trades we saw earlier
    sample_wallet = "0x90aadb1c214783e4df1fce6aaa692fe637a01e72"
    
    async with aiohttp.ClientSession() as session:
        try:
            stats = await get_whale_stats(sample_wallet, session)
            print("\n" + "="*60)
            print(f"Whale Stats for: {sample_wallet}")
            print("="*60)
            print(f"Total Profit: ${stats['total_profit']:,.2f}")
            print(f"Win Rate: {stats['win_rate']:.2%}")
            print(f"Max Drawdown: {stats['max_drawdown']:.2%}")
            print(f"Avg Hold Time: {stats['avg_hold_time_hours']:.2f} hours")
            print(f"Trades Count: {stats['trades_count']:,}")
            print("\nSegmented Win Rate:")
            for category, rate in stats['segmented_win_rate'].items():
                print(f"  {category.capitalize()}: {rate:.2%}")
            print("="*60 + "\n")
        except Exception as e:
            logger.error("demo failed", error=str(e), wallet=sample_wallet)
            print(f"Error fetching stats: {e}")
            print("Note: This might fail if the API endpoint structure differs.")


if __name__ == "__main__":
    asyncio.run(demo())

