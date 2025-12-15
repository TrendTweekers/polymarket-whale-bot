"""
Polymarket Whale Signal Engine
Polls trades, scores whales, and logs signals to CSV and console.
"""

import asyncio
import aiohttp
import structlog
import csv
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from collections import defaultdict
import json
import pandas as pd
from pathlib import Path

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

from src.polymarket.scraper import fetch_recent_trades, fetch_top_markets, fetch_trades, fetch_trades_scanned, get_midpoint_price_cached, get_token_id_for_condition, get_market_midpoint_cached, BASE, HEADERS
from src.polymarket.profiler import get_whale_stats
from src.polymarket.score import whale_score, whitelist_whales
from src.polymarket.telegram import notify_engine_start, notify_engine_stop, notify_signal, notify_phase1b_bypass, notify_csv_write_attempt, notify_csv_write_done
from src.polymarket.telegram_notify import SignalStats

# Configure logging level from environment (for filtering debug messages)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Setup file logging for console output
def setup_file_logging():
    """Configure logging to write to both console and daily log file."""
    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)
    
    # Create daily log file
    day = datetime.utcnow().strftime("%Y-%m-%d")
    log_file = Path("logs") / f"engine_{day}.log"
    
    # Configure Python logging to write to file
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    
    # Format: timestamp level message
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    
    # Get root logger and add file handler
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    
    return log_file

# Setup file logging
_log_file = setup_file_logging()

# Configure structlog to use standard library logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# Add console handler for structlog (for real-time viewing)
console_handler = logging.StreamHandler()
console_handler.setLevel(getattr(logging, LOG_LEVEL))
console_formatter = structlog.stdlib.ProcessorFormatter(
    processor=structlog.dev.ConsoleRenderer(),
    foreign_pre_chain=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
    ],
)
console_handler.setFormatter(console_formatter)

# Add console handler to root logger (file handler already added in setup_file_logging)
root_logger = logging.getLogger()
root_logger.addHandler(console_handler)

logger = structlog.get_logger()

# Configuration
POLL_INTERVAL_SECONDS = 30
MIN_WHALE_SCORE = float(os.getenv("MIN_WHALE_SCORE", "0.70"))  # Env-configurable
MIN_ORDERBOOK_DEPTH_MULTIPLIER = 3.0
CONFLICT_WINDOW_MINUTES = 5
MAX_SIGNALS_PER_DAY = int(os.getenv("DAILY_SIGNAL_LIMIT", "3"))  # Daily signal limit (env-configurable)
MAX_DAILY_LOSS_USD = 50.0
MAX_BANKROLL_PCT_PER_TRADE = 5.0

# Production mode configuration
PRODUCTION_MODE = os.getenv("PRODUCTION_MODE", "False").lower() == "true"

# Helper function for boolean environment variable parsing
def env_bool(name: str, default: bool) -> bool:
    """Parse environment variable as boolean."""
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")

# Exclude categories (comma-separated from env, e.g., "sports,crypto")
EXCLUDE_CATEGORIES = {
    c.strip().lower()
    for c in os.getenv("EXCLUDE_CATEGORIES", "").split(",")
    if c.strip()
}

# Data collection mode flags (disable blockers temporarily)
# WHITELIST_ONLY can be overridden via environment variable
WHITELIST_ONLY = env_bool("WHITELIST_ONLY", default=(PRODUCTION_MODE is True))

# Override other settings in production mode (unless explicitly set via env)
# MIN_DISCOUNT_PCT can be overridden via env even in production mode
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "2.0" if PRODUCTION_MODE else "2.0"))

if PRODUCTION_MODE:
    BYPASS_SCORE_ON_STATS_FAIL = False  # require valid stats in production
