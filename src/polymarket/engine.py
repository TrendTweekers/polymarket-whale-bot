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
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from collections import defaultdict
import json
import math
import pandas as pd
from pathlib import Path

# Load environment variables (force load at top)
try:
    from dotenv import load_dotenv
    load_dotenv()  # Load .env file
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

from src.polymarket.scraper import fetch_recent_trades, fetch_top_markets, fetch_trades, fetch_trades_scanned, get_midpoint_price_cached, get_token_id_for_condition, get_market_midpoint_cached, fetch_market_metadata_by_condition, BASE, HEADERS
from src.polymarket.profiler import get_user_stats, whale_score_from_stats
from src.polymarket.score import whale_score, whitelist_whales
from src.polymarket.telegram import notify_engine_start, notify_engine_stop, notify_signal
from src.polymarket.telegram_notify import SignalStats

# Windows-safe stdout/stderr UTF-8 reconfiguration (prevents crashes from emoji/unicode)
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # If reconfigure fails, continue anyway

# Configure logging level from environment (for filtering debug messages)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Recent log handler that maintains only last 50 lines
class RecentLogHandler(logging.Handler):
    """Handler that maintains only the last 50 log lines in a separate file."""
    def __init__(self, filename, max_lines=50):
        super().__init__()
        self.filename = Path(filename)
        self.max_lines = max_lines
        self.lines = []
        # Load existing lines if file exists
        if self.filename.exists():
            try:
                self.lines = self.filename.read_text(encoding="utf-8").strip().split("\n")
                # Keep only last max_lines
                if len(self.lines) > self.max_lines:
                    self.lines = self.lines[-self.max_lines:]
            except Exception:
                self.lines = []
    
    def emit(self, record):
        """Write log record and maintain only last max_lines."""
        try:
            msg = self.format(record)
            self.lines.append(msg)
            # Keep only last max_lines
            if len(self.lines) > self.max_lines:
                self.lines = self.lines[-self.max_lines:]
            # Write to file
            self.filename.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        except Exception:
            pass  # Don't break logging if recent log fails

# Setup file logging for console output
def setup_file_logging():
    """Configure logging to write to both console and daily log file."""
    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)
    
    # Create daily log file
    day = datetime.utcnow().strftime("%Y-%m-%d")
    log_file = Path("logs") / f"engine_{day}.log"
    recent_log_file = Path("logs") / "engine_recent.log"
    
    # Clear log file on startup (start fresh each session)
    if log_file.exists():
        try:
            log_file.unlink()  # Delete existing file
        except Exception:
            pass  # If locked or can't delete, continue anyway
    
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
    
    # Recent log handler (last 50 lines)
    recent_handler = RecentLogHandler(recent_log_file, max_lines=50)
    recent_handler.setLevel(logging.DEBUG)
    recent_handler.setFormatter(file_formatter)
    
    # Get root logger and add file handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(recent_handler)
    
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
# MIN_LOW_DISCOUNT is an alias/alternative name for MIN_DISCOUNT_PCT (for clarity)
MIN_LOW_DISCOUNT = float(os.getenv("MIN_LOW_DISCOUNT", os.getenv("MIN_DISCOUNT_PCT", "0.0")))
# Use MIN_LOW_DISCOUNT if set, otherwise fall back to MIN_DISCOUNT_PCT
if "MIN_LOW_DISCOUNT" in os.environ:
    MIN_DISCOUNT_PCT = MIN_LOW_DISCOUNT

# Bypass score on stats fail (env-configurable)
BYPASS_SCORE_ON_STATS_FAIL = env_bool("BYPASS_SCORE_ON_STATS_FAIL", default=False)

# Include SELL trades (env-configurable)
INCLUDE_SELL_TRADES = env_bool("INCLUDE_SELL_TRADES", default=False)

# Bypass flags for testing (env-configurable)
BYPASS_CLUSTER_MIN = env_bool("BYPASS_CLUSTER_MIN", default=False)
BYPASS_LOW_DISCOUNT = env_bool("BYPASS_LOW_DISCOUNT", default=False)

# Minimum cluster USD threshold (env-configurable, lowered default for testing)
MIN_CLUSTER_USD = float(os.getenv("MIN_CLUSTER_USD", "100.0"))

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
CLUSTER_MIN_TRADES = int(os.getenv("CLUSTER_MIN_TRADES", "1"))  # Minimum trades required per cluster (env-configurable)
MIN_CLUSTER_TRADES = int(os.getenv("MIN_CLUSTER_TRADES", "1"))  # Alias for CLUSTER_MIN_TRADES (env-configurable)
CLUSTER_MIN_AVG_HOLD_MINUTES = int(os.getenv("CLUSTER_MIN_HOLD", "30"))  # Skip clusters with avg hold < X min (arb bot filter, env-configurable)
# Log cluster configuration at startup (after cluster config is defined)
logger.info("cluster_config",
           CLUSTER_MIN_TRADES=CLUSTER_MIN_TRADES,
           MIN_CLUSTER_TRADES=MIN_CLUSTER_TRADES,
           CLUSTER_MIN_HOLD=CLUSTER_MIN_AVG_HOLD_MINUTES,
           MIN_CLUSTER_USD=MIN_CLUSTER_USD)

# Log environment settings at startup (force log even if exists)
logger.info("ENV_SETTINGS",
           INCLUDE_SELL_TRADES=os.getenv("INCLUDE_SELL_TRADES", "False"),
           MIN_CLUSTER_USD=os.getenv("MIN_CLUSTER_USD", "500.0"),
           MIN_CLUSTER_TRADES=os.getenv("MIN_CLUSTER_TRADES", "1"),
           MIN_WHALE_SCORE=os.getenv("MIN_WHALE_SCORE", "0.005"),
           BYPASS_SCORE_ON_STATS_FAIL=os.getenv("BYPASS_SCORE_ON_STATS_FAIL", "False"),
           MIN_LOW_DISCOUNT=os.getenv("MIN_LOW_DISCOUNT", "0.01"),
           MIN_DISCOUNT_PCT=MIN_DISCOUNT_PCT,
           BYPASS_CLUSTER_MIN=os.getenv("BYPASS_CLUSTER_MIN", "False"),
           BYPASS_LOW_DISCOUNT=os.getenv("BYPASS_LOW_DISCOUNT", "False"))

whale_clusters: Dict[str, Dict] = {}  # {wallet+market: {trades: [], total_usd: 0, first_trade_time: datetime, whale: {}, category: ""}}

