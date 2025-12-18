# src/polymarket/resolver.py
"""
Market resolution checker for paper trading.
Periodically checks if markets have resolved and closes paper trades.
Uses existing scraper functions to fetch market state.
"""
import aiohttp
import asyncio
import structlog
from typing import Optional, Dict, Tuple
from datetime import datetime

logger = structlog.get_logger()


async def fetch_outcome(session: aiohttp.ClientSession, event_id: str, market_id: str = None) -> Optional[Dict]:
    """
    Fetch market outcome/resolution using existing scraper functions.
    Uses the same Gamma API endpoint that scraper.py uses.
    
    Args:
        session: aiohttp session
        event_id: Condition ID or event ID
        market_id: Optional market ID (not used, kept for compatibility)
        
    Returns:
        Dict with:
        - resolved: bool
        - resolved_outcome_index: int or None
        - resolved_outcome_name: str or None
        Or None on error
    """
    try:
        # Use the same endpoint and headers as scraper.py
        from src.polymarket.scraper import HEADERS
        
        GAMMA_BASE = "https://gamma-api.polymarket.com"
        url = f"{GAMMA_BASE}/markets?conditionId={event_id}"
        
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                logger.debug("fetch_outcome_api_failed", 
                           event_id=event_id[:20] if event_id else "unknown",
                           status=resp.status)
                return None
            
            data = await resp.json()
        
        # Handle different response formats (same as scraper.py)
        market = None
        if isinstance(data, list) and len(data) > 0:
            market = data[0]
        elif isinstance(data, dict) and "markets" in data and isinstance(data["markets"], list) and data["markets"]:
            market = data["markets"][0]
        elif isinstance(data, dict) and "id" in data:
            market = data
        
        if not isinstance(market, dict):
            return None
        
        # Check for resolution indicators
        active = market.get("active", True)
        resolved_flag = market.get("resolved", False)
        resolution = market.get("resolution")
        
        # Check if market is resolved
        if not active or resolved_flag or resolution:
            # Market is resolved - find winning outcome
            winning_outcome_index = None
            winning_outcome_name = None
            
            # Try to get resolved outcome from various fields
            if resolution:
                winning_outcome_index = resolution.get("outcome")
                if isinstance(winning_outcome_index, str):
                    # Try to parse as int
                    try:
                        winning_outcome_index = int(winning_outcome_index)
                    except ValueError:
                        pass
                # Get outcome name from outcomes list
                outcomes = market.get("outcomes", [])
                if winning_outcome_index is not None and isinstance(winning_outcome_index, int):
                    if winning_outcome_index < len(outcomes):
                        winning_outcome_name = outcomes[winning_outcome_index].get("name") or outcomes[winning_outcome_index].get("title", "")
            
            elif "resolvedOutcomeIndex" in market:
                winning_outcome_index = market.get("resolvedOutcomeIndex")
                outcomes = market.get("outcomes", [])
                if winning_outcome_index is not None and isinstance(winning_outcome_index, int):
                    if winning_outcome_index < len(outcomes):
                        winning_outcome_name = outcomes[winning_outcome_index].get("name") or outcomes[winning_outcome_index].get("title", "")
            
            elif "outcomes" in market:
                # Check outcomes for resolved status
                outcomes = market.get("outcomes", [])
                for idx, outcome in enumerate(outcomes):
                    if outcome.get("resolved") or outcome.get("winning"):
                        winning_outcome_index = idx
                        winning_outcome_name = outcome.get("name") or outcome.get("title", "")
                        break
            
            return {
                "resolved": True,
                "resolved_outcome_index": winning_outcome_index,
                "resolved_outcome_name": winning_outcome_name or ""
            }
        
        # Market is still active
        return {
            "resolved": False,
            "resolved_outcome_index": None,
            "resolved_outcome_name": None
        }
        
    except Exception as e:
        logger.warning("fetch_outcome_failed", 
                      event_id=event_id[:20] if event_id else "unknown",
                      error=str(e))
        return None