else:
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
CLUSTER_WINDOW_MINUTES = 5  # Reduced from 10 to 5 minutes
CLUSTER_MIN_TRADES = int(os.getenv("CLUSTER_MIN_TRADES", "3"))  # Minimum trades required per cluster (env-configurable)
CLUSTER_MIN_AVG_HOLD_MINUTES = int(os.getenv("CLUSTER_MIN_HOLD", "30"))  # Skip clusters with avg hold < X min (arb bot filter, env-configurable)
CLUSTER_MIN_USD = float(os.getenv("CLUSTER_MIN_USD", "10000.0"))  # Cumulative threshold for signal generation (env-configurable)
whale_clusters: Dict[str, Dict] = {}  # {wallet+market: {trades: [], total_usd: 0, first_trade_time: datetime, whale: {}, category: ""}}

# Filter rejection counters (for diagnostics)
rejected_below_cluster_min = 0
rejected_low_score = 0
rejected_low_discount = 0
rejected_score_missing = 0  # Score is None
rejected_discount_missing = 0  # Discount is None
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


def append_status_line(status: str) -> None:
    """Append a status line to the daily status log file."""
    Path("logs").mkdir(exist_ok=True)
    day = datetime.utcnow().strftime("%Y-%m-%d")
    path = Path("logs") / f"status_{day}.log"
    with path.open("a", encoding="utf-8") as f:
        f.write(status.rstrip() + "\n")


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


async def get_whale_with_score(session: aiohttp.ClientSession, wallet: str, category: str) -> Optional[Dict]:
    """
    Fetch whale stats and compute score. Does NOT enforce whitelist gate.
    Returns whale dict with score, or None if stats cannot be fetched.
    """
    # Check cache first
    if wallet in whitelist_cache:
        whale = whitelist_cache[wallet]
        return whale
    
    # Fetch stats
    stats = None
    score = None
    stats_lookup_failed = False
    
    try:
        stats = await get_whale_stats(wallet, session)
        if stats and stats.get("trades_count", 0) > 0:
            score = whale_score(stats, category)
        else:
            # Stats missing or empty - set score to None (will reject)
            stats_lookup_failed = True
            score = None
            logger.debug("whale_stats_missing", wallet=wallet[:20], reason="no_stats_or_zero_trades")
    except Exception as e:
        logger.error("whale_stats_fetch_failed", wallet=wallet[:20], error=str(e))
        stats_lookup_failed = True
        score = None
    
    # Reject if we can't get a valid score (unless bypass is enabled for data collection)
    if score is None:
        if BYPASS_SCORE_ON_STATS_FAIL:
            # Data collection mode: allow with low score (0.0) but log the issue
            score = 0.0
            logger.debug("whale_score_bypassed", wallet=wallet[:20], reason="stats_failed_but_bypass_enabled", score=score)
        else:
            # Production mode: reject
            logger.debug("whale_rejected", wallet=wallet[:20], reason="no_valid_score", stats_failed=stats_lookup_failed)
            return None
    
    whale = {
        "wallet": wallet,
        "stats": stats or {},
        "score": score,
        "category": category
    }
    
    whitelist_cache[wallet] = whale
    logger.debug("whale_score_computed", wallet=wallet[:20], score=score, category=category, stats_failed=stats_lookup_failed)
    return whale


