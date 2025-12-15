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
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "2.0"))  # Temporarily lowered for data collection (was 5.0 production)
MIN_ORDERBOOK_DEPTH_MULTIPLIER = 3.0
CONFLICT_WINDOW_MINUTES = 5
MAX_SIGNALS_PER_DAY = int(os.getenv("DAILY_SIGNAL_LIMIT", "3"))  # Daily signal limit (env-configurable)
MAX_DAILY_LOSS_USD = 50.0
MAX_BANKROLL_PCT_PER_TRADE = 5.0

# Data collection mode flags (disable blockers temporarily)
WHITELIST_ONLY = False  # disable whitelist gate for now
BYPASS_SCORE_ON_STATS_FAIL = True  # allow clustering when stats API fails

# Two-tier thresholds (env-driven)
API_MIN_SIZE_USD = float(os.getenv("API_MIN_SIZE_USD", "1000"))  # API filter (lower for data collection)
SIGNAL_MIN_SIZE_USD = float(os.getenv("SIGNAL_MIN_SIZE_USD", "10000"))  # Signal gate (production threshold)
MIN_SIZE_USD = SIGNAL_MIN_SIZE_USD  # Backward compatibility

# State tracking
whitelist_cache: Dict[str, Dict] = {}  # {wallet: {stats, score, category}}
recent_signals: List[Dict] = []  # Track signals sent today
daily_loss_usd = 0.0
conflicting_whales: Dict[str, datetime] = {}  # {wallet: timestamp} for opposite side trades

# Whale clustering: group multiple trades from same wallet+market within time window
CLUSTER_WINDOW_MINUTES = 10
CLUSTER_MIN_USD = float(os.getenv("CLUSTER_MIN_USD", "10000.0"))  # Cumulative threshold for signal generation (env-configurable)
whale_clusters: Dict[str, Dict] = {}  # {wallet+market: {trades: [], total_usd: 0, first_trade_time: datetime, whale: {}, category: ""}}

# Filter rejection counters (for diagnostics)
rejected_below_cluster_min = 0
rejected_low_score = 0
rejected_low_discount = 0
rejected_depth = 0
rejected_conflicting = 0
rejected_daily_limit = 0
signals_generated = 0
trades_considered = 0

# Trade deduplication cache (prevent re-processing same trades)
SEEN_TRADE_KEYS: Set[str] = set()
SEEN_TRADE_KEYS_MAX = 250000  # prevent unbounded memory


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
    # Bypass whitelist check if disabled (data collection mode)
    if not WHITELIST_ONLY:
        # Return a dummy whale with score 1.0 to allow clustering
        return {
            "wallet": wallet,
            "stats": {},
            "score": 1.0,
            "category": category
        }
    
    if wallet in whitelist_cache:
        whale = whitelist_cache[wallet]
        if whale["score"] >= MIN_WHALE_SCORE:
            return whale
        return None
    
    # Fetch stats
    stats_lookup_failed = False
    try:
        stats = await get_whale_stats(wallet, session)
        score = whale_score(stats, category)
        
        # Bypass score check if stats lookup failed and bypass flag is set
        if BYPASS_SCORE_ON_STATS_FAIL and (not stats or stats.get("trades_count", 0) == 0):
            stats_lookup_failed = True
            score = 1.0  # allow clustering during data collection
        
        whale = {
            "wallet": wallet,
            "stats": stats,
            "score": score,
            "category": category
        }
        
        whitelist_cache[wallet] = whale
        
        if score >= MIN_WHALE_SCORE or stats_lookup_failed:
            logger.info("whale_whitelisted", wallet=wallet[:20], score=score, category=category)
            return whale
        else:
            logger.debug("whale_below_threshold", wallet=wallet[:20], score=score)
            return None
    except Exception as e:
        logger.error("whale_stats_fetch_failed", wallet=wallet[:20], error=str(e))
        # Bypass score check if stats lookup failed and bypass flag is set
        if BYPASS_SCORE_ON_STATS_FAIL:
            return {
                "wallet": wallet,
                "stats": {},
                "score": 1.0,
                "category": category
            }
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


