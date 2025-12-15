"""
Polymarket Whale Signal Engine
Polls trades, scores whales, and logs signals to CSV and console.
"""

import asyncio
import aiohttp
import structlog
import csv
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from collections import defaultdict
import json

# Load environment variables (dotenv loaded in main if available)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # Environment variables can be set directly

# Import our modules
import sys
import os

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(parent_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.polymarket.scraper import fetch_recent_trades, fetch_top_markets, fetch_trades, fetch_trades_scanned, BASE, HEADERS
from src.polymarket.profiler import get_whale_stats
from src.polymarket.score import whale_score, whitelist_whales

# Telegram removed - paper trading mode (CSV + console logging only)

logger = structlog.get_logger()

# Configuration
POLL_INTERVAL_SECONDS = 30
MIN_WHALE_SCORE = 0.70
MIN_DISCOUNT_PCT = 2.0  # Temporarily lowered for data collection (was 5.0 production)
MIN_ORDERBOOK_DEPTH_MULTIPLIER = 3.0
CONFLICT_WINDOW_MINUTES = 5
MAX_SIGNALS_PER_DAY = 3
MAX_DAILY_LOSS_USD = 50.0
MAX_BANKROLL_PCT_PER_TRADE = 5.0

# Two-tier thresholds (env-driven)
API_MIN_SIZE_USD = float(os.getenv("API_MIN_SIZE_USD", "1000"))  # API filter (lower for data collection)
SIGNAL_MIN_SIZE_USD = float(os.getenv("SIGNAL_MIN_SIZE_USD", "10000"))  # Signal gate (production threshold)
MIN_SIZE_USD = SIGNAL_MIN_SIZE_USD  # Backward compatibility

# State tracking
whitelist_cache: Dict[str, Dict] = {}  # {wallet: {stats, score, category}}
recent_signals: List[Dict] = []  # Track signals sent today
daily_loss_usd = 0.0
conflicting_whales: Dict[str, datetime] = {}  # {wallet: timestamp} for opposite side trades


async def get_orderbook_depth(session: aiohttp.ClientSession, condition_id: str, size: float) -> float:
    """
    Fetch orderbook depth for a condition.
    Returns depth ratio (available_size / required_size).
    """
    # Simplified: assume depth is sufficient if we can't fetch it
    # In production, this would call the orderbook API
    try:
        # Placeholder: would call actual orderbook endpoint
        # For now, return a conservative estimate
        return 5.0  # Assume 5x depth available
    except Exception as e:
        logger.warning("orderbook_depth_fetch_failed", error=str(e))
        return 0.0


def get_category_from_trade(trade: Dict) -> str:
    """Extract category from trade data."""
    # Try to infer from slug or title
    slug = trade.get("slug", "").lower()
    title = trade.get("title", "").lower()
    
    if any(word in slug or word in title for word in ["bitcoin", "crypto", "ethereum", "btc", "eth"]):
        return "crypto"
    elif any(word in slug or word in title for word in ["election", "president", "vote", "poll"]):
        return "elections"
    elif any(word in slug or word in title for word in ["sport", "nfl", "nba", "soccer", "football"]):
        return "sports"
    elif any(word in slug or word in title for word in ["country", "geo", "nation", "state"]):
        return "geo"
    else:
        return "crypto"  # Default


async def ensure_whale_whitelisted(session: aiohttp.ClientSession, wallet: str, category: str) -> Optional[Dict]:
    """
    Ensure whale is in whitelist cache. Fetch stats if needed.
    Returns whale dict with score if whitelisted, None otherwise.
    """
    if wallet in whitelist_cache:
        whale = whitelist_cache[wallet]
        if whale["score"] >= MIN_WHALE_SCORE:
            return whale
        return None
    
    # Fetch stats
    try:
        stats = await get_whale_stats(wallet, session)
        score = whale_score(stats, category)
        
        whale = {
            "wallet": wallet,
            "stats": stats,
            "score": score,
            "category": category
        }
        
        whitelist_cache[wallet] = whale
        
        if score >= MIN_WHALE_SCORE:
            logger.info("whale_whitelisted", wallet=wallet[:20], score=score, category=category)
            return whale
        else:
            logger.debug("whale_below_threshold", wallet=wallet[:20], score=score)
            return None
    except Exception as e:
        logger.error("whale_stats_fetch_failed", wallet=wallet[:20], error=str(e))
        return None


def check_daily_limits() -> tuple[bool, str]:
    """Check if we've hit daily limits. Returns (can_proceed, reason)."""
    if len(recent_signals) >= MAX_SIGNALS_PER_DAY:
        return False, f"Daily signal limit reached ({MAX_SIGNALS_PER_DAY})"
    
    if daily_loss_usd >= MAX_DAILY_LOSS_USD:
        return False, f"Daily loss limit reached (${MAX_DAILY_LOSS_USD})"
    
    return True, ""


def check_conflicting_whale(wallet: str, side: str) -> bool:
    """
    Check if there's a conflicting whale trade (opposite side) within conflict window.
    """
    if side != "BUY":
        return False  # Only check BUY side conflicts
    
    # Check for SELL trades from same whale recently
    if wallet in conflicting_whales:
        conflict_time = conflicting_whales[wallet]
        if datetime.now() - conflict_time < timedelta(minutes=CONFLICT_WINDOW_MINUTES):
            return True
    
    return False


def calculate_discount(whale_entry_price: float, current_price: float) -> float:
    """Calculate discount percentage."""
    if whale_entry_price == 0:
        return 0.0
    return ((whale_entry_price - current_price) / whale_entry_price) * 100.0


async def process_trade(session: aiohttp.ClientSession, trade: Dict) -> Optional[Dict]:
    """
    Process a trade and generate signal if conditions are met.
    Returns signal dict if generated, None otherwise.
    """
    # Check daily limits
    can_proceed, reason = check_daily_limits()
    if not can_proceed:
        logger.debug("trade_rejected", reason="daily_limit", details=reason)
        return None
    
    wallet = trade.get("proxyWallet") or trade.get("makerAddress", "")
    if not wallet:
        logger.debug("trade_rejected", reason="no_wallet")
        return None
    
    side = trade.get("side", "BUY")
    if side != "BUY":
        logger.debug("trade_rejected", reason="wrong_side", side=side)
        return None
    
    # Check for conflicting whale
    if check_conflicting_whale(wallet, side):
        logger.debug("conflicting_whale", wallet=wallet[:20])
        return None
    
    # Get category
    category = get_category_from_trade(trade)
    
    # Ensure whale is whitelisted
    whale = await ensure_whale_whitelisted(session, wallet, category)
    if not whale:
        logger.debug("trade_rejected", reason="whale_not_whitelisted", wallet=wallet[:8], category=category)
        return None
    
    # Calculate discount
    whale_entry_price = trade.get("price", 0.0)
    current_price = whale_entry_price  # In production, fetch from orderbook
    discount_pct = calculate_discount(whale_entry_price, current_price)
    
    # Log ALL whale activity for analysis (before filtering)
    size = trade.get("size", 0.0)
    size_usd = size * whale_entry_price
    market_id = trade.get("conditionId", trade.get("slug", "unknown"))
    logger.debug("whale_activity", wallet=wallet[:20], score=whale["score"], discount=discount_pct, size_usd=size_usd)
    log_all_activity(market_id, wallet, whale["score"], discount_pct, size_usd)
    
    if discount_pct < MIN_DISCOUNT_PCT:
        logger.debug("trade_rejected", reason="below_discount", discount=discount_pct, wallet=wallet[:8], score=whale["score"])
        return None
    
    # Check orderbook depth
    depth_ratio = await get_orderbook_depth(session, trade.get("conditionId", ""), size)
    
    if depth_ratio < MIN_ORDERBOOK_DEPTH_MULTIPLIER:
        logger.debug("trade_rejected", reason="insufficient_depth", depth=depth_ratio, wallet=wallet[:8])
        return None
    
    # Generate signal
    signal = {
        "timestamp": datetime.now().isoformat(),
        "wallet": wallet,
        "whale_score": whale["score"],
        "category": category,
        "market": trade.get("title", "Unknown"),
        "slug": trade.get("slug", ""),
        "condition_id": trade.get("conditionId", ""),
        "whale_entry_price": whale_entry_price,
        "current_price": current_price,
        "discount_pct": discount_pct,
        "size": size,
        "trade_value_usd": size * whale_entry_price,
        "orderbook_depth_ratio": depth_ratio,
        "transaction_hash": trade.get("transactionHash", ""),
    }
    
    return signal


def log_all_activity(market_id: str, whale_wallet: str, score: float, discount: float, size_usd: float):
    """Log ALL whale activity for analysis, not just signals."""
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    today = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(log_dir, f"activity_{today}.csv")
    
    file_exists = os.path.exists(path)
    
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:  # Write header if new file
            writer.writerow(["timestamp", "market_id", "wallet", "score", "discount_pct", "size_usd"])
        writer.writerow([datetime.now().isoformat(), market_id, whale_wallet, score, discount, size_usd])


def log_signal_to_csv(signal: Dict):
    """Log signal to CSV file."""
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"signals_{date_str}.csv")
    
    file_exists = os.path.exists(log_file)
    
    with open(log_file, "a", newline="") as f:
        fieldnames = [
            "timestamp", "wallet", "whale_score", "category", "market", "slug",
            "condition_id", "whale_entry_price", "current_price", "discount_pct",
            "size", "trade_value_usd", "orderbook_depth_ratio", "transaction_hash"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        if not file_exists:
            writer.writeheader()
        
        writer.writerow(signal)


# Telegram functions removed - paper trading mode (CSV + console logging only)

async def main_loop():
    """Main polling loop - polls top 20 active markets by volume (gamma-api → conditionId bridge)."""
    logger.info("engine_started", poll_interval=POLL_INTERVAL_SECONDS, mode="multi_event")
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 1. Fetch top 20 active markets by volume (gamma-api → conditionId bridge)
                markets = await fetch_top_markets(session, limit=20, offset=0)
                
                if not markets:
                    logger.warning("no_markets_found")
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue
                
                logger.info("fetched_markets", count=len(markets))
                
                # 2. Poll trades for each market using conditionId
                total_trades_processed = 0
                for m in markets:
                    try:
                        event_id = m["conditionId"]  # conditionId (0x...) used as 'market' param in Data-API
                        if not event_id:
                            logger.debug("market_missing_conditionId", market=m.get("title", "unknown"))
                            continue
                        
                        # Fetch trades for this market (client-side scanning, 5 pages)
                        trades = await fetch_trades_scanned(session, event_id, API_MIN_SIZE_USD, pages=5, limit=100)
                        
                        # Process each trade (filter by SIGNAL_MIN_SIZE_USD for production signals)
                        for trade in trades:
                            # Signal gate: only process trades ≥ $10k for signals
                            size = trade.get("size", 0.0)
                            price = trade.get("price", 0.0)
                            size_usd = size * price
                            
                            if size_usd < SIGNAL_MIN_SIZE_USD:
                                logger.debug("trade_rejected", reason="below_signal_threshold", size_usd=size_usd, signal_threshold=SIGNAL_MIN_SIZE_USD)
                                continue
                            
                            signal = await process_trade(session, trade)
                            total_trades_processed += 1
                            
                            if signal:
                                # Log signal to CSV
                                log_signal_to_csv(signal)
                                recent_signals.append(signal)
                                
                                # Console log
                                logger.info("signal_generated", 
                                           wallet=signal['wallet'][:20],
                                           discount=signal['discount_pct'],
                                           market=signal['market'][:50],
                                           event_id=event_id)
                    except Exception as e:
                        logger.error("market_processing_error", 
                                    conditionId=m.get("conditionId", "unknown"), 
                                    error=str(e))
                        continue
                
                logger.info("processing_complete", 
                           markets=len(markets), 
                           trades_processed=total_trades_processed)
                
                # Clean up old conflicting whales
                cutoff_time = datetime.now() - timedelta(minutes=CONFLICT_WINDOW_MINUTES)
                conflicting_whales.clear()  # Simplified cleanup
                
            except Exception as e:
                logger.error("loop_error", error=str(e))
            
            # Wait before next poll
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def shutdown():
    """Cleanup on shutdown."""
    logger.info("engine_shutdown")


async def main():
    """Main entry point."""
    logger.info("engine_starting", mode="paper_trading", logging="csv_and_console")
    
    try:
        await main_loop()
    except KeyboardInterrupt:
        logger.info("shutdown_requested")
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())