async def ensure_whale_whitelisted(session: aiohttp.ClientSession, wallet: str, category: str) -> Optional[Dict]:
    """
    Ensure whale is in whitelist cache. Fetch stats if needed.
    Returns whale dict with score if whitelisted, None otherwise.
    """
    # Bypass whitelist check if disabled (data collection mode)
    # BUT: still require valid stats/score (don't default to 1.0)
    if not WHITELIST_ONLY:
        # Still fetch stats to get real score, but don't enforce whitelist gate
        # This allows data collection while maintaining score accuracy
        pass  # Continue to fetch stats below
    
    if wallet in whitelist_cache:
        whale = whitelist_cache[wallet]
        if WHITELIST_ONLY and whale["score"] < MIN_WHALE_SCORE:
            return None
        return whale
    
    # Fetch stats
    stats = None
    score = None
    stats_lookup_failed = False
    
    try:
        stats = await get_whale_stats(wallet, session)
        if stats and stats.get("trades_count", 0) > 0:
            score = whale_score(stats, category)
        else:
            # Stats missing or empty - set score to None (will reject)
            stats_lookup_failed = True
            score = None
            logger.debug("whale_stats_missing", wallet=wallet[:20], reason="no_stats_or_zero_trades")
    except Exception as e:
        logger.error("whale_stats_fetch_failed", wallet=wallet[:20], error=str(e))
        stats_lookup_failed = True
        score = None
    
    # Reject if we can't get a valid score (unless bypass is enabled for data collection)
    if score is None:
        if BYPASS_SCORE_ON_STATS_FAIL and not WHITELIST_ONLY:
            # Data collection mode: allow with low score (0.0) but log the issue
            score = 0.0
            logger.debug("whale_score_bypassed", wallet=wallet[:20], reason="stats_failed_but_bypass_enabled", score=score)
        else:
            # Production mode or whitelist enabled: reject
            logger.debug("whale_rejected", wallet=wallet[:20], reason="no_valid_score", stats_failed=stats_lookup_failed)
            return None
    
    whale = {
        "wallet": wallet,
        "stats": stats or {},
        "score": score,
        "category": category
    }
    
    whitelist_cache[wallet] = whale
    
    # Check score threshold
    if WHITELIST_ONLY and score < MIN_WHALE_SCORE:
        logger.debug("whale_below_threshold", wallet=wallet[:20], score=score, required=MIN_WHALE_SCORE)
        return None
    
    logger.info("whale_whitelisted", wallet=wallet[:20], score=score, category=category, stats_failed=stats_lookup_failed)
    return whale


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