# Filter rejection counters (for diagnostics)
rejected_below_cluster_min = 0
rejected_low_score = 0
rejected_low_discount = 0
rejected_score_missing = 0  # Score is None
rejected_score_unavailable = 0  # Stats missing/unavailable
rejected_discount_missing = 0  # Discount is None
rejected_depth = 0
rejected_conflicting = 0
rejected_daily_limit = 0
rejected_other = 0  # Other gates not explicitly counted
signals_generated = 0
trades_considered = 0

# Calibration mode: track whale scores for histogram analysis
CALIBRATION_CYCLE_COUNT = 0  # Track cycles for periodic reporting
whale_score_samples: List[Dict] = []  # Store {wallet, condition_id, trade_usd, whale_score} for all considered trades
WHALE_SCORE_SAMPLES_MAX = 10000  # Limit memory usage

# Trade deduplication cache (prevent re-processing same trades)
SEEN_TRADE_KEYS: Set[str] = set()
SEEN_TRADE_KEYS_MAX = 250000  # prevent unbounded memory


async def fetch_gamma_midpoint(condition_id: str) -> Optional[float]:
    """Last-ditch Gamma fetch by condition_id; returns None on any fail."""
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://gamma-api.polymarket.com/markets?conditionId={condition_id}"
            async with s.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                # Handle list or dict response
                market = None
                if isinstance(data, list) and len(data) > 0:
                    market = data[0]
                elif isinstance(data, dict) and "markets" in data and isinstance(data["markets"], list) and data["markets"]:
                    market = data["markets"][0]
                elif isinstance(data, dict) and "id" in data:
                    market = data
                
                if not isinstance(market, dict):
                    return None
                
                bid = float(market.get("bestBid", 0) or 0)
                ask = float(market.get("bestAsk", 0) or 0)
                if bid > 0 and ask > 0:
                    return round((bid + ask) / 2, 3)
    except Exception:
        pass
    return None


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


async def get_whale_with_score(session: aiohttp.ClientSession, wallet: str, category: str, trade_usd: float = 0.0) -> Optional[Dict]:
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
    
    try:
        stats = await get_user_stats(session, wallet)
        score = whale_score_from_stats(stats)
    except Exception as e:
        logger.error("whale_stats_fetch_failed", wallet=wallet[:20], error=str(e))
        stats = {
            "wallet": wallet,
            "trade_count_100": 0,
            "total_usd_100": 0.0,
            "max_trade_usd_100": 0.0,
            "stats_missing": True,
            "reason": f"fetch_error:{type(e).__name__}",
        }
        score = None
    
    # If stats missing, optionally fallback to trade_usd-based score instead of hard reject
    if stats.get("stats_missing") or (score is None):
        global rejected_score_unavailable
        if BYPASS_SCORE_ON_STATS_FAIL:
            # fallback: strong single trade should still bubble up
            # trade_usd should be the USD size of the current trade you're evaluating
            try:
                fallback = min(1.0, math.log10(float(trade_usd) + 1.0) / 5.0)
            except Exception:
                fallback = 0.0

            score = fallback
            logger.debug(
                "whale_score_fallback_used",
                wallet=wallet[:10],
                trade_usd=trade_usd,
                fallback_score=score,
                reason=stats.get("reason", "stats_missing"),
            )
        else:
            rejected_score_unavailable += 1
            logger.debug(
                "trade_rejected",
                reason="whale_score_unavailable",
                wallet=wallet[:10],
                note=stats.get("reason", "stats_missing"),
            )
            return None
    
    whale = {
        "wallet": wallet,
        "stats": stats or {},
        "score": score,
        "category": category
    }
    
    whitelist_cache[wallet] = whale
    logger.debug("whale_score_computed", wallet=wallet[:20], score=score, category=category)
    return whale


async def ensure_whale_whitelisted(session: aiohttp.ClientSession, wallet: str, category: str, trade_usd: float = 0.0) -> Optional[Dict]:
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
    
    try:
        stats = await get_user_stats(session, wallet)
        score = whale_score_from_stats(stats)
    except Exception as e:
        logger.error("whale_stats_fetch_failed", wallet=wallet[:20], error=str(e))
        stats = {
            "wallet": wallet,
            "trade_count_100": 0,
            "total_usd_100": 0.0,
            "max_trade_usd_100": 0.0,
            "stats_missing": True,
            "reason": f"fetch_error:{type(e).__name__}",
        }
        score = None
    
    # If stats missing, optionally fallback to trade_usd-based score instead of hard reject
    if stats.get("stats_missing") or (score is None):
        global rejected_score_unavailable
        if BYPASS_SCORE_ON_STATS_FAIL and not WHITELIST_ONLY:
            # fallback: strong single trade should still bubble up
            # trade_usd should be the USD size of the current trade you're evaluating
            try:
                fallback = min(1.0, math.log10(float(trade_usd) + 1.0) / 5.0)
            except Exception:
                fallback = 0.0

            score = fallback
            logger.debug(
                "whale_score_fallback_used",
                wallet=wallet[:10],
                trade_usd=trade_usd,
                fallback_score=score,
                reason=stats.get("reason", "stats_missing"),
            )
        else:
            rejected_score_unavailable += 1
            logger.debug(
                "trade_rejected",
                reason="whale_score_unavailable",
                wallet=wallet[:10],
                note=stats.get("reason", "stats_missing"),
            )
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
    
    logger.info("whale_whitelisted", wallet=wallet[:20], score=score, category=category)
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


def _parse_dt(s: str) -> Optional[datetime]:
    """Parse ISO datetime string, handling various formats."""
    if not s:
        return None
    # Handle "2025-12-16T09:00:00Z" and "2025-12-16T09:00:00.000Z"
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _days_to_expiry(market: dict) -> Optional[float]:
    """Calculate days to expiry from market metadata. Returns None if expiry date not found."""
    # Polymarket fields vary; try the common ones
    for k in ("endDate", "end_date", "closeTime", "close_time", "resolutionTime", "resolution_time"):
        dt = _parse_dt(market.get(k))
        if dt:
            now = datetime.now(timezone.utc)
            # Ensure dt is timezone-aware
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (dt - now).total_seconds() / 86400.0
    return None


