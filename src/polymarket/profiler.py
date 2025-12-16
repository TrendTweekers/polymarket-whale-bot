import os
import time
import math
import aiohttp
import structlog

logger = structlog.get_logger()

DATA_API_BASE = os.getenv("DATA_API_BASE", "https://data-api.polymarket.com").rstrip("/")

# 30 min cache to avoid re-fetching same wallet constantly
_STATS_CACHE = {}
_STATS_TTL_SEC = int(os.getenv("STATS_CACHE_TTL_SEC", "1800"))

def _now():
    return time.time()

async def _get_json(session: aiohttp.ClientSession, url: str):
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
        r.raise_for_status()
        return await r.json()

async def get_user_stats(session: aiohttp.ClientSession, wallet: str, limit: int = 100):
    """
    Returns:
      {
        "wallet": str,
        "trade_count_100": int,
        "total_usd_100": float,
        "max_trade_usd_100": float,
        "stats_missing": bool,
        "reason": str
      }
    """
    wallet = wallet.lower()

    cached = _STATS_CACHE.get(wallet)
    if cached and (_now() - cached["ts"]) < _STATS_TTL_SEC:
        return cached["data"]

    url = f"{DATA_API_BASE}/trades?user={wallet}&limit={limit}&offset=0&takerOnly=true"

    try:
        data = await _get_json(session, url)
        # Handle both dict with 'value' key and direct list responses
        if isinstance(data, list):
            rows = data
        else:
            rows = data.get("value") or []
    except Exception as e:
        out = {
            "wallet": wallet,
            "trade_count_100": 0,
            "total_usd_100": 0.0,
            "max_trade_usd_100": 0.0,
            "stats_missing": True,
            "reason": f"fetch_error:{type(e).__name__}",
        }
        _STATS_CACHE[wallet] = {"ts": _now(), "data": out}
        return out

    # data-api /trades rows include: size, price. We'll treat size*price as USDC notionals.
    total_usd = 0.0
    max_usd = 0.0
    
    try:
        for t in rows:
            try:
                # Use 'side', 'size', 'price' directly as per API docs
                # Use 'proxyWallet' instead of 'makerAddress'
                size = float(t.get("size") or 0.0)
                price = float(t.get("price") or 0.0)
                usd = max(0.0, size * price)
            except (KeyError, AttributeError, TypeError) as e:
                logger.debug("stats_parse_error", 
                           wallet=wallet[:10], 
                           error=str(e), 
                           error_type=type(e).__name__,
                           response_sample=str(t)[:200] if t else "empty")
                usd = 0.0

            total_usd += usd
            if usd > max_usd:
                max_usd = usd
    except (KeyError, AttributeError, TypeError) as e:
        logger.debug("stats_parse_error", 
                   wallet=wallet[:10], 
                   error=str(e), 
                   error_type=type(e).__name__,
                   response_sample=str(rows[:2]) if rows else "empty")
        # Continue with empty stats
        total_usd = 0.0
        max_usd = 0.0

    out = {
        "wallet": wallet,
        "trade_count_100": int(len(rows)),
        "total_usd_100": float(total_usd),
        "max_trade_usd_100": float(max_usd),
        "stats_missing": (len(rows) == 0),
        "reason": ("no_trades" if len(rows) == 0 else "ok"),
    }

    _STATS_CACHE[wallet] = {"ts": _now(), "data": out}
    return out

def whale_score_from_stats(stats: dict) -> float:
    """
    Score 0..1 using log scaling.
    """
    trade_count = float(stats.get("trade_count_100") or 0.0)
    total_usd = float(stats.get("total_usd_100") or 0.0)
    max_usd = float(stats.get("max_trade_usd_100") or 0.0)

    score_total = math.log10(total_usd + 1.0) / 6.0   # ~1 around 1M
    score_max   = math.log10(max_usd + 1.0) / 6.0
    score_cnt   = trade_count / 50.0

    s = 0.55 * score_total + 0.35 * score_max + 0.10 * score_cnt
    if s < 0.0:
        return 0.0
    if s > 1.0:
        return 1.0
    return float(s)