def calculate_discount(whale_entry_price: float, current_price: float) -> Optional[float]:
    """
    Calculate discount percentage.
    Returns None if prices are missing/invalid (instead of silently returning 0.0).
    """
    # Reject if either price is missing or invalid
    if whale_entry_price is None or whale_entry_price <= 0:
        return None
    if current_price is None or current_price < 0:
        return None
    
    # Calculate discount
    discount = ((whale_entry_price - current_price) / whale_entry_price) * 100.0
    return discount


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
    # Declare all global variables at the top of the function
    global rejected_conflicting, rejected_low_score, rejected_discount_missing
    global rejected_below_cluster_min, rejected_low_discount, rejected_depth
    
    # Check daily limits
    can_proceed, reason = check_daily_limits()
    if not can_proceed:
        logger.debug("trade_rejected", reason="daily_limit", details=reason)
        return None
    
    wallet = trade.get("proxyWallet") or trade.get("makerAddress", "")
    if not wallet:
        logger.debug("trade_rejected", reason="no_wallet")
        return None
    
    # Exclude categories (early filter, before scoring/discount work)
    market_category = get_category_from_trade(trade).lower().strip()
    if market_category and market_category in EXCLUDE_CATEGORIES:
        logger.debug("trade_rejected", category=market_category, reason="excluded_category")
        return None
    
    side = trade.get("side", "BUY")
    if side != "BUY":
        return None  # skip SELL trades quietly, no log spam
    
    # Check for conflicting whale
    if check_conflicting_whale(wallet, side):
        rejected_conflicting += 1
        logger.debug("conflicting_whale", wallet=wallet[:20])
        return None
    
    # Get category
    category = get_category_from_trade(trade)
    
    # Get whale stats/score (whitelist check only if WHITELIST_ONLY is True)
    if WHITELIST_ONLY:
        whale = await ensure_whale_whitelisted(session, wallet, category)
        if not whale:
            rejected_low_score += 1
            logger.debug("trade_rejected", reason="whale_not_whitelisted", wallet=wallet[:8], category=category)
            return None
    else:
        # Whitelist disabled: just get score, don't enforce whitelist gate
        whale = await get_whale_with_score(session, wallet, category)
        if not whale:
            rejected_low_score += 1
            logger.debug("trade_rejected", reason="whale_score_unavailable", wallet=wallet[:8], category=category)
            return None
    
    # Calculate discount
    whale_entry_price = trade.get("price")
    if whale_entry_price is None or whale_entry_price <= 0:
        logger.debug("trade_rejected", reason="missing_entry_price", wallet=wallet[:8])
        return None
    
    # Fetch current price from CLOB midpoint endpoint using token_id
    condition_id = trade.get("conditionId", "")
    if not condition_id:
        logger.debug("trade_rejected", reason="missing_condition_id", wallet=wallet[:8])
        return None
    
    # Extract token_id from trade (Path A: direct from trade payload)
    token_id = (trade.get("tokenId") or trade.get("clobTokenId") or 
                trade.get("asset_id") or trade.get("outcomeId"))
    
    # Path B: If not in trade, get from conditionId → clobTokenIds mapping
    if not token_id:
        side = trade.get("side", "BUY")
        token_id = get_token_id_for_condition(condition_id, side)
    
    if not token_id:
        logger.debug("trade_rejected", reason="rejected_discount_missing", 
                    wallet=wallet[:8], condition_id=condition_id[:20], 
                    note="token_id_not_found_in_trade_or_cache")
        rejected_discount_missing += 1
        return None
    
    # Fetch midpoint price: try CLOB first, fallback to Gamma market bestBid/bestAsk
    current_price = await get_midpoint_price_cached(session, str(token_id))
    
    # Fallback to Gamma market midpoint if CLOB fails
    if current_price is None and condition_id:
        current_price = await get_market_midpoint_cached(session, condition_id)
    
    if current_price is None:
        # Phase 1b bypass: allow missing discount for calibration
        if os.getenv("PHASE1B_ALLOW_MISSING_DISCOUNT", "False") == "True":
            logger.warning("PHASE1B_USING_ZERO_DISCOUNT", wallet=wallet[:8], 
                         token_id=str(token_id)[:20] if token_id else None, 
                         condition_id=condition_id[:20], note="current_price_missing_using_entry_price")
            notify_phase1b_bypass(wallet, condition_id, "current_price_missing_using_entry_price")
            current_price = whale_entry_price  # Use entry price so discount = 0.0
        else:
            rejected_discount_missing += 1
            logger.debug("trade_rejected", reason="rejected_discount_missing", 
                        wallet=wallet[:8], token_id=str(token_id)[:20] if token_id else None, 
                        condition_id=condition_id[:20])
            return None
    
    # Calculate discount: entry_price vs current midpoint
    discount_pct = calculate_discount(whale_entry_price, current_price)
    
    # Reject if discount cannot be calculated
    if discount_pct is None:
        # Phase 1b bypass: allow missing discount for calibration
        if os.getenv("PHASE1B_ALLOW_MISSING_DISCOUNT", "False") == "True":
            logger.warning("PHASE1B_USING_ZERO_DISCOUNT", wallet=wallet[:8], 
                         entry_price=whale_entry_price, current_price=current_price,
                         note="discount_calc_returned_none_using_zero")
            notify_phase1b_bypass(wallet, condition_id, "discount_calc_returned_none_using_zero")
            discount_pct = 0.0
        else:
            rejected_discount_missing += 1
            logger.debug("trade_rejected", reason="rejected_discount_missing", 
                        wallet=wallet[:8], entry_price=whale_entry_price, current_price=current_price)
            return None
    
    # Log ALL whale activity for analysis (before filtering)
    size = trade.get("size", 0.0)
    size_usd = size * whale_entry_price
    market_id = trade.get("conditionId", trade.get("slug", "unknown"))
    logger.debug("whale_activity", wallet=wallet[:20], score=whale["score"], discount=discount_pct, size_usd=size_usd)
    log_all_activity(market_id, wallet, whale["score"], discount_pct, size_usd)
    
    # Check if trade meets minimum size for clustering ($2k-$8k range)
    if size_usd < 2000.0:
        rejected_below_cluster_min += 1
        logger.debug("trade_rejected", reason="below_cluster_min", size_usd=size_usd, wallet=wallet[:8])
        return None
    
    if size_usd >= CLUSTER_MIN_USD:
        # Single trade already meets threshold - check other filters and generate signal directly
        if discount_pct < MIN_DISCOUNT_PCT:
            rejected_low_discount += 1
            logger.debug("trade_rejected", reason="below_discount", discount=discount_pct, wallet=wallet[:8], score=whale["score"])
            return None
        
        # Check orderbook depth
        depth_ratio = await get_orderbook_depth(session, trade.get("conditionId", ""), size)
        
        if depth_ratio < MIN_ORDERBOOK_DEPTH_MULTIPLIER:
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
        
        # Require minimum 3 trades per cluster
        if len(cluster["trades"]) < CLUSTER_MIN_TRADES:
            logger.debug("cluster_rejected", 
                        reason="insufficient_trades", 
                        trades_count=len(cluster["trades"]), 
                        required=CLUSTER_MIN_TRADES,
                        wallet=wallet[:20])
            return None
        
        # Arb bot filter: skip if whale's avg hold time < 30 min
        whale_stats = cluster.get("whale", {}).get("stats", {})
        avg_hold_hours = whale_stats.get("avg_hold_time_hours", 0.0)
        avg_hold_minutes = avg_hold_hours * 60
        
        if avg_hold_minutes > 0 and avg_hold_minutes < CLUSTER_MIN_AVG_HOLD_MINUTES:
            logger.debug("cluster_rejected",
                        reason="avg_hold_too_short",
                        avg_hold_minutes=avg_hold_minutes,
                        required=CLUSTER_MIN_AVG_HOLD_MINUTES,
                        wallet=wallet[:20])
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
    weighted_price = cluster["total_usd"] / total_size if total_size > 0 else first_trade.get("price")
    
    # Calculate discount
    whale_entry_price = weighted_price
    if whale_entry_price is None or whale_entry_price <= 0:
        logger.debug("cluster_rejected", reason="missing_entry_price", wallet=cluster["wallet"][:8])
        return None
    
    # Fetch current price from CLOB midpoint endpoint using token_id
    condition_id = cluster["market_id"]
    if not condition_id:
        logger.debug("cluster_rejected", reason="missing_condition_id", wallet=cluster["wallet"][:8])
        return None
    
    # Extract token_id from first trade (Path A: direct from trade payload)
    first_trade = cluster["trades"][0]
    token_id = (first_trade.get("tokenId") or first_trade.get("clobTokenId") or 
                first_trade.get("asset_id") or first_trade.get("outcomeId"))
    
    # Path B: If not in trade, get from conditionId → clobTokenIds mapping
    if not token_id:
        side = first_trade.get("side", "BUY")
        token_id = get_token_id_for_condition(condition_id, side)
    
    if not token_id:
        logger.debug("cluster_rejected", reason="rejected_discount_missing", 
                    wallet=cluster["wallet"][:8], condition_id=condition_id[:20], 
                    note="token_id_not_found_in_trade_or_cache")
        return None
    
    # Fetch midpoint price: try CLOB first, fallback to Gamma market bestBid/bestAsk
    current_price = await get_midpoint_price_cached(session, str(token_id))
    
    # Fallback to Gamma market midpoint if CLOB fails
    if current_price is None and condition_id:
        current_price = await get_market_midpoint_cached(session, condition_id)
    
    if current_price is None:
        # Phase 1b bypass: allow missing discount for calibration
        if os.getenv("PHASE1B_ALLOW_MISSING_DISCOUNT", "False") == "True":
            logger.warning("PHASE1B_USING_ZERO_DISCOUNT", wallet=cluster["wallet"][:8], 
                         token_id=str(token_id)[:20] if token_id else None, 
                         condition_id=condition_id[:20], note="current_price_missing_using_entry_price")
            notify_phase1b_bypass(cluster["wallet"], condition_id, "current_price_missing_using_entry_price")
            current_price = whale_entry_price  # Use entry price so discount = 0.0
        else:
            logger.debug("cluster_rejected", reason="rejected_discount_missing", 
                        wallet=cluster["wallet"][:8], token_id=str(token_id)[:20] if token_id else None, 
                        condition_id=condition_id[:20])
            return None
    
    # Calculate discount: entry_price vs current midpoint
    discount_pct = calculate_discount(whale_entry_price, current_price)
    
    # Reject if discount cannot be calculated
    if discount_pct is None:
        # Phase 1b bypass: allow missing discount for calibration
        if os.getenv("PHASE1B_ALLOW_MISSING_DISCOUNT", "False") == "True":
            logger.warning("PHASE1B_USING_ZERO_DISCOUNT", wallet=cluster["wallet"][:8], 
                         entry_price=whale_entry_price, current_price=current_price,
                         note="discount_calc_returned_none_using_zero")
            notify_phase1b_bypass(cluster["wallet"], condition_id, "discount_calc_returned_none_using_zero")
            discount_pct = 0.0
        else:
            logger.debug("cluster_rejected", reason="rejected_discount_missing", 
                        wallet=cluster["wallet"][:8], entry_price=whale_entry_price, current_price=current_price)
            return None
    
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


