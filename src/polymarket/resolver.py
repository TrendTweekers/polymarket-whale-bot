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
        
        logger.info("resolve_once_started", open_trades_count=len(open_trades))
        
        # Create session for API calls
        async with aiohttp.ClientSession() as session:
            for trade in open_trades:
                event_id = trade.get("event_id") or trade.get("condition_id")
                market_id = trade.get("market_id")
                trade_id = trade.get("id")
                market_name = trade.get("market", "Unknown")[:50]
                
                if not event_id:
                    logger.warning("resolve_once_missing_event_id",
                                 trade_id=trade_id,
                                 market=market_name)
                    error_count += 1
                    try:
                        storage.write_resolution(trade_id, "ERROR", "Missing event_id")
                    except Exception as e:
                        logger.error("write_resolution_failed", trade_id=trade_id, error=str(e))
                    continue
                
                # Fetch outcome using provided function
                try:
                    outcome = await fetch_outcome_fn(session, event_id, market_id)
                except Exception as e:
                    logger.error("fetch_outcome_exception",
                               trade_id=trade_id,
                               event_id=event_id[:20] if event_id else "none",
                               market=market_name,
                               error=str(e))
                    error_count += 1
                    try:
                        storage.write_resolution(trade_id, "ERROR", f"Exception: {str(e)[:100]}")
                    except Exception:
                        pass
                    continue
                
                if outcome is None:
                    # Error fetching - log and continue
                    logger.warning("resolve_once_fetch_failed",
                                 trade_id=trade_id,
                                 event_id=event_id[:20] if event_id else "none",
                                 market=market_name)
                    error_count += 1
                    try:
                        storage.write_resolution(trade_id, "ERROR", "Failed to fetch market data")
                    except Exception as e:
                        logger.error("write_resolution_failed", trade_id=trade_id, error=str(e))
                    continue
                
                if not outcome.get("resolved"):
                    # Market not resolved yet - log check periodically
                    if trade_id and trade_id % 10 == 0:  # Log every 10th check
                        logger.debug("resolve_once_not_resolved",
                                   trade_id=trade_id,
                                   event_id=event_id[:20] if event_id else "none",
                                   market=market_name)
                    try:
                        storage.write_resolution(trade_id, "NOT_RESOLVED", "Market still active")
                    except Exception:
                        pass  # Don't fail on write_resolution errors
                    continue
                
                # Market is resolved - close the trade
                resolved_outcome_index = outcome.get("resolved_outcome_index")
                trade_outcome_index = trade.get("outcome_index")
                
                logger.info("resolve_once_market_resolved",
                           trade_id=trade_id,
                           event_id=event_id[:20] if event_id else "none",
                           market=market_name,
                           resolved_outcome_index=resolved_outcome_index,
                           trade_outcome_index=trade_outcome_index)
                
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
                try:
                    success = storage.mark_trade_resolved(
                        trade_id,
                        resolved_outcome_index or -1,
                        won,
                        1.0 if won else 0.0  # resolved_price for binary markets
                    )
                except Exception as e:
                    logger.error("mark_trade_resolved_exception",
                               trade_id=trade_id,
                               event_id=event_id[:20] if event_id else "none",
                               market=market_name,
                               error=str(e))
                    error_count += 1
                    continue
                
                if success:
                    resolved_count += 1
                    
                    logger.info("resolve_once_resolved_success",
                               trade_id=trade_id,
                               market=market_name,
                               won=won,
                               pnl_usd=pnl_usd)
                    
                    # Notify via Telegram
                    try:
                        from src.polymarket.telegram import send_telegram
                        outcome_name = outcome.get("resolved_outcome_name") or trade.get("outcome_name", "N/A")
                        pnl_emoji = "✅" if won else "❌"
                        
                        send_telegram(
                            f"{pnl_emoji} Paper trade resolved\n"
                            f"Market: {market_name}\n"
                            f"Outcome: {outcome_name}\n"
                            f"Result: {'WON' if won else 'LOST'}\n"
                            f"PnL: ${pnl_usd:.2f} USD"
                        )
                    except Exception as e:
                        logger.warning("telegram_notification_failed", trade_id=trade_id, error=str(e))
                else:
                    logger.error("mark_trade_resolved_failed",
                               trade_id=trade_id,
                               event_id=event_id[:20] if event_id else "none",
                               market=market_name)
                    error_count += 1
        
        logger.info("resolve_once_complete",
                   resolved_count=resolved_count,
                   error_count=error_count,
                   total_checked=len(open_trades))
        return (resolved_count, error_count)
        
    except Exception as e:
        logger.error(
            "resolve_once_failed",
            extra={
                "event": "resolve_once_failed",
                "error": str(e),
            },
            exc_info=True
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
            elif resolved == 0 and errors == 0:
                # Log periodically even when no resolutions (every 12 cycles = 1 hour if 5 min interval)
                cycle_count = getattr(run_resolver_loop, '_cycle_count', 0) + 1
                run_resolver_loop._cycle_count = cycle_count
                if cycle_count % 12 == 0:
                    logger.info("resolver_cycle_no_resolutions",
                              cycle_count=cycle_count,
                              interval_seconds=interval_seconds)
        except Exception as e:
            logger.error(
                "resolver_loop_error",
                extra={
                    "event": "resolver_loop_error",
                    "error": str(e),
                },
                exc_info=True
            )
        
        await asyncio.sleep(interval_seconds)


async def check_market_resolution(session: aiohttp.ClientSession, condition_id: str) -> Optional[Dict]:
    """
    Check if a market has resolved and return resolution details.
    
    First tries on-chain UMA OptimisticOracleV2 resolution, then falls back to API.
    
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
    # Try on-chain UMA resolution first
    question_id_from_api = None
    try:
        from src.polymarket.uma_resolver import check_uma_resolution
        
        # First, try to get market metadata from API to help UMA lookup
        market_title = None
        question_id_from_api = None
        end_date_iso = None
        try:
            from src.polymarket.scraper import HEADERS
            GAMMA_BASE = "https://gamma-api.polymarket.com"
            url = f"{GAMMA_BASE}/markets?conditionId={condition_id}"
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    market = None
                    if isinstance(data, list) and data:
                        market = data[0]
                    elif isinstance(data, dict) and "markets" in data and data["markets"]:
                        market = data["markets"][0]
                    elif isinstance(data, dict) and "id" in data:
                        market = data
                    
                    if market:
                        # Extract market title (for ancillaryData)
                        market_title = market.get("title") or market.get("question")
                        # Extract questionId (fallback)
                        question_id_from_api = market.get("questionId") or market.get("question_id")
                        # Extract end date (for timestamp)
                        end_date_iso = market.get("endDateIso") or market.get("endDate") or market.get("end_date")
        except Exception as e:
            logger.debug("uma_api_metadata_fetch_failed",
                        condition_id=condition_id[:20],
                        error=str(e))
        
        # Try UMA resolution with market metadata
        uma_result = check_uma_resolution(
            condition_id, 
            market_title=market_title,
            question_id_address=question_id_from_api,
            end_date_iso=end_date_iso
        )
        if uma_result and uma_result.get("resolved"):
            logger.info("uma_resolution_found",
                       condition_id=condition_id[:20],
                       winning_outcome_index=uma_result.get("winning_outcome_index"),
                       resolved_price=uma_result.get("resolved_price"))
            return uma_result
        elif uma_result:
            # UMA check succeeded but market not resolved yet
            logger.debug("uma_market_not_resolved",
                        condition_id=condition_id[:20])
    except ImportError:
        logger.debug("uma_resolver_not_available",
                    condition_id=condition_id[:20])
    except Exception as e:
        logger.debug("uma_resolution_check_failed",
                    condition_id=condition_id[:20],
                    error=str(e))
    
    # Fall back to API method
    try:
        # Use the same endpoint and headers as scraper.py
        from src.polymarket.scraper import HEADERS
        
        GAMMA_BASE = "https://gamma-api.polymarket.com"
        # Try to fetch market metadata from Gamma API
        url = f"{GAMMA_BASE}/markets?conditionId={condition_id}"
        
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
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
            
            # Validate we got the right market - check if title/slug matches expected
            # If API returns wrong market (e.g., all return same 2020 Biden market), log warning
            market_title = market.get("title", "").lower()
            market_slug = market.get("slug", "").lower()
            if "biden" in market_title or "coronavirus" in market_title or "2020" in str(market.get("endDate", "")):
                # This looks like the wrong market - API may have returned default
                logger.warning("resolver_wrong_market_returned",
                             condition_id=condition_id[:20],
                             returned_title=market.get("title", "N/A")[:50],
                             returned_slug=market.get("slug", "N/A")[:50],
                             returned_endDate=market.get("endDate", "N/A"))
                # Still check if it's resolved, but log the issue
            
            # Check for resolution indicators
            # Polymarket markets typically have:
            # - active: bool (false = resolved/closed)
            # - closed: bool (true = market closed, may be resolved)
            # - resolved: bool (explicit resolution flag)
            # - resolution: dict with outcome details
            # - outcomes: list with resolvedOutcomeIndex
            # - outcomePrices: ["0", "0"] when resolved (both outcomes priced at 0)
            
            active = market.get("active", True)
            closed = market.get("closed", False)
            resolved_flag = market.get("resolved", False)
            resolution = market.get("resolution")
            outcome_prices = market.get("outcomePrices", [])
            
            # Check if market is resolved
            # Market is resolved if:
            # 1. active is False
            # 2. closed is True AND outcomePrices show a winner (one price = 1.0)
            # 3. resolved flag is True
            # 4. resolution object exists
            # 5. outcomePrices has one outcome at 1.0 (winner)
            
            # Check outcomePrices for winner
            has_winner = False
            winning_idx_from_prices = None
            if outcome_prices:
                for idx, price_str in enumerate(outcome_prices):
                    try:
                        price = float(price_str)
                        if price == 1.0:
                            has_winner = True
                            winning_idx_from_prices = idx
                            break
                    except (ValueError, TypeError):
                        continue
            
            # Market is resolved if closed AND has a winner
            is_closed_with_winner = closed and has_winner
            
            if not active or is_closed_with_winner or resolved_flag or resolution:
                # Market is resolved - find winning outcome
                winning_outcome_index = None
                resolved_price = 0.0
                
                # Try to get resolved outcome from various fields
                # Priority: outcomePrices (most reliable) > resolution object > resolvedOutcomeIndex
                if winning_idx_from_prices is not None:
                    # Use outcomePrices result (already found above)
                    winning_outcome_index = winning_idx_from_prices
                    resolved_price = 1.0
                elif resolution:
                    winning_outcome_index = resolution.get("outcome") or resolution.get("outcomeIndex")
                    if isinstance(winning_outcome_index, str):
                        try:
                            winning_outcome_index = int(winning_outcome_index)
                        except ValueError:
                            pass
                    resolved_price = 1.0 if winning_outcome_index is not None else 0.0
                elif "resolvedOutcomeIndex" in market:
                    winning_outcome_index = market.get("resolvedOutcomeIndex")
                    resolved_price = 1.0 if winning_outcome_index is not None else 0.0
                elif outcome_prices:
                    # Check outcomePrices again (fallback)
                    for idx, price_str in enumerate(outcome_prices):
                        try:
                            price = float(price_str)
                            if price == 1.0:
                                winning_outcome_index = idx
                                resolved_price = 1.0
                                break
                        except (ValueError, TypeError):
                            continue
                elif "outcomes" in market:
                    # Check outcomes for resolved status
                    outcomes = market.get("outcomes", [])
                    # Handle both dict and string outcomes
                    for idx, outcome in enumerate(outcomes):
                        if isinstance(outcome, dict):
                            if outcome.get("resolved") or outcome.get("winning"):
                                winning_outcome_index = idx
                                resolved_price = 1.0
                                break
                        elif isinstance(outcome, str):
                            # Sometimes outcomes are just strings like "Yes", "No"
                            # Check if this is a winning outcome by checking outcomePrices
                            outcome_prices = market.get("outcomePrices", [])
                            if idx < len(outcome_prices):
                                try:
                                    if float(outcome_prices[idx]) == 1.0:
                                        winning_outcome_index = idx
                                        resolved_price = 1.0
                                        break
                                except (ValueError, TypeError):
                                    continue
                
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
            
            # Check if market is closed (even if active=True, closed=True means it's done)
            closed = market.get("closed", False)
            outcome_prices = market.get("outcomePrices", [])
            
            # If closed and outcomePrices exist, check if resolved
            if closed and outcome_prices:
                # Find which outcome has price = 1.0 (winner)
                for idx, price_str in enumerate(outcome_prices):
                    try:
                        price = float(price_str)
                        if price == 1.0:
                            # Market is resolved!
                            resolution_time = market.get("closedTime") or market.get("endDate") or market.get("endDateIso")
                            return {
                                "resolved": True,
                                "winning_outcome_index": idx,
                                "resolved_price": 1.0,
                                "resolution_time": resolution_time,
                                "market_data": market
                            }
                    except (ValueError, TypeError):
                        continue
                
                # If closed but no winner found (both prices 0), market might be cancelled
                # or still resolving - treat as not resolved for now
                if all(float(p) == 0.0 for p in outcome_prices if p):
                    logger.debug("market_closed_but_no_winner",
                               condition_id=condition_id[:20],
                               outcome_prices=outcome_prices)
            
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
            logger.debug("resolve_paper_trades_no_open_trades", count=0)
            return (0, 0)
        
        resolved_count = 0
        error_count = 0
        
        logger.info("resolve_paper_trades_started", 
                   open_trades_count=len(open_trades),
                   limit=limit)
        
        for trade in open_trades:
            event_id = trade.get("event_id") or trade.get("condition_id")
            trade_id = trade.get("id")
            market_name = trade.get("market", "Unknown")[:50]
            
            if not event_id:
                logger.warning("resolve_paper_trades_missing_event_id",
                             trade_id=trade_id,
                             market=market_name,
                             trade_keys=list(trade.keys()))
                error_count += 1
                try:
                    signal_store.write_resolution(
                        trade_id, 
                        "ERROR", 
                        "Missing event_id/condition_id"
                    )
                except Exception as e:
                    logger.error("write_resolution_failed", trade_id=trade_id, error=str(e))
                continue
            
            # Check market resolution
            try:
                resolution = await check_market_resolution(session, event_id)
            except Exception as e:
                logger.error("check_market_resolution_exception",
                           trade_id=trade_id,
                           event_id=event_id[:20] if event_id else "none",
                           market=market_name,
                           error=str(e))
                error_count += 1
                try:
                    signal_store.write_resolution(
                        trade_id, 
                        "ERROR", 
                        f"Exception checking resolution: {str(e)[:100]}"
                    )
                except Exception:
                    pass
                continue
            
            if resolution is None:
                # Error checking - log and continue
                logger.warning("resolve_paper_trades_api_failed",
                             trade_id=trade_id,
                             event_id=event_id[:20] if event_id else "none",
                             market=market_name)
                error_count += 1
                try:
                    signal_store.write_resolution(
                        trade_id, 
                        "ERROR", 
                        "Failed to fetch market data from API"
                    )
                except Exception as e:
                    logger.error("write_resolution_failed", trade_id=trade_id, error=str(e))
                continue
            
            if not resolution.get("resolved"):
                # Market not resolved yet - log check periodically (every 10th check to avoid spam)
                if trade_id % 10 == 0:  # Log every 10th check
                    logger.debug("resolve_paper_trades_not_resolved",
                               trade_id=trade_id,
                               event_id=event_id[:20] if event_id else "none",
                               market=market_name)
                try:
                    signal_store.write_resolution(
                        trade_id,
                        "PENDING",
                        "Market still active"
                    )
                except Exception:
                    pass  # Don't fail on write_resolution errors
                continue
            
            # Market is resolved - close the trade
            winning_outcome_index = resolution.get("winning_outcome_index")
            resolved_price = resolution.get("resolved_price", 0.0)
            trade_outcome_index = trade.get("outcome_index")
            
            logger.info("resolve_paper_trades_market_resolved",
                       trade_id=trade_id,
                       event_id=event_id[:20] if event_id else "none",
                       market=market_name,
                       winning_outcome_index=winning_outcome_index,
                       trade_outcome_index=trade_outcome_index,
                       resolved_price=resolved_price)
            
            # Determine if we won
            # We win if the winning outcome matches our trade outcome
            won = (winning_outcome_index is not None and 
                   trade_outcome_index is not None and
                   winning_outcome_index == trade_outcome_index)
            
            # Mark trade as resolved
            try:
                success = signal_store.mark_trade_resolved(
                    trade_id,
                    winning_outcome_index or -1,
                    won,
                    resolved_price
                )
            except Exception as e:
                logger.error("mark_trade_resolved_exception",
                           trade_id=trade_id,
                           event_id=event_id[:20] if event_id else "none",
                           market=market_name,
                           error=str(e))
                error_count += 1
                continue
            
            if success:
                resolved_count += 1
                
                logger.info("resolve_paper_trades_resolved_success",
                           trade_id=trade_id,
                           market=market_name,
                           won=won,
                           winning_outcome_index=winning_outcome_index,
                           trade_outcome_index=trade_outcome_index)
                
                # Notify via Telegram
                try:
                    from src.polymarket.telegram import send_telegram
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
                except Exception as e:
                    logger.warning("telegram_notification_failed", trade_id=trade_id, error=str(e))
            else:
                logger.error("mark_trade_resolved_failed",
                           trade_id=trade_id,
                           event_id=event_id[:20] if event_id else "none",
                           market=market_name)
                error_count += 1
        
        logger.info("resolve_paper_trades_complete",
                   resolved_count=resolved_count,
                   error_count=error_count,
                   total_checked=len(open_trades))
        return (resolved_count, error_count)
        
    except Exception as e:
        logger.error(
            "resolve_paper_trades_failed",
            extra={
                "event": "resolve_paper_trades_failed",
                "error": str(e),
            },
            exc_info=True
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
    
    cycle_count = 0
    while True:
        try:
            resolved, errors = await resolve_paper_trades(session, signal_store)
            cycle_count += 1
            if resolved > 0 or errors > 0:
                logger.info("resolver_cycle_complete", 
                          resolved=resolved, 
                          errors=errors,
                          cycle_count=cycle_count)
            elif resolved == 0 and errors == 0:
                # Log periodically even when no resolutions (every 12 cycles = 1 hour if 5 min interval)
                if cycle_count % 12 == 0:
                    logger.info("resolver_cycle_no_resolutions",
                              cycle_count=cycle_count,
                              interval_seconds=interval_seconds)
        except Exception as e:
            logger.error(
                "resolver_loop_error",
                extra={
                    "event": "resolver_loop_error",
                    "error": str(e),
                },
                exc_info=True
            )
        
        await asyncio.sleep(interval_seconds)