def calculate_discount(whale_entry_price: float, current_price: float, side: str = "BUY") -> Optional[float]:
    """
    Calculate discount percentage (edge/advantage).
    For BUY: positive discount means you bought below market (good)
    For SELL: positive discount means you sold above market (good)
    Returns None if prices are missing/invalid (instead of silently returning 0.0).
    """
    # Reject if either price is missing or invalid
    if whale_entry_price is None or whale_entry_price <= 0:
        return None
    if current_price is None or current_price < 0:
        return None
    
    # Calculate discount based on side
    if side.upper() == "BUY":
        # For BUY: discount = (current_price - entry_price) / current_price * 100
        # Positive means you bought below market (good)
        discount = ((current_price - whale_entry_price) / current_price) * 100.0
    else:
        # For SELL: discount = (entry_price - current_price) / entry_price * 100
        # Positive means you sold above market (good)
        discount = ((whale_entry_price - current_price) / whale_entry_price) * 100.0
    
    return discount


# Cache for market token IDs: condition_id -> list of clobTokenIds
_market_token_cache: Dict[str, List[str]] = {}


async def get_token_id(condition_id: str, trade: Dict, session: aiohttp.ClientSession) -> Optional[str]:
    """
    Resolve token_id from condition_id and trade outcome using Gamma API.
    Uses clobTokenIds field from market data and matches trade outcome to outcomes list.
    """
    # Check cache first
    if condition_id in _market_token_cache:
        token_ids = _market_token_cache[condition_id]
        # Get outcomes from cache if available, otherwise need to fetch
        outcomes = _market_token_cache.get(f"{condition_id}_outcomes", [])
        
        if outcomes:
            # Normalize outcomes for matching
            normalized_outcomes = [str(o).strip().upper() for o in outcomes]
            outcome_upper = trade.get("outcome", "").strip().upper()
            matching_indices = [i for i, norm_o in enumerate(normalized_outcomes) if norm_o == outcome_upper]
            if matching_indices and matching_indices[0] < len(token_ids):
                return token_ids[matching_indices[0]].strip()
        else:
            # Fallback: use outcome_index if available
            outcome_index = trade.get("outcomeIndex") or trade.get("outcome_index", 0)
            if outcome_index < len(token_ids):
                return token_ids[outcome_index].strip()
    
    try:
        url = f"https://gamma-api.polymarket.com/markets?condition_ids={condition_id}&limit=1&offset=0"
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                logger.debug("market_fetch_failed", condition_id=condition_id[:20], status=resp.status)
                return None
            
            data = await resp.json()
            if not data:
                return None
            
            # Handle both list and dict responses
            market = None
            if isinstance(data, list) and len(data) > 0:
                market = data[0]
            elif isinstance(data, dict) and "markets" in data and isinstance(data["markets"], list) and data["markets"]:
                market = data["markets"][0]
            elif isinstance(data, dict) and "id" in data:
                market = data
            
            if not market:
                return None
            
            # Parse clobTokenIds (can be JSON array string or comma-separated)
            clob_token_ids_str = market.get("clobTokenIds", "")
            if not clob_token_ids_str:
                logger.debug("outcomes_missing", condition_id=condition_id[:20], market_id=market.get("id", "unknown"))
                return None
            
            try:
                if clob_token_ids_str.startswith('['):
                    # Parse JSON array string to list
                    token_ids = json.loads(clob_token_ids_str)
                else:
                    # Fallback: split and strip quotes
                    token_ids = [tid.strip().strip('"').strip("'") for tid in clob_token_ids_str.split(',') if tid]
                # Normalize token_ids (ensure strings, strip whitespace)
                token_ids = [str(tid).strip() for tid in token_ids if tid]
            except (json.JSONDecodeError, IndexError, TypeError) as e:
                logger.debug("clobTokenIds_parse_error", 
                            condition_id=condition_id[:20], 
                            clobTokenIds=clob_token_ids_str[:100], 
                            error=str(e))
                return None
            
            # Cache token_ids
            _market_token_cache[condition_id] = token_ids
            
            # Get outcomes list - handle both list and JSON string
            outcomes_raw = market.get("outcomes", [])
            if isinstance(outcomes_raw, str):
                try:
                    outcomes = json.loads(outcomes_raw) if outcomes_raw else []
                    logger.debug("outcomes_parsed", condition_id=condition_id[:20], parsed_outcomes=outcomes)
                except json.JSONDecodeError:
                    outcomes = []
            else:
                outcomes = outcomes_raw if isinstance(outcomes_raw, list) else []
            
            if not outcomes:
                logger.debug("outcomes_missing", condition_id=condition_id[:20], market_id=market.get("id", "unknown"))
                return None
            
            # Normalize outcomes for matching (strip spaces, upper case)
            normalized_outcomes = [str(o).strip().upper() for o in outcomes]
            
            # Cache outcomes (both raw and normalized)
            _market_token_cache[f"{condition_id}_outcomes"] = outcomes
            
            # Normalize trade outcome
            outcome_upper = trade.get("outcome", "").strip().upper()
            
            # Match normalized trade outcome to normalized market outcomes
            matching_indices = [i for i, norm_o in enumerate(normalized_outcomes) if norm_o == outcome_upper]
            
            if not matching_indices:
                logger.debug("outcome_index_not_found", 
                            condition_id=condition_id[:20], 
                            trade_outcome=outcome_upper,
                            outcome_upper=outcome_upper,
                            normalized_market_outcomes=normalized_outcomes,
                            raw_outcomes=outcomes)
                return None
            
            outcome_index = matching_indices[0]  # Assume first match; binary markets
            
            if outcome_index < len(token_ids):
                token_id = token_ids[outcome_index].strip()
                logger.debug("token_id_resolved_from_gamma",
                            condition_id=condition_id[:20],
                            token_id=str(token_id)[:20],
                            outcome_index=outcome_index,
                            trade_outcome=outcome_upper,
                            matched_outcome=normalized_outcomes[outcome_index])
                return token_id
            else:
                logger.debug("token_id_index_out_of_range", 
                            condition_id=condition_id[:20], 
                            outcome_index=outcome_index, 
                            token_ids_len=len(token_ids))
                return None
            
    except Exception as e:
        logger.debug("token_id_fetch_failed", condition_id=condition_id[:20], error=str(e))
        return None


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