def log_all_activity(market_id: str, whale_wallet: str, score: float, discount: Optional[float], size_usd: float):
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
        # Handle None discount (log as empty string or 0.0 for CSV compatibility)
        discount_value = discount if discount is not None else ""
        writer.writerow([datetime.now().isoformat(), market_id, whale_wallet, score, discount_value, size_usd])


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
        
        logger.debug("CSV_WRITE_ATTEMPT", row=signal)
        notify_csv_write_attempt(signal)
        writer.writerow(signal)
        f.flush()
        os.fsync(f.fileno())
        logger.debug("CSV_WRITE_DONE", file=log_file)
        notify_csv_write_done(str(log_file))


def audit_data_quality():
    """
    Analyze today's signals.csv and compute quality metrics.
    Logs results to quality_audit.txt.
    """
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    signals_file = os.path.join(log_dir, f"signals_{date_str}.csv")
    
    if not os.path.exists(signals_file):
        logger.debug("audit_skipped", reason="no_signals_file", file=signals_file)
        return
    
    try:
        # Load signals CSV with encoding error handling
        try:
            df = pd.read_csv(signals_file, encoding="utf-8", encoding_errors="replace")
        except TypeError:
            # Older pandas fallback (doesn't support encoding_errors parameter)
            df = pd.read_csv(signals_file, encoding="utf-8", errors="replace")
        except Exception:
            # Final fallback: try cp1252 (Windows encoding)
            try:
                df = pd.read_csv(signals_file, encoding="cp1252", encoding_errors="replace")
            except TypeError:
                df = pd.read_csv(signals_file, encoding="cp1252", errors="replace")
        
        if len(df) == 0:
            logger.debug("audit_skipped", reason="empty_signals_file")
            return
        
        # Helper function to convert numpy types to native Python types
        def _py(v):
            try:
                import numpy as np
                if isinstance(v, (np.floating, np.integer)):
                    return v.item()
            except Exception:
                pass
            return float(v) if hasattr(v, "__float__") else v
        
        # Compute metrics
        total_signals = len(df)
        
        # Average cluster size (convert numpy types to native Python)
        avg_cluster_size = df['cluster_trades_count'].mean() if 'cluster_trades_count' in df.columns else 0.0
        avg_cluster_size = _py(avg_cluster_size)
        
        # Average discount (convert numpy types to native Python)
        avg_discount = df['discount_pct'].mean() if 'discount_pct' in df.columns else 0.0
        avg_discount = _py(avg_discount)
        
        # Market category distribution
        category_counts = df['category'].value_counts().to_dict() if 'category' in df.columns else {}
        
        # % of signals with score < 0.70 (convert numpy types to native Python)
        if 'whale_score' in df.columns:
            low_score_count = len(df[df['whale_score'] < 0.70])
            low_score_pct = (low_score_count / total_signals * 100) if total_signals > 0 else 0.0
            low_score_pct = _py(low_score_pct)
        else:
            low_score_count = 0
            low_score_pct = 0.0
        
        # Market title analysis (extract sport/event types)
        market_types = {}
        if 'market' in df.columns:
            for market in df['market'].dropna():
                market_lower = str(market).lower()
                if 'nhl' in market_lower or 'hockey' in market_lower:
                    market_types['NHL'] = market_types.get('NHL', 0) + 1
                elif 'nfl' in market_lower or 'football' in market_lower:
                    market_types['NFL'] = market_types.get('NFL', 0) + 1
                elif 'nba' in market_lower or 'basketball' in market_lower:
                    market_types['NBA'] = market_types.get('NBA', 0) + 1
                elif 'election' in market_lower or 'president' in market_lower or 'vote' in market_lower:
                    market_types['Elections'] = market_types.get('Elections', 0) + 1
                elif 'crypto' in market_lower or 'bitcoin' in market_lower or 'btc' in market_lower:
                    market_types['Crypto'] = market_types.get('Crypto', 0) + 1
                elif 'sport' in market_lower:
                    market_types['Sports'] = market_types.get('Sports', 0) + 1
        
        # Write audit report
        audit_file = os.path.join(log_dir, "quality_audit.txt")
        with open(audit_file, "w", encoding="utf-8") as f:
            f.write("="*70 + "\n")
            f.write(f"DATA QUALITY AUDIT - {date_str}\n")
            f.write("="*70 + "\n\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Signals File: {signals_file}\n\n")
            
            f.write("SUMMARY METRICS\n")
            f.write("-"*70 + "\n")
            f.write(f"Total Signals: {total_signals}\n")
            f.write(f"Average Cluster Size: {avg_cluster_size:.2f} trades\n")
            f.write(f"Average Discount: {avg_discount:.2f}%\n")
            f.write(f"Signals with Score < 0.70: {low_score_count} ({low_score_pct:.2f}%)\n\n")
            
            f.write("CATEGORY DISTRIBUTION\n")
            f.write("-"*70 + "\n")
            for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
                pct = (count / total_signals * 100) if total_signals > 0 else 0.0
                f.write(f"  {category}: {count} ({pct:.2f}%)\n")
            f.write("\n")
            
            f.write("MARKET TYPE DISTRIBUTION\n")
            f.write("-"*70 + "\n")
            if market_types:
                for market_type, count in sorted(market_types.items(), key=lambda x: x[1], reverse=True):
                    pct = (count / total_signals * 100) if total_signals > 0 else 0.0
                    f.write(f"  {market_type}: {count} ({pct:.2f}%)\n")
            else:
                f.write("  (No market types detected)\n")
            f.write("\n")
            
            f.write("="*70 + "\n")
        
        logger.info("quality_audit_completed",
                   total_signals=total_signals,
                   avg_cluster_size=avg_cluster_size,
                   avg_discount=avg_discount,
                   low_score_pct=low_score_pct,
                   audit_file=audit_file)
        
    except Exception as e:
        logger.error("audit_failed", error=str(e))
        import traceback
        logger.error("audit_traceback", traceback=traceback.format_exc())