async def resolve_once(storage, fetch_outcome_fn) -> Tuple[int, int]:
    """
    Resolve open paper trades once.
    
    Args:
        storage: SignalStore instance
        fetch_outcome_fn: Function that takes (session, event_id, market_id) and returns outcome dict
        
    Returns:
        Tuple of (resolved_count, error_count)
    """
    try:
        open_trades = storage.get_open_paper_trades(limit=100)
        
        if not open_trades:
            return (0, 0)
        
        resolved_count = 0
        error_count = 0
        
        # Create session for API calls
        async with aiohttp.ClientSession() as session:
            for trade in open_trades:
                event_id = trade.get("event_id")
                market_id = trade.get("market_id")
                
                if not event_id:
                    error_count += 1
                    storage.write_resolution(trade["id"], "ERROR", "Missing event_id")
                    continue
                
                # Fetch outcome using provided function
                outcome = await fetch_outcome_fn(session, event_id, market_id)
                
                if outcome is None:
                    # Error fetching - log and continue
                    storage.write_resolution(trade["id"], "ERROR", "Failed to fetch market data")
                    error_count += 1
                    continue
                
                if not outcome.get("resolved"):
                    # Market not resolved yet - log check and continue
                    storage.write_resolution(trade["id"], "NOT_RESOLVED", "Market still active")
                    continue
                
                # Market is resolved - close the trade
                resolved_outcome_index = outcome.get("resolved_outcome_index")
                trade_outcome_index = trade.get("outcome_index")
                
                # Determine if we won (outcome indices match)
                won = (resolved_outcome_index is not None and 
                       trade_outcome_index is not None and
                       resolved_outcome_index == trade_outcome_index)
                
                # Compute PnL
                stake_usd = trade.get("stake_usd", 0.0)
                entry_price = trade.get("entry_price", 0.0)
                
                if won and entry_price and entry_price > 0:
                    # Binary payout approximation: +stake_usd * ((1/entry_price) - 1)
                    pnl_usd = stake_usd * ((1.0 / entry_price) - 1.0)
                else:
                    # Lost - lose the stake
                    pnl_usd = -stake_usd
                
                # Mark trade as resolved
                success = storage.mark_trade_resolved(
                    trade["id"],
                    resolved_outcome_index or -1,
                    won,
                    1.0 if won else 0.0  # resolved_price for binary markets
                )
                
                if success:
                    resolved_count += 1
                    
                    # Notify via Telegram
                    from src.polymarket.telegram import send_telegram
                    market_name = trade.get("market", "Unknown")[:50]
                    outcome_name = outcome.get("resolved_outcome_name") or trade.get("outcome_name", "N/A")
                    pnl_emoji = "✅" if won else "❌"
                    
                    send_telegram(
                        f"{pnl_emoji} Paper trade resolved\n"
                        f"Market: {market_name}\n"
                        f"Outcome: {outcome_name}\n"
                        f"Result: {'WON' if won else 'LOST'}\n"
                        f"PnL: ${pnl_usd:.2f} USD"
                    )
                else:
                    error_count += 1
        
        return (resolved_count, error_count)
        
    except Exception as e:
        logger.error(
            "resolve_once_failed",
            extra={
                "event": "resolve_once_failed",
                "error": str(e),
            }
        )
        return (0, 1)


async def run_resolver_loop(storage, fetch_outcome_fn, interval_seconds: int):
    """
    Run resolver loop periodically.
    
    Args:
        storage: SignalStore instance
        fetch_outcome_fn: Function that fetches market outcome
        interval_seconds: How often to check for resolutions
    """
    logger.info("resolver_loop_started", interval_seconds=interval_seconds)
    
    while True:
        try:
            resolved, errors = await resolve_once(storage, fetch_outcome_fn)
            if resolved > 0 or errors > 0:
                logger.info("resolver_cycle_complete", 
                          resolved=resolved, 
                          errors=errors)
        except Exception as e:
            logger.error(
                "resolver_loop_error",
                extra={
                    "event": "resolver_loop_error",
                    "error": str(e),
                }
            )
        
        await asyncio.sleep(interval_seconds)
    """
    Check if a market has resolved and return resolution details.
    
    Args:
        session: aiohttp session
        condition_id: Market condition ID
        
    Returns:
        Resolution dict with:
        - resolved: bool
        - winning_outcome_index: int or None
        - resolved_price: float (typically 1.0 for win, 0.0 for loss)
        - resolution_time: str or None
        Or None if market not found or error
    """
    try:
        # Try to fetch market metadata from Gamma API
        url = f"{GAMMA_BASE}/markets?conditionId={condition_id}"
        
        async with session.get(url, headers=HEADERS, timeout=10) as resp:
            if resp.status != 200:
                logger.debug("resolver_market_fetch_failed", 
                           condition_id=condition_id[:20], 
                           status=resp.status)
                return None
            
            data = await resp.json()
            
            # Handle different response formats
            markets = []
            if isinstance(data, list):
                markets = data
            elif isinstance(data, dict):
                if "markets" in data:
                    markets = data["markets"]
                elif "value" in data:
                    markets = data["value"]
                else:
                    markets = [data] if "id" in data else []
            
            if not markets:
                return None
            
            market = markets[0]
            
            # Check for resolution indicators
            # Polymarket markets typically have:
            # - active: bool (false = resolved/closed)
            # - resolved: bool (explicit resolution flag)
            # - resolution: dict with outcome details
            # - outcomes: list with resolvedOutcomeIndex
            
            active = market.get("active", True)
            resolved_flag = market.get("resolved", False)
            resolution = market.get("resolution")
            
            # Check if market is resolved
            if not active or resolved_flag or resolution:
                # Market is resolved - find winning outcome
                winning_outcome_index = None
                resolved_price = 0.0
                
                # Try to get resolved outcome from various fields
                if resolution:
                    winning_outcome_index = resolution.get("outcome")
                    resolved_price = 1.0 if winning_outcome_index is not None else 0.0
                elif "resolvedOutcomeIndex" in market:
                    winning_outcome_index = market.get("resolvedOutcomeIndex")
                    resolved_price = 1.0 if winning_outcome_index is not None else 0.0
                elif "outcomes" in market:
                    # Check outcomes for resolved status
                    outcomes = market.get("outcomes", [])
                    for idx, outcome in enumerate(outcomes):
                        if outcome.get("resolved") or outcome.get("winning"):
                            winning_outcome_index = idx
                            resolved_price = 1.0
                            break
                
                # Get resolution time
                resolution_time = None
                if resolution and "timestamp" in resolution:
                    resolution_time = resolution["timestamp"]
                elif "resolvedAt" in market:
                    resolution_time = market["resolvedAt"]
                elif "endDate" in market:
                    resolution_time = market["endDate"]
                
                return {
                    "resolved": True,
                    "winning_outcome_index": winning_outcome_index,
                    "resolved_price": resolved_price,
                    "resolution_time": resolution_time,
                    "market_data": market
                }
            
            # Market is still active
            return {
                "resolved": False,
                "winning_outcome_index": None,
                "resolved_price": None,
                "resolution_time": None,
                "market_data": market
            }
            
    except Exception as e:
        logger.warning("resolver_check_failed", 
                      condition_id=condition_id[:20] if condition_id else "unknown",
                      error=str(e))
        return None