async def process_trade(session: aiohttp.ClientSession, trade: Dict, market_category: Optional[str] = None) -> Optional[Dict]:
    """
    Process a trade and generate signal if conditions are met.
    Returns signal dict if generated, None otherwise.
    """
    # Declare all global variables at the top of the function
    global rejected_conflicting, rejected_low_score, rejected_discount_missing
    global rejected_below_cluster_min, rejected_low_discount, rejected_depth
    global rejected_score_unavailable, rejected_other
    
    # Check daily limits
    can_proceed, reason = check_daily_limits()
    if not can_proceed:
        rejected_other += 1
        logger.debug("trade_rejected_other", wallet=wallet[:8] if wallet else "unknown", specific_reason="daily_limit", details=reason)
        return None
    
    wallet = trade.get("proxyWallet") or trade.get("makerAddress", "")
    if not wallet:
        rejected_other += 1
        logger.debug("trade_rejected_other", wallet="unknown", specific_reason="no_wallet", details="proxyWallet and makerAddress both missing")
        return None
    
    # Get category from market metadata (preferred) or infer from trade
    if not market_category:
        market_category = get_category_from_trade(trade)
    market_category = market_category.lower().strip() if market_category else ""
    
    # Exclude categories (early filter, before scoring/discount work)
    if market_category and market_category in EXCLUDE_CATEGORIES:
        rejected_other += 1
        logger.debug("trade_rejected_other", wallet=wallet[:8], specific_reason="excluded_category", details=f"category={market_category}")
        return None
    
    side = trade.get("side", "BUY")
    include_sells = os.getenv("INCLUDE_SELL_TRADES", "False") == "True"
    logger.debug("sell_trade_check",
                include_sells=include_sells,
                trade_side=side.upper())
    if not include_sells and side.upper() == "SELL":
        rejected_other += 1
        logger.debug("trade_rejected_other",
                    wallet=wallet[:8],
                    specific_reason="sell_trade",
                    details=f"side={side}, INCLUDE_SELL_TRADES={include_sells}")
        return None  # skip SELL trades unless INCLUDE_SELL_TRADES=True
    
    # Check for conflicting whale
    if check_conflicting_whale(wallet, side):
        rejected_conflicting += 1
        logger.debug("conflicting_whale", wallet=wallet[:20])
        return None
    
    # Use market_category (from market metadata) or infer from trade
    category = market_category if market_category else get_category_from_trade(trade)
    
    # Calculate trade USD early for fallback scoring
    whale_entry_price = trade.get("price")
    if whale_entry_price is None or whale_entry_price <= 0:
        rejected_other += 1
        logger.debug("trade_rejected_other", wallet=wallet[:8], specific_reason="missing_entry_price", details=f"price={whale_entry_price}")
        return None
    
    size = trade.get("size", 0.0)
    trade_usd = size * whale_entry_price
    
    # Get whale stats/score (whitelist check only if WHITELIST_ONLY is True)
    if WHITELIST_ONLY:
        whale = await ensure_whale_whitelisted(session, wallet, category, trade_usd)
        if not whale:
            rejected_low_score += 1
            logger.debug("trade_rejected", reason="whale_not_whitelisted", wallet=wallet[:8], category=category)
            return None
    else:
        # Whitelist disabled: just get score, don't enforce whitelist gate
        whale = await get_whale_with_score(session, wallet, category, trade_usd)
        if not whale:
            rejected_low_score += 1
            logger.debug("trade_rejected", reason="whale_score_unavailable", wallet=wallet[:8], category=category)
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
    
    # Path C: Try Gamma API to resolve token_id from condition_id and trade outcome
    if not token_id:
        token_id = await get_token_id(condition_id, trade, session)
        if token_id:
            logger.debug("token_id_resolved",
                        wallet=wallet[:8],
                        condition_id=condition_id[:20],
                        token_id=str(token_id)[:20],
                        outcome=trade.get("outcome"))
    
    if not token_id:
        rejected_other += 1
        logger.debug("trade_rejected", 
                    wallet=wallet[:8], 
                    reason="token_id_resolve_failed", 
                    condition_id=condition_id[:20],
                    outcome=trade.get("outcome"))
        return None
    
    # Fetch midpoint price: try CLOB first, fallback to Gamma market bestBid/bestAsk
    current_price = await get_midpoint_price_cached(session, str(token_id))
    
    # Fallback to Gamma market midpoint if CLOB fails
    if current_price is None and condition_id:
        current_price = await get_market_midpoint_cached(session, condition_id)
    
    if current_price is None:
        rejected_discount_missing += 1
        logger.debug("trade_rejected", reason="rejected_discount_missing", 
                    wallet=wallet[:8], token_id=str(token_id)[:20] if token_id else None, 
                    condition_id=condition_id[:20])
        return None
    
    # Calculate discount: entry_price vs current midpoint
    side = trade.get("side", "BUY")
    discount_pct = calculate_discount(whale_entry_price, current_price, side)
    
    # Debug discount calculation
    logger.debug("discount_calc_debug",
                wallet=wallet[:8],
                condition_id=condition_id[:20],
                entry_price=whale_entry_price,
                midpoint=current_price,
                side=side,
                calculated_discount=discount_pct,
                discount_formula=f"BUY: (midpoint - entry)/midpoint, SELL: (entry - midpoint)/entry")
    
    # Reject if discount cannot be calculated
    if discount_pct is None:
        rejected_discount_missing += 1
        logger.debug("trade_rejected", reason="rejected_discount_missing", 
                    wallet=wallet[:8], entry_price=whale_entry_price, current_price=current_price)
        return None
    
    # Log ALL whale activity for analysis (before filtering)
    # Note: trade_usd already calculated above
    market_id = trade.get("conditionId", trade.get("slug", "unknown"))
    logger.debug("whale_activity", wallet=wallet[:20], score=whale["score"], discount=discount_pct, size_usd=trade_usd)
    log_all_activity(market_id, wallet, whale["score"], discount_pct, trade_usd)
    
    # Calibration mode: track whale score for histogram analysis
    global whale_score_samples
    if len(whale_score_samples) < WHALE_SCORE_SAMPLES_MAX:
        whale_score_samples.append({
            "wallet": wallet,
            "condition_id": condition_id,
            "trade_usd": trade_usd,
            "whale_score": whale["score"]
        })
    elif len(whale_score_samples) >= WHALE_SCORE_SAMPLES_MAX:
        # Rotate: remove oldest 10% when full
        whale_score_samples = whale_score_samples[int(WHALE_SCORE_SAMPLES_MAX * 0.1):]
        whale_score_samples.append({
            "wallet": wallet,
            "condition_id": condition_id,
            "trade_usd": trade_usd,
            "whale_score": whale["score"]
        })
    
    # Check if trade meets minimum size for clustering (bypass if enabled)
    bypass_cluster = os.getenv("BYPASS_CLUSTER_MIN", "False") == "True"
    logger.debug("trade_cluster_bypass_check",
                bypass_enabled=bypass_cluster,
                trade_usd=trade_usd,
                required=2000.0)
    if not bypass_cluster and trade_usd < 2000.0:
        rejected_below_cluster_min += 1
        logger.debug("trade_rejected_other",
                    wallet=wallet[:8],
                    specific_reason="below_cluster_min",
                    details=f"size_usd={trade_usd}, required=2000.0")
        return None
    
    if trade_usd >= MIN_CLUSTER_USD:
        # Single trade already meets threshold - check other filters and generate signal directly
        bypass_discount = os.getenv("BYPASS_LOW_DISCOUNT", "False") == "True"
        min_discount = float(os.getenv("MIN_LOW_DISCOUNT", "0.0"))
        
        logger.debug("discount_bypass_check",
                    bypass_enabled=bypass_discount,
                    calculated_discount=discount_pct,
                    min_required=min_discount,
                    entry_price=whale_entry_price,
                    midpoint=current_price if current_price else "none")
        
        if not bypass_discount and discount_pct < min_discount:
            rejected_low_discount += 1
            logger.debug("trade_rejected_low_discount",
                        wallet=wallet[:8],
                        condition_id=condition_id[:20],
                        calculated_discount=discount_pct,
                        min_required=min_discount,
                        trade_price=whale_entry_price,
                        midpoint=current_price if current_price else "none",
                        discount_formula_details=f"entry={whale_entry_price}, midpoint={current_price}, discount={discount_pct}")
            return None
        
        # Check orderbook depth
        depth_ratio = await get_orderbook_depth(session, trade.get("conditionId", ""), size if size > 0 else trade_usd / max(whale_entry_price, 0.001))
        
        if depth_ratio < MIN_ORDERBOOK_DEPTH_MULTIPLIER:
            rejected_depth += 1
            logger.debug("trade_rejected", reason="insufficient_depth", depth=depth_ratio, wallet=wallet[:8])
            return None
        
        # Generate signal directly (single trade ≥ $10k)
        signal = {
            "timestamp": datetime.now().isoformat(),
            "wallet": wallet,
            "whale_score": whale["score"],
            "category": market_category if market_category else category,
            "market": trade.get("title", "Unknown"),
            "slug": trade.get("slug", ""),
            "condition_id": trade.get("conditionId", ""),
            "market_id": trade.get("conditionId", ""),
            "side": trade.get("side", "BUY"),
            "whale_entry_price": whale_entry_price,
            "current_price": current_price,
            "discount_pct": discount_pct,
            "size": size,
            "trade_value_usd": trade_usd,
            "orderbook_depth_ratio": depth_ratio,
            "transaction_hash": trade.get("transactionHash", ""),
            "cluster_trades_count": 1,
            "cluster_window_minutes": 0,
        }
        
        # Exclude categories filter (even for single trade signals)
        signal_category = signal.get("category", "").lower().strip()
        if signal_category and signal_category in EXCLUDE_CATEGORIES:
            logger.debug("signal_rejected", category=signal_category, reason="excluded_category")
            return None
        
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
    if cluster["total_usd"] >= MIN_CLUSTER_USD:
        # DEDUPE: skip if cluster already triggered
        if cluster.get("triggered"):
            return None
        
        # Check cluster thresholds with detailed logging (bypass if enabled)
        bypass_cluster = os.getenv("BYPASS_CLUSTER_MIN", "False") == "True"
        min_usd = float(os.getenv("MIN_CLUSTER_USD", "100.0"))
        min_trades = int(os.getenv("MIN_CLUSTER_TRADES", "1"))
        
        logger.debug("cluster_bypass_check",
                    bypass_enabled=bypass_cluster,
                    cluster_usd=cluster["total_usd"],
                    cluster_trades=len(cluster["trades"]),
                    required_usd=min_usd,
                    required_trades=min_trades)
        
        if not bypass_cluster:
            if cluster["total_usd"] < min_usd:
                reason = "below_min_usd"
            elif len(cluster["trades"]) < min_trades:
                reason = "below_min_trades"
            else:
                reason = "other_cluster_fail"
            
            if reason != "other_cluster_fail":
                rejected_below_cluster_min += 1
                logger.debug("cluster_rejected",
                            wallet=wallet[:8],
                            market=market_id[:20],
                            total_usd=cluster["total_usd"],
                            trades_count=len(cluster["trades"]),
                            reason=reason,
                            required_usd=min_usd,
                            required_trades=min_trades)
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
    
    # Path C: Try Gamma API to resolve token_id from condition_id and trade outcome
    if not token_id:
        token_id = await get_token_id(condition_id, first_trade, session)
    
    if not token_id:
        logger.debug("cluster_rejected", 
                    reason="token_id_resolve_failed", 
                    wallet=cluster["wallet"][:8], 
                    condition_id=condition_id[:20],
                    outcome=first_trade.get("outcome"))
        return None
    
    # Fetch midpoint price: try CLOB first, fallback to Gamma market bestBid/bestAsk
    current_price = await get_midpoint_price_cached(session, str(token_id))
    
    # Fallback to Gamma market midpoint if CLOB fails
    if current_price is None and condition_id:
        current_price = await get_market_midpoint_cached(session, condition_id)
    
    if current_price is None:
        logger.debug("cluster_rejected", reason="rejected_discount_missing", 
                    wallet=cluster["wallet"][:8], token_id=str(token_id)[:20] if token_id else None, 
                    condition_id=condition_id[:20])
        return None
    
    # Calculate discount: entry_price vs current midpoint
    # Use side from first trade in cluster
    side = cluster["trades"][0].get("side", "BUY") if cluster["trades"] else "BUY"
    discount_pct = calculate_discount(whale_entry_price, current_price, side)
    
    # Reject if discount cannot be calculated
    if discount_pct is None:
        logger.debug("cluster_rejected", reason="rejected_discount_missing", 
                    wallet=cluster["wallet"][:8], entry_price=whale_entry_price, current_price=current_price)
        return None
    
    # Check discount filter (bypass if enabled)
    bypass_discount = os.getenv("BYPASS_LOW_DISCOUNT", "False") == "True"
    min_discount = float(os.getenv("MIN_LOW_DISCOUNT", "0.0"))
    
    logger.debug("cluster_discount_bypass_check",
                bypass_enabled=bypass_discount,
                calculated_discount=discount_pct,
                min_required=min_discount,
                entry_price=whale_entry_price,
                midpoint=current_price if current_price else "none")
    
    if not bypass_discount and discount_pct < min_discount:
        global rejected_low_discount
        rejected_low_discount += 1
        logger.debug("cluster_rejected_low_discount",
                    wallet=cluster["wallet"][:8],
                    condition_id=condition_id[:20],
                    calculated_discount=discount_pct,
                    min_required=min_discount,
                    cluster_total=cluster["total_usd"],
                    trades_count=len(cluster["trades"]),
                    entry_price=whale_entry_price,
                    midpoint=current_price if current_price else "none",
                    discount_formula_details=f"entry={whale_entry_price}, midpoint={current_price}, discount={discount_pct}")
        return None
    
    # Get orderbook depth for total size
    depth_ratio = await get_orderbook_depth(session, cluster["market_id"], total_size)
    
    # Check depth filter
    if depth_ratio < MIN_ORDERBOOK_DEPTH_MULTIPLIER:
        logger.debug("cluster_rejected", reason="insufficient_depth", depth=depth_ratio, wallet=cluster["wallet"][:8], cluster_total=cluster["total_usd"])
        return None
    
    # Fetch market metadata to get real category (not from cluster defaults)
    condition_id = cluster.get("market_id", "")
    market_meta = None
    if condition_id:
        try:
            market_meta = await fetch_market_metadata_by_condition(session, condition_id)
        except Exception as e:
            logger.debug("market_metadata_fetch_failed", condition_id=condition_id[:20], error=str(e))
    
    # Use category from market metadata (preferred) or fallback to cluster category
    if market_meta and market_meta.get("category"):
        signal_category = market_meta["category"].lower().strip()
        market_title = market_meta.get("title", cluster.get("market_title", "Unknown"))
        market_slug = market_meta.get("slug", cluster.get("slug", ""))
    else:
        signal_category = cluster.get("category", "").lower().strip()
        market_title = cluster.get("market_title", "Unknown")
        market_slug = cluster.get("slug", "")
    
    # Exclude categories filter (even for normal signals)
    if signal_category and signal_category in EXCLUDE_CATEGORIES:
        logger.debug("signal_rejected", category=signal_category, reason="excluded_category")
        return None
    
    signal = {
        "timestamp": datetime.now().isoformat(),
        "wallet": cluster["wallet"],
        "whale_score": cluster["whale"]["score"],
        "category": signal_category,
        "market": market_title,
        "slug": market_slug,
        "condition_id": condition_id,
        "market_id": condition_id,
        "side": first_trade.get("side", "BUY"),
        "whale_entry_price": whale_entry_price,
        "current_price": current_price,
        "discount_pct": discount_pct,
        "size": total_size,
        "trade_value_usd": cluster["total_usd"],
        "orderbook_depth_ratio": depth_ratio,
        "transaction_hash": first_trade.get("transactionHash", ""),
        "cluster_trades_count": len(cluster["trades"]),
        "cluster_window_minutes": CLUSTER_WINDOW_MINUTES,
        "phase": "normal",
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


def log_calibration_histogram():
    """Log histogram of whale scores and top 20 highest scores for calibration."""
    global whale_score_samples, CALIBRATION_CYCLE_COUNT
    
    if len(whale_score_samples) == 0:
        logger.info("calibration_histogram", note="no_samples_yet", cycle=CALIBRATION_CYCLE_COUNT)
        return
    
    # Calculate histogram buckets: 0, (0-0.01], (0.01-0.05], (0.05-0.1], (0.1-0.2], (0.2-0.5], >0.5
    buckets = {
        "0": 0,
        "(0-0.01]": 0,
        "(0.01-0.05]": 0,
        "(0.05-0.1]": 0,
        "(0.1-0.2]": 0,
        "(0.2-0.5]": 0,
        ">0.5": 0
    }
    
    for sample in whale_score_samples:
        score = sample["whale_score"]
        if score == 0:
            buckets["0"] += 1
        elif score <= 0.01:
            buckets["(0-0.01]"] += 1
        elif score <= 0.05:
            buckets["(0.01-0.05]"] += 1
        elif score <= 0.1:
            buckets["(0.05-0.1]"] += 1
        elif score <= 0.2:
            buckets["(0.1-0.2]"] += 1
        elif score <= 0.5:
            buckets["(0.2-0.5]"] += 1
        else:
            buckets[">0.5"] += 1
    
    # Get top 20 highest whale_score trades
    top_20 = sorted(whale_score_samples, key=lambda x: x["whale_score"], reverse=True)[:20]
    
    # Log histogram
    logger.warning("calibration_histogram",
                  cycle=CALIBRATION_CYCLE_COUNT,
                  total_samples=len(whale_score_samples),
                  bucket_0=buckets["0"],
                  bucket_0_001=buckets["(0-0.01]"],
                  bucket_001_005=buckets["(0.01-0.05]"],
                  bucket_005_01=buckets["(0.05-0.1]"],
                  bucket_01_02=buckets["(0.1-0.2]"],
                  bucket_02_05=buckets["(0.2-0.5]"],
                  bucket_05_plus=buckets[">0.5"],
                  min_whale_score_threshold=MIN_WHALE_SCORE)
    
    # Log top 20 trades
    logger.warning("calibration_top_20_trades",
                  cycle=CALIBRATION_CYCLE_COUNT,
                  top_trades=[
                      {
                          "wallet": t["wallet"][:8],
                          "condition_id": t["condition_id"][:20] if t["condition_id"] else "N/A",
                          "trade_usd": round(t["trade_usd"], 2),
                          "whale_score": round(t["whale_score"], 4)
                      }
                      for t in top_20
                  ])
    
    # Also print to console for visibility
    print("\n" + "="*80)
    print(f"CALIBRATION HISTOGRAM (Cycle {CALIBRATION_CYCLE_COUNT}, {len(whale_score_samples)} samples)")
    print("="*80)
    print(f"Whale Score Distribution:")
    print(f"  0:              {buckets['0']:>6} ({buckets['0']/len(whale_score_samples)*100:.1f}%)")
    print(f"  (0-0.01]:      {buckets['(0-0.01]']:>6} ({buckets['(0-0.01]']/len(whale_score_samples)*100:.1f}%)")
    print(f"  (0.01-0.05]:   {buckets['(0.01-0.05]']:>6} ({buckets['(0.01-0.05]']/len(whale_score_samples)*100:.1f}%)")
    print(f"  (0.05-0.1]:    {buckets['(0.05-0.1]']:>6} ({buckets['(0.05-0.1]']/len(whale_score_samples)*100:.1f}%)")
    print(f"  (0.1-0.2]:     {buckets['(0.1-0.2]']:>6} ({buckets['(0.1-0.2]']/len(whale_score_samples)*100:.1f}%)")
    print(f"  (0.2-0.5]:     {buckets['(0.2-0.5]']:>6} ({buckets['(0.2-0.5]']/len(whale_score_samples)*100:.1f}%)")
    print(f"  >0.5:          {buckets['>0.5']:>6} ({buckets['>0.5']/len(whale_score_samples)*100:.1f}%)")
    print(f"\nCurrent MIN_WHALE_SCORE threshold: {MIN_WHALE_SCORE}")
    print(f"\nTop 20 Highest Whale Scores:")
    for i, t in enumerate(top_20, 1):
        print(f"  {i:2}. Score: {t['whale_score']:.4f} | Wallet: {t['wallet'][:12]}... | Trade: ${t['trade_usd']:,.2f} | Condition: {t['condition_id'][:20] if t['condition_id'] else 'N/A'}")
    print("="*80 + "\n")


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


def _csv_clean(v):
    """Clean a value for CSV writing: convert to string, remove newlines, handle dicts/lists."""
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False)
    else:
        v = str(v)
    # Replace newlines and carriage returns with spaces to prevent CSV corruption
    return v.replace("\r", " ").replace("\n", " ")