def trade_key(trade: Dict) -> str:
    """
    Generate a stable unique key for a trade to enable deduplication.
    Prefers real unique IDs if present, falls back to composite key.
    """
    # Prefer real unique IDs if present
    tid = trade.get("id") or trade.get("tradeId") or trade.get("hash") or trade.get("transactionHash")
    if tid:
        return str(tid)
    
    # Fallback: stable composite key
    return "|".join([
        str(trade.get("conditionId") or ""),
        str(trade.get("timestamp") or trade.get("createdAt") or ""),
        str(trade.get("makerAddress") or trade.get("maker") or ""),
        str(trade.get("takerAddress") or trade.get("taker") or ""),
        str(trade.get("side") or ""),
        str(trade.get("price") or ""),
        str(trade.get("size") or ""),
    ])


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
        return None  # skip SELL trades quietly, no log spam
    
    # Check for conflicting whale
    if check_conflicting_whale(wallet, side):
        global rejected_conflicting
        rejected_conflicting += 1
        logger.debug("conflicting_whale", wallet=wallet[:20])
        return None
    
    # Get category
    category = get_category_from_trade(trade)
    
    # Ensure whale is whitelisted
    whale = await ensure_whale_whitelisted(session, wallet, category)
    if not whale:
        global rejected_low_score
        rejected_low_score += 1
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
    
    # Check if trade meets minimum size for clustering ($2k-$8k range)
    if size_usd < 2000.0:
        global rejected_below_cluster_min
        rejected_below_cluster_min += 1
        logger.debug("trade_rejected", reason="below_cluster_min", size_usd=size_usd, wallet=wallet[:8])
        return None
    
    if size_usd >= CLUSTER_MIN_USD:
        # Single trade already meets threshold - check other filters and generate signal directly
        if discount_pct < MIN_DISCOUNT_PCT:
            global rejected_low_discount
            rejected_low_discount += 1
            logger.debug("trade_rejected", reason="below_discount", discount=discount_pct, wallet=wallet[:8], score=whale["score"])
            return None
        
        # Check orderbook depth
        depth_ratio = await get_orderbook_depth(session, trade.get("conditionId", ""), size)
        
        if depth_ratio < MIN_ORDERBOOK_DEPTH_MULTIPLIER:
            global rejected_depth
            rejected_depth += 1
            logger.debug("trade_rejected", reason="insufficient_depth", depth=depth_ratio, wallet=wallet[:8])
            return None
        
        # Generate signal directly (single trade ≥ $10k)
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
            "trade_value_usd": size_usd,
            "orderbook_depth_ratio": depth_ratio,
            "transaction_hash": trade.get("transactionHash", ""),
            "cluster_trades_count": 1,
            "cluster_window_minutes": 0,
        }
        
        return signal
    else:
        # Trade is $2k-$8k range - add to cluster
        # Note: We'll check discount/depth when cluster completes
        cluster_signal = await add_trade_to_cluster(session, trade, whale, category)
        return cluster_signal


def get_cluster_key(wallet: str, market_id: str) -> str:
    """Generate unique key for wallet+market cluster."""
    return f"{wallet}:{market_id}"