# Telegram functions removed - paper trading mode (CSV + console logging only)

# Global SignalStats instance for periodic Telegram notifications
stats = SignalStats(notify_every_signals=10, notify_every_seconds=15*60)

async def main_loop():
    """Main polling loop - polls top markets by volume (gamma-api → conditionId bridge)."""
    # Log production mode status
    if PRODUCTION_MODE:
        logger.info("production_mode_enabled",
                    message="Running in production mode - enforcing filters",
                    whitelist_only=WHITELIST_ONLY,
                    bypass_score=BYPASS_SCORE_ON_STATS_FAIL,
                    min_discount=MIN_DISCOUNT_PCT,
                    min_score=MIN_WHALE_SCORE,
                    cluster_window=CLUSTER_WINDOW_MINUTES,
                    cluster_min_trades=CLUSTER_MIN_TRADES,
                    cluster_min_hold=CLUSTER_MIN_AVG_HOLD_MINUTES)
    else:
        logger.info("data_collection_mode",
                    message="Running in data collection mode - relaxed filters",
                    whitelist_only=WHITELIST_ONLY,
                    bypass_score=BYPASS_SCORE_ON_STATS_FAIL,
                    min_discount=MIN_DISCOUNT_PCT)
    
    logger.info("engine_started", poll_interval=POLL_INTERVAL_SECONDS, mode="multi_event")
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # 1. Fetch top markets by volume (gamma-api → conditionId bridge)
                # Limit to 10 markets in production mode for faster testing
                market_limit = 10 if PRODUCTION_MODE else 20
                markets = await fetch_top_markets(session, limit=market_limit, offset=0)
                
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
                                # Final validation: reject if score or discount is None
                                if signal.get("whale_score") is None:
                                    global rejected_score_missing
                                    rejected_score_missing += 1
                                    logger.debug("signal_rejected", reason="rejected_score_missing", wallet=signal.get("wallet", "unknown")[:8])
                                    continue
                                
                                if signal.get("discount_pct") is None:
                                    global rejected_discount_missing
                                    rejected_discount_missing += 1
                                    logger.debug("signal_rejected", reason="rejected_discount_missing", wallet=signal.get("wallet", "unknown")[:8])
                                    continue
                                
                                global signals_generated
                                signals_generated += 1
                                # Log signal to CSV
                                log_signal_to_csv(signal)
                                recent_signals.append(signal)
                                
                                # Notify via Telegram (real signal notification)
                                notify_signal(signal)
                                
                                # Periodic stats update (every 10 signals or 15 min)
                                stats.bump(extra_line="signal recorded")
                                
                                # Console log
                                logger.info("signal_generated", 
                                           wallet=signal['wallet'][:20],
                                           discount=signal['discount_pct'],
                                           market=signal['market'][:50],
                                           event_id=event_id)
                                
                                # Signal notification already sent via notify_signal() above
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
                           rejected_score_missing=rejected_score_missing,
                           rejected_discount_missing=rejected_discount_missing,
                           rejected_depth=rejected_depth,
                           rejected_conflicting=rejected_conflicting,
                           rejected_daily_limit=rejected_daily_limit,
                           signals_generated=signals_generated)
                
                # Write status line to file for easy tracking
                append_status_line(
                    f"{datetime.utcnow().isoformat()}Z gate_breakdown "
                    f"trades_considered={trades_considered} signals_generated={signals_generated} "
                    f"rejected_low_score={rejected_low_score} rejected_low_discount={rejected_low_discount} "
                    f"rejected_score_missing={rejected_score_missing} rejected_discount_missing={rejected_discount_missing} "
                    f"rejected_below_cluster_min={rejected_below_cluster_min} rejected_conflicting={rejected_conflicting} "
                    f"rejected_depth={rejected_depth} rejected_daily_limit={rejected_daily_limit}"
                )
                
                # Audit data quality
                audit_data_quality()
                
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
    # Notify engine start
    notify_engine_start()
    
    # Log file location
    day = datetime.utcnow().strftime("%Y-%m-%d")
    log_file = Path("logs") / f"engine_{day}.log"
    logger.info("engine_starting", mode="paper_trading", logging="csv_and_console", log_file=str(log_file))
    print(f"\n📝 Console output is being logged to: {log_file}\n")
    
    try:
        await main_loop()
    except KeyboardInterrupt:
        logger.info("shutdown_requested")
        notify_engine_stop()
    except Exception as e:
        from src.polymarket.telegram import notify_engine_crash
        notify_engine_crash(f"{type(e).__name__}: {e}")
        raise
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())