def log_signal_to_csv(signal: Dict):
    """Log signal to CSV file with bulletproof CSV writing."""
    log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"signals_{date_str}.csv")
    
    file_exists = os.path.exists(log_file)
    
    with open(log_file, "a", newline="", encoding="utf-8") as f:
        fieldnames = [
            "timestamp", "wallet", "whale_score", "category", "market", "slug",
            "condition_id", "market_id", "side", "phase",
            "whale_entry_price", "current_price", "discount_pct",
            "size", "trade_value_usd", "orderbook_depth_ratio", "transaction_hash",
            "cluster_trades_count", "cluster_window_minutes"
        ]
        # Use QUOTE_MINIMAL for proper quoting and extrasaction="ignore" to ignore extra fields
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", quoting=csv.QUOTE_MINIMAL)
        
        if not file_exists:
            writer.writeheader()
        
        logger.debug("CSV_WRITE_ATTEMPT", row=signal)
        # Clean all values: convert to strings, remove newlines, handle dicts/lists
        safe_row = {k: _csv_clean(signal.get(k, "")) for k in fieldnames}
        writer.writerow(safe_row)
        f.flush()
        os.fsync(f.fileno())
        logger.debug("CSV_WRITE_DONE", file=log_file)


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
                
                # Filter markets by expiry time (same-day / 1-2 day markets only)
                max_days = float(os.getenv("MAX_DAYS_TO_EXPIRY", "9999"))
                min_hours = float(os.getenv("MIN_HOURS_TO_EXPIRY", "0"))
                filtered_markets = []
                for m in markets:
                    dte = _days_to_expiry(m)
                    if dte is None:
                        # Expiry missing - keep market (don't reject until we fetch full metadata)
                        logger.debug("market_expiry_missing",
                                    market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                    condition_id=m.get("conditionId", "unknown")[:20],
                                    note="keeping market, expiry not in top_markets response")
                        filtered_markets.append(m)
                        continue
                    if dte > max_days:
                        # Too long - skip this market
                        logger.debug("market_rejected_expiry",
                                    market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                    condition_id=m.get("conditionId", "unknown")[:20],
                                    days_to_expiry=dte,
                                    max_days=max_days,
                                    reason="too_long")
                        continue
                    if dte * 24.0 < min_hours:
                        # Too close / already ending - skip this market
                        logger.debug("market_rejected_expiry",
                                    market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                    condition_id=m.get("conditionId", "unknown")[:20],
                                    days_to_expiry=dte,
                                    min_hours=min_hours,
                                    reason="too_close")
                        continue
                    # Market passes expiry filter
                    filtered_markets.append(m)
                
                logger.info("markets_after_expiry_filter",
                           fetched=len(markets),
                           filtered=len(filtered_markets),
                           max_days=max_days,
                           min_hours=min_hours)
                
                # 2. Poll trades for each market using conditionId
                total_trades_processed = 0
                for m in filtered_markets:
                    # Initialize safe_vars BEFORE try block - always exists for exception handler
                    safe_vars = {"wallet": "unknown", "condition_id": "unknown"}
                    # Update condition_id from market
                    safe_vars["condition_id"] = m.get("conditionId") or m.get("condition_id") or "unknown"
                    try:
                        event_id = m.get("conditionId") or m.get("condition_id")  # conditionId (0x...) used as 'market' param in Data-API
                        if not event_id:
                            market_info = m.get("title") or m.get("slug") or m.get("market") or "unknown"
                            logger.debug("market_missing_conditionId", market_title=market_info[:50])
                            continue
                        
                        # Validate condition_id before fetching metadata (real Polymarket conditionIds are longer)
                        if len(event_id) < 20 or not event_id.startswith("0x"):
                            logger.debug("bad_condition_id_for_expiry_fetch",
                                        condition_id=event_id[:30],
                                        market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                        note="condition_id too short or invalid, skipping expiry filter")
                            # Keep market - don't reject for bad condition_id
                        else:
                            # Fetch full market metadata to get expiry (if not already in top_markets response)
                            market_meta = await fetch_market_metadata_by_condition(session, event_id)
                            if market_meta:
                                # Try to get expiry from full metadata
                                dte_from_meta = _days_to_expiry(market_meta)
                                if dte_from_meta is not None:
                                    # Apply expiry filter using full metadata (only when expiry is reliably known)
                                    max_days = float(os.getenv("MAX_DAYS_TO_EXPIRY", "9999"))
                                    min_hours = float(os.getenv("MIN_HOURS_TO_EXPIRY", "0"))
                                    if dte_from_meta > max_days:
                                        logger.debug("market_rejected_expiry_from_metadata",
                                                    market_title=market_meta.get("title", m.get("title", "unknown"))[:50],
                                                    condition_id=event_id[:30],
                                                    days_to_expiry=dte_from_meta,
                                                    max_days=max_days,
                                                    reason="too_long")
                                        continue
                                    if dte_from_meta * 24.0 < min_hours:
                                        logger.debug("market_rejected_expiry_from_metadata",
                                                    market_title=market_meta.get("title", m.get("title", "unknown"))[:50],
                                                    condition_id=event_id[:30],
                                                    days_to_expiry=dte_from_meta,
                                                    min_hours=min_hours,
                                                    reason="too_close")
                                        continue
                                    # Expiry found and within limits - keep market
                                else:
                                    # Expiry missing after full fetch - KEEP market (don't reject)
                                    logger.debug("market_expiry_missing_after_full_fetch",
                                                market_title=market_meta.get("title", m.get("title", "unknown"))[:50],
                                                condition_id=event_id[:30],
                                                note="keeping market, expiry not in full metadata")
                                    # Continue processing - don't reject
                            else:
                                # Metadata fetch failed - KEEP market (don't reject)
                                logger.debug("market_metadata_fetch_failed",
                                            condition_id=event_id[:30],
                                            market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                            note="keeping market, metadata fetch returned None")
                                # Continue processing - don't reject
                        
                        # Fetch trades for this market (client-side scanning, 25 pages = 2500 trades max)
                        trades = await fetch_trades_scanned(session, event_id, API_MIN_SIZE_USD, pages=25, limit=100)
                        
                        # Process each trade (use API_MIN_SIZE_USD filter, clustering happens inside process_trade)
                        for trade in trades:
                            # Update wallet in safe_vars dict for exception handling
                            safe_vars["wallet"] = trade.get("proxyWallet") or trade.get("wallet") or trade.get("makerAddress") or "unknown"
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
                            # Get category from market metadata (more accurate than trade inference)
                            # fetch_top_markets now includes category in the returned dict
                            market_category = m.get("category", "").lower().strip() or get_category_from_trade(trade)
                            signal = await process_trade(session, trade, market_category=market_category)
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
                                
                                # Check cluster minimum trades (bypass if enabled)
                                bypass_cluster = os.getenv("BYPASS_CLUSTER_MIN", "False") == "True"
                                trade_count = signal.get("cluster_trades_count", 0)
                                min_trades = int(os.getenv("CLUSTER_MIN_TRADES", "1"))
                                
                                logger.debug("signal_cluster_bypass_check",
                                            bypass_enabled=bypass_cluster,
                                            trade_count=trade_count,
                                            required=min_trades)
                                
                                if not bypass_cluster and trade_count < min_trades:
                                    global rejected_below_cluster_min
                                    rejected_below_cluster_min += 1
                                    logger.debug("signal_rejected", reason="below_cluster_min", 
                                               trade_count=trade_count,
                                               required=min_trades,
                                               wallet=signal.get("wallet", "unknown")[:8])
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
                                signal_wallet = signal.get('wallet', 'unknown')
                                logger.info("signal_generated", 
                                           wallet=signal_wallet[:20] if signal_wallet else "unknown",
                                           discount=signal['discount_pct'],
                                           market=signal['market'][:50],
                                           event_id=event_id)
                                
                                # Signal notification already sent via notify_signal() above
                    except Exception as e:
                        # NEVER let the error logger crash the engine
                        # Use direct dict access, never reference 'wallet' as a variable name
                        try:
                            # Access safe_vars directly - it's always initialized before try block
                            wallet_val = safe_vars.get("wallet", "unknown")
                            condition_val = safe_vars.get("condition_id", "unknown")
                        except Exception:
                            # If safe_vars doesn't exist somehow, use defaults
                            wallet_val = "unknown"
                            condition_val = "unknown"
                        
                        try:
                            logger.error(
                                "market_processing_error",
                                error=str(e),
                                wallet=wallet_val,
                                condition_id=condition_val,
                            )
                        except Exception:
                            # last resort: swallow logging failures
                            pass
                        
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
                           rejected_score_unavailable=rejected_score_unavailable,
                           rejected_discount_missing=rejected_discount_missing,
                           rejected_depth=rejected_depth,
                           rejected_conflicting=rejected_conflicting,
                           rejected_daily_limit=rejected_daily_limit,
                           rejected_other=rejected_other,
                           signals_generated=signals_generated)
                
                # Write status line to file for easy tracking
                append_status_line(
                    f"{datetime.utcnow().isoformat()}Z gate_breakdown "
                    f"trades_considered={trades_considered} signals_generated={signals_generated} "
                    f"rejected_low_score={rejected_low_score} rejected_low_discount={rejected_low_discount} "
                    f"rejected_score_missing={rejected_score_missing} rejected_score_unavailable={rejected_score_unavailable} "
                    f"rejected_discount_missing={rejected_discount_missing} rejected_below_cluster_min={rejected_below_cluster_min} "
                    f"rejected_conflicting={rejected_conflicting} rejected_depth={rejected_depth} "
                    f"rejected_daily_limit={rejected_daily_limit} rejected_other={rejected_other}"
                )
                
                # Audit data quality
                audit_data_quality()
                
                # Clean up old conflicting whales
                cutoff_time = datetime.now() - timedelta(minutes=CONFLICT_WINDOW_MINUTES)
                conflicting_whales.clear()  # Simplified cleanup
                
                # Clean up expired clusters
                cleanup_expired_clusters()
                
                # Calibration mode: log histogram every 10 cycles
                global CALIBRATION_CYCLE_COUNT
                CALIBRATION_CYCLE_COUNT += 1
                if CALIBRATION_CYCLE_COUNT % 10 == 0:
                    log_calibration_histogram()
                
            except Exception as e:
                logger.error("loop_error", error=str(e))
            
            # Wait before next poll
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def shutdown():
    """Cleanup on shutdown."""
    logger.info("engine_shutdown")