async def add_trade_to_cluster(session: aiohttp.ClientSession, trade: Dict, whale: Dict, category: str) -> Optional[Dict]:
    """
    Add trade to cluster and generate signal if cluster reaches threshold.
    Returns signal dict if cluster threshold met, None otherwise.
    """
    wallet = trade.get("proxyWallet") or trade.get("makerAddress", "")
    market_id = trade.get("conditionId", trade.get("slug", "unknown"))
    cluster_key = get_cluster_key(wallet, market_id)
    
    size = trade.get("size", 0.0)
    price = trade.get("price", 0.0)
    trade_usd = size * price
    
    now = datetime.now()
    
    # Check if cluster exists and is still valid (within time window)
    if cluster_key in whale_clusters:
        cluster = whale_clusters[cluster_key]
        
        # DEDUPE: don't add the same trade to a cluster twice
        if cluster.get("triggered"):
            return None
        
        age_minutes = (now - cluster["first_trade_time"]).total_seconds() / 60
        
        if age_minutes > CLUSTER_WINDOW_MINUTES:
            # Cluster expired, remove it
            del whale_clusters[cluster_key]
            cluster = None
        else:
            cluster = whale_clusters[cluster_key]
            
            # DEDUPE: check if this trade is already in the cluster
            trade_k = trade_key(trade)
            existing_trade_keys = cluster.get("trade_keys", set())
            if trade_k in existing_trade_keys:
                return None  # Trade already in cluster, skip
            existing_trade_keys.add(trade_k)
            cluster["trade_keys"] = existing_trade_keys
    else:
        cluster = None
    
    # Create new cluster or add to existing
    if cluster is None:
        trade_k = trade_key(trade)
        whale_clusters[cluster_key] = {
            "trades": [],
            "total_usd": 0.0,
            "first_trade_time": now,
            "whale": whale,
            "category": category,
            "wallet": wallet,
            "market_id": market_id,
            "market_title": trade.get("title", "Unknown"),
            "slug": trade.get("slug", ""),
            "trade_keys": {trade_k},  # Track trade keys for deduplication
        }
        cluster = whale_clusters[cluster_key]
    
    # Add trade to cluster
    cluster["trades"].append(trade)
    cluster["total_usd"] += trade_usd
    
    logger.info("cluster_updated",
                key=cluster_key[:30],
                wallet=wallet[:20],
                market=market_id[:20],
                trades=len(cluster["trades"]),
                total_usd=cluster["total_usd"],
                trade_usd=trade_usd)
    
    # Check if cluster threshold met
    if cluster["total_usd"] >= CLUSTER_MIN_USD:
        # DEDUPE: skip if cluster already triggered
        if cluster.get("triggered"):
            return None
        
        # Generate signal from cluster
        signal = await generate_cluster_signal(session, cluster)
        
        # DEDUPE: mark cluster as triggered so we don't re-fire
        if signal:
            cluster["triggered"] = True
        
        # Remove cluster after signal generation (keep it briefly to prevent re-triggering)
        # Will be cleaned up by cleanup_expired_clusters()
        
        return signal
    
    return None


async def generate_cluster_signal(session: aiohttp.ClientSession, cluster: Dict) -> Optional[Dict]:
    """Generate signal from a completed whale cluster. Returns None if filters fail."""
    # Use the first trade for most fields, aggregate for size/price
    first_trade = cluster["trades"][0]
    last_trade = cluster["trades"][-1]
    
    # Calculate weighted average price
    total_size = sum(t.get("size", 0.0) for t in cluster["trades"])
    weighted_price = cluster["total_usd"] / total_size if total_size > 0 else first_trade.get("price", 0.0)
    
    # Calculate discount (use first trade price as entry, last as current for now)
    whale_entry_price = weighted_price
    current_price = weighted_price  # In production, fetch from orderbook
    discount_pct = calculate_discount(whale_entry_price, current_price)
    
    # Check discount filter
    if discount_pct < MIN_DISCOUNT_PCT:
        logger.debug("cluster_rejected", reason="below_discount", discount=discount_pct, wallet=cluster["wallet"][:8], cluster_total=cluster["total_usd"])
        return None
    
    # Get orderbook depth for total size
    depth_ratio = await get_orderbook_depth(session, cluster["market_id"], total_size)
    
    # Check depth filter
    if depth_ratio < MIN_ORDERBOOK_DEPTH_MULTIPLIER:
        logger.debug("cluster_rejected", reason="insufficient_depth", depth=depth_ratio, wallet=cluster["wallet"][:8], cluster_total=cluster["total_usd"])
        return None
    
    signal = {
        "timestamp": datetime.now().isoformat(),
        "wallet": cluster["wallet"],
        "whale_score": cluster["whale"]["score"],
        "category": cluster["category"],
        "market": cluster["market_title"],
        "slug": cluster["slug"],
        "condition_id": cluster["market_id"],
        "whale_entry_price": whale_entry_price,
        "current_price": current_price,
        "discount_pct": discount_pct,
        "size": total_size,
        "trade_value_usd": cluster["total_usd"],
        "orderbook_depth_ratio": depth_ratio,
        "transaction_hash": first_trade.get("transactionHash", ""),
        "cluster_trades_count": len(cluster["trades"]),
        "cluster_window_minutes": CLUSTER_WINDOW_MINUTES,
    }
    
    logger.info("cluster_signal_generated",
                wallet=cluster["wallet"][:20],
                market=cluster["market_title"][:50],
                cluster_total=cluster["total_usd"],
                trades_count=len(cluster["trades"]),
                discount=discount_pct)
    
    # DEDUPE: mark cluster as triggered so we don't re-fire
    cluster["triggered"] = True
    
    return signal