async def resolve_paper_trades(session: aiohttp.ClientSession, signal_store, limit: int = 100):
    """
    Check and resolve open paper trades.
    
    Args:
        session: aiohttp session
        signal_store: SignalStore instance
        limit: Maximum number of trades to check
        
    Returns:
        Tuple of (resolved_count, error_count)
    """
    try:
        open_trades = signal_store.get_open_paper_trades(limit=limit)
        
        if not open_trades:
            return (0, 0)
        
        resolved_count = 0
        error_count = 0
        
        for trade in open_trades:
            event_id = trade.get("event_id")
            if not event_id:
                error_count += 1
                continue
            
            # Check market resolution
            resolution = await check_market_resolution(session, event_id)
            
            if resolution is None:
                # Error checking - log and continue
                signal_store.write_resolution(
                    trade["id"], 
                    "ERROR", 
                    "Failed to fetch market data"
                )
                error_count += 1
                continue
            
            if not resolution.get("resolved"):
                # Market not resolved yet - log check and continue
                signal_store.write_resolution(
                    trade["id"],
                    "PENDING",
                    "Market still active"
                )
                continue
            
            # Market is resolved - close the trade
            winning_outcome_index = resolution.get("winning_outcome_index")
            resolved_price = resolution.get("resolved_price", 0.0)
            trade_outcome_index = trade.get("outcome_index")
            
            # Determine if we won
            # We win if the winning outcome matches our trade outcome
            won = (winning_outcome_index is not None and 
                   trade_outcome_index is not None and
                   winning_outcome_index == trade_outcome_index)
            
            # Mark trade as resolved
            success = signal_store.mark_trade_resolved(
                trade["id"],
                winning_outcome_index or -1,
                won,
                resolved_price
            )
            
            if success:
                resolved_count += 1
                
                # Notify via Telegram
                from src.polymarket.telegram import send_telegram
                market_name = trade.get("market", "Unknown")[:50]
                pnl_emoji = "✅" if won else "❌"
                
                # Compute PnL for notification
                stake_usd = trade.get("stake_usd", 0.0)
                entry_price = trade.get("entry_price", 0.0)
                if won and entry_price and entry_price > 0:
                    pnl_usd = stake_usd * (resolved_price - entry_price) / entry_price
                else:
                    pnl_usd = -stake_usd if not won else (stake_usd * (1.0 - entry_price) if entry_price else stake_usd)
                
                send_telegram(
                    f"{pnl_emoji} Paper trade resolved\n"
                    f"Market: {market_name}\n"
                    f"Outcome: {trade.get('outcome_name', 'N/A')}\n"
                    f"Result: {'WON' if won else 'LOST'}\n"
                    f"PnL: ${pnl_usd:.2f} USD"
                )
            else:
                error_count += 1
        
        return (resolved_count, error_count)
        
    except Exception as e:
        logger.error(
            "resolve_paper_trades_failed",
            extra={
                "event": "resolve_paper_trades_failed",
                "error": str(e),
            }
        )
        return (0, 1)


async def resolver_loop(session: aiohttp.ClientSession, signal_store, interval_seconds: int):
    """
    Main resolver loop that runs periodically.
    
    Args:
        session: aiohttp session
        signal_store: SignalStore instance
        interval_seconds: How often to check for resolutions
    """
    logger.info("resolver_loop_started", interval_seconds=interval_seconds)
    
    while True:
        try:
            resolved, errors = await resolve_paper_trades(session, signal_store)
            if resolved > 0 or errors > 0:
                logger.info("resolver_cycle_complete", 
                          resolved=resolved, 
                          errors=errors)
        except Exception as e:
            logger.error(
                "resolver_loop_error",
                extra={
                    "event": "resolver_loop_error",
                    "error": str(e),
                }
            )
        
        await asyncio.sleep(interval_seconds)