async def main():
    """Main entry point."""
    # Force reload .env to ensure latest values
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)  # Force reload, override existing
    except ImportError:
        pass
    
    # Force ENV_SETTINGS log at the very start (before any processing)
    # Use print to ensure it shows up even if logging config is wrong
    env_settings = {
        "INCLUDE_SELL_TRADES": os.getenv("INCLUDE_SELL_TRADES", "False"),
        "MIN_CLUSTER_USD": os.getenv("MIN_CLUSTER_USD", "100.0"),
        "MIN_CLUSTER_TRADES": os.getenv("MIN_CLUSTER_TRADES", "1"),
        "MIN_WHALE_SCORE": os.getenv("MIN_WHALE_SCORE", "0.005"),
        "BYPASS_SCORE_ON_STATS_FAIL": os.getenv("BYPASS_SCORE_ON_STATS_FAIL", "False"),
        "MIN_LOW_DISCOUNT": os.getenv("MIN_LOW_DISCOUNT", "0.0"),
        "BYPASS_CLUSTER_MIN": os.getenv("BYPASS_CLUSTER_MIN", "False"),
        "BYPASS_LOW_DISCOUNT": os.getenv("BYPASS_LOW_DISCOUNT", "False"),
        "MIN_DISCOUNT_PCT": MIN_DISCOUNT_PCT
    }
    print(f"\n🔧 ENV_SETTINGS: {env_settings}\n")  # Force print to console
    logger.info("ENV_SETTINGS", **env_settings)  # Also log normally
    
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