def cleanup_expired_clusters():
    """Remove clusters older than CLUSTER_WINDOW_MINUTES."""
    now = datetime.now()
    expired_keys = []
    
    for cluster_key, cluster in whale_clusters.items():
        age_minutes = (now - cluster["first_trade_time"]).total_seconds() / 60
        if age_minutes > CLUSTER_WINDOW_MINUTES:
            expired_keys.append(cluster_key)
    
    for key in expired_keys:
        cluster = whale_clusters[key]
        logger.debug("cluster_expired",
                     wallet=cluster["wallet"][:20],
                     market=cluster["market_id"][:20],
                     total_usd=cluster["total_usd"],
                     trades_count=len(cluster["trades"]))
        del whale_clusters[key]


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
            "size", "trade_value_usd", "orderbook_depth_ratio", "transaction_hash",
            "cluster_trades_count", "cluster_window_minutes"
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
                        
                        # Fetch trades for this market (client-side scanning, 25 pages = 2500 trades max)
                        trades = await fetch_trades_scanned(session, event_id, API_MIN_SIZE_USD, pages=25, limit=100)
                        
                        # Process each trade (use API_MIN_SIZE_USD filter, clustering happens inside process_trade)
                        for trade in trades:
                            # DEDUPE: skip duplicate trades (prevent re-processing same trades)
                            k = trade_key(trade)
                            if k in SEEN_TRADE_KEYS:
                                continue  # Skip already processed trades
                            SEEN_TRADE_KEYS.add(k)
                            
                            # Prevent unbounded memory growth
                            if len(SEEN_TRADE_KEYS) > SEEN_TRADE_KEYS_MAX:
                                SEEN_TRADE_KEYS.clear()
                            
                            # DO NOT reject here — clustering happens inside process_trade()
                            # Only apply the cheap API_MIN_SIZE_USD filter before calling process_trade.
                            size = trade.get("size", 0.0)
                            price = trade.get("price", 0.0)
                            size_usd = size * price
                            
                            if size_usd < API_MIN_SIZE_USD:
                                continue  # Skip trades below API filter threshold
                            
                            global trades_considered
                            trades_considered += 1
                            signal = await process_trade(session, trade)
                            total_trades_processed += 1
                            
                            if signal:
                                global signals_generated
                                signals_generated += 1
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
                
                # Log filter breakdown
                logger.info("gate_breakdown",
                           trades_considered=trades_considered,
                           rejected_below_cluster_min=rejected_below_cluster_min,
                           rejected_low_score=rejected_low_score,
                           rejected_low_discount=rejected_low_discount,
                           rejected_depth=rejected_depth,
                           rejected_conflicting=rejected_conflicting,
                           rejected_daily_limit=rejected_daily_limit,
                           signals_generated=signals_generated)
                
                # Clean up old conflicting whales
                cutoff_time = datetime.now() - timedelta(minutes=CONFLICT_WINDOW_MINUTES)
                conflicting_whales.clear()  # Simplified cleanup
                
                # Clean up expired clusters
                cleanup_expired_clusters()
                
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

