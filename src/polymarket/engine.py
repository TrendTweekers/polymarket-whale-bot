"""
Polymarket Whale Signal Engine
Polls trades, scores whales, and logs signals to CSV and console.
"""

from pathlib import Path

# Force-load .env from project root (works no matter where you run from)
# MUST be at the very top, before any other imports
try:
    from dotenv import load_dotenv
    ROOT = Path(__file__).resolve().parents[2]  # .../polymarket-whale-engine
    load_dotenv(ROOT / ".env", override=True)
except Exception:
    pass

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
import re
from time import time

# Engine fingerprint for process identification
ENGINE_FINGERPRINT = f"pid={os.getpid()}"

# Debug: Log Telegram config on startup (mask token for security)
try:
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    # Mask token: show only last 4 chars for verification
    tok_masked = f"***{tok[-4:]}" if tok and len(tok) > 4 else "EMPTY"
    print(f"[TELEGRAM_CFG] chat_id={chat} token_tail={tok_masked}")
except Exception:
    pass

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
from src.polymarket.storage import SignalStore
from src.polymarket.paper_trading import should_paper_trade, open_paper_trade, format_paper_trade_telegram
from src.polymarket.resolver import run_resolver_loop, fetch_outcome
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

# Setup logging to respect LOG_LEVEL globally and silence noisy libraries
def _setup_logging_from_env():
    """Configure logging levels from environment, silence noisy libraries."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    
    # Set root logger level from env (handlers will be added later)
    root = logging.getLogger()
    root.setLevel(level)   # Set root level from env
    
    # Silence common noisy libraries unless explicitly needed
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

# Call immediately to set up logging before any other logging happens
_setup_logging_from_env()

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
    # NOTE: Don't clear handlers here - console handler was already added by _setup_logging_from_env()
    # File handlers are added in addition to console handler
    root_logger = logging.getLogger()
    # File logs always DEBUG (for auditing), console level controlled separately
    # Don't change root level here - it's already set by _setup_logging_from_env()
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

# Replace the basic console handler with structlog-aware handler
# Console handler was already added by _setup_logging_from_env(), replace it
root_logger = logging.getLogger()
log_level_value = getattr(logging, LOG_LEVEL, logging.INFO)

# Remove basic console handler and replace with structlog formatter
for handler in root_logger.handlers[:]:
    if isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
        root_logger.removeHandler(handler)

# Add structlog-aware console handler
structlog_console_handler = logging.StreamHandler()
structlog_console_handler.setLevel(log_level_value)  # Respect LOG_LEVEL
structlog_console_formatter = structlog.stdlib.ProcessorFormatter(
    processor=structlog.dev.ConsoleRenderer(),
    foreign_pre_chain=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
    ],
)
structlog_console_handler.setFormatter(structlog_console_formatter)
root_logger.addHandler(structlog_console_handler)

# Ensure structlog loggers respect the level
structlog_logger = logging.getLogger("structlog")
structlog_logger.setLevel(log_level_value)

logger = structlog.get_logger()

# Configuration
POLL_INTERVAL_SECONDS = 30  # Legacy - kept for backward compatibility
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))  # Main scan interval (default 60 seconds)
MIN_WHALE_SCORE = float(os.getenv("MIN_WHALE_SCORE", "0.70"))  # Env-configurable
MIN_ORDERBOOK_DEPTH_MULTIPLIER = 3.0
CONFLICT_WINDOW_MINUTES = 5
MAX_SIGNALS_PER_DAY = int(os.getenv("DAILY_SIGNAL_LIMIT", "0"))  # Daily signal limit (0 = disabled, env-configurable)
MAX_DAILY_LOSS_USD = 50.0
MAX_BANKROLL_PCT_PER_TRADE = 5.0

# Signal de-dupe cooldown (prevents repeated alerts on same market/outcome)
SIGNAL_COOLDOWN_SECONDS = int(os.getenv("SIGNAL_COOLDOWN_SECONDS", "21600"))  # 6 hours default (was 1800)
# Whale signal Telegram cooldown (prevents spam for same market)
WHALE_SIGNAL_COOLDOWN_SECONDS = int(os.getenv("WHALE_SIGNAL_COOLDOWN_SECONDS", "300"))  # 5 minutes default
_recent_signal_keys: dict[tuple, float] = {}  # For signal deduplication
_last_whale_alert_at: dict[str, float] = {}  # condition_id -> timestamp (for Telegram cooldown)

# Market/outcome dedupe: (market_id, outcome_index) -> last_alert_time
_market_outcome_alerts: dict[tuple, float] = {}  # (market_id, outcome_index) -> timestamp

# Market maker/bot detection: track wallets trading both sides in same market
# Structure: {wallet: {market_id: {side: timestamp, ...}}}
_mm_wallet_trades: dict[str, dict[str, dict[str, float]]] = {}  # wallet -> market_id -> side -> timestamp
_mm_blacklist: set[str] = set()  # Wallets detected as market makers/bots
MM_DETECTION_WINDOW_SECONDS = int(os.getenv("MM_DETECTION_WINDOW_SECONDS", "7200"))  # 2 hours default (30-120 min range)

# Whale signal rollup (aggregate multiple wallets/trades per market)
_whale_rollup: defaultdict = defaultdict(lambda: {
    "wallets": set(),
    "trades": 0,
    "total_usd": 0.0,
    "max_trade_usd": 0.0,
    "market": "",
    "outcome_name": None,
    "dedupe_key": None,  # (market_id, outcome_index) for dedupe
    "min_discount": None,  # Track minimum discount in rollup for filtering
})

# Expiry filter configuration
MAX_DAYS_TO_EXPIRY = float(os.getenv("MAX_DAYS_TO_EXPIRY", "2"))
MIN_HOURS_TO_EXPIRY = float(os.getenv("MIN_HOURS_TO_EXPIRY", "2"))
STRICT_SHORT_TERM = os.getenv("STRICT_SHORT_TERM", "1").strip() == "1"  # Reject markets with unknown expiry

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
# Handle empty string, "none", "false", "0" as "no excludes"
raw = os.getenv("EXCLUDE_CATEGORIES", "")
raw = (raw or "").strip()

if raw == "" or raw.lower() in {"none", "no", "false", "0"}:
    EXCLUDE_CATEGORIES = set()
else:
    EXCLUDE_CATEGORIES = {x.strip().lower() for x in raw.split(",") if x.strip()}

# Data collection mode flags (disable blockers temporarily)
# WHITELIST_ONLY can be overridden via environment variable
WHITELIST_ONLY = env_bool("WHITELIST_ONLY", default=(PRODUCTION_MODE is True))

# Override other settings in production mode (unless explicitly set via env)
# MIN_DISCOUNT_PCT can be overridden via env even in production mode
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DISCOUNT_PCT", "2.0" if PRODUCTION_MODE else "2.0"))
# MIN_LOW_DISCOUNT is an alias/alternative name for MIN_DISCOUNT_PCT (for clarity)
MIN_LOW_DISCOUNT = float(os.getenv("MIN_LOW_DISCOUNT", os.getenv("MIN_DISCOUNT_PCT", "0.02")))  # Default 0.02 (2%) minimum edge
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

# Paper trading configuration
PAPER_TRADING = env_bool("PAPER_TRADING", default=False)
PAPER_MIN_CONFIDENCE = int(os.getenv("PAPER_MIN_CONFIDENCE", "60"))  # 0-100
PAPER_STAKE_EUR = float(os.getenv("PAPER_STAKE_EUR", "2.0"))
FX_EUR_USD = float(os.getenv("FX_EUR_USD", "1.10"))
RESOLVER_INTERVAL_SECONDS = int(os.getenv("RESOLVER_INTERVAL_SECONDS", "300"))  # 5 minutes
# Paper trading filters (for fast feedback)
PAPER_MAX_DTE_DAYS = float(os.getenv("PAPER_MAX_DTE_DAYS", "2.0"))  # Only trade markets expiring within N days
PAPER_MIN_DISCOUNT_PCT = float(os.getenv("PAPER_MIN_DISCOUNT_PCT", "0.0001"))  # Minimum discount (as fraction, e.g., 0.0001 = 0.01%)
PAPER_MIN_TRADE_USD = float(os.getenv("PAPER_MIN_TRADE_USD", "50.0"))  # Minimum trade value USD

# Heartbeat configuration
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "600"))  # Default 10 minutes

# Operator dashboard configuration (periodic summary reports)
DASHBOARD_INTERVAL_SECONDS = int(os.getenv("DASHBOARD_INTERVAL_SECONDS", "3600"))  # Default 1 hour (0 = disabled)
# Rolling metrics tracking (last hour)
_rolling_metrics = {
    "signals": [],
    "trades_considered": [],
    "rejections": {},  # reason -> count
    "timestamps": [],  # Keep last hour of timestamps
}

# Minimum cluster USD threshold (env-configurable, lowered default for testing)
MIN_CLUSTER_USD = float(os.getenv("MIN_CLUSTER_USD", "100.0"))

# Two-tier thresholds (env-driven)
API_MIN_SIZE_USD = float(os.getenv("API_MIN_SIZE_USD", "150"))  # API filter (raised from 1000 to reduce noise)
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
           MIN_LOW_DISCOUNT=os.getenv("MIN_LOW_DISCOUNT", "0.02"),
           MIN_DISCOUNT_PCT=MIN_DISCOUNT_PCT,
           BYPASS_CLUSTER_MIN=os.getenv("BYPASS_CLUSTER_MIN", "False"),
           BYPASS_LOW_DISCOUNT=os.getenv("BYPASS_LOW_DISCOUNT", "False"),
           DAILY_SIGNAL_LIMIT=MAX_SIGNALS_PER_DAY,
           MAX_DAYS_TO_EXPIRY=MAX_DAYS_TO_EXPIRY,
           MIN_HOURS_TO_EXPIRY=MIN_HOURS_TO_EXPIRY,
           STRICT_SHORT_TERM=STRICT_SHORT_TERM,
           EXCLUDE_CATEGORIES_RAW=os.getenv("EXCLUDE_CATEGORIES", ""),
           EXCLUDE_CATEGORIES_PARSED=list(EXCLUDE_CATEGORIES) if EXCLUDE_CATEGORIES else [],
           API_MIN_SIZE_USD=API_MIN_SIZE_USD,
           SIGNAL_COOLDOWN_SECONDS=SIGNAL_COOLDOWN_SECONDS,
           MM_DETECTION_WINDOW_SECONDS=MM_DETECTION_WINDOW_SECONDS)

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
rejected_other_reasons = {}  # Track specific reasons for rejected_other
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
        logger.warning(
            "orderbook_depth_fetch_failed",
            extra={
                "event": "orderbook_depth_fetch_failed",
                "error": str(e),
            }
        )
        return 0.0


def append_status_line(status: str) -> None:
    """Append a status line to the daily status log file."""
    Path("logs").mkdir(exist_ok=True)
    day = datetime.utcnow().strftime("%Y-%m-%d")
    path = Path("logs") / f"status_{day}.log"
    with path.open("a", encoding="utf-8") as f:
        f.write(status.rstrip() + "\n")


def infer_category_from_title_slug(title: str, slug: str) -> str | None:
    """
    Infer category from title/slug patterns when API doesn't provide category.
    Returns inferred category or None if no match.
    """
    t = (title or "").lower()
    s = (slug or "").lower()
    text = f"{t} {s}".lower()  # Combined text for pattern matching

    # esports / CS2 patterns (check before general sports to catch specific esports terms)
    esports_keys = [
        "cs2", "counter-strike", "counter strike", "bo1", "bo3", "bo5",
        "to win 0 maps", "to win 1 maps", "to win 2 maps",
        "map handicap", "handicap", "total maps", "games total"
    ]
    if any(k in t for k in esports_keys) or any(k in s for k in esports_keys):
        return "sports"

    # --- SPORTS (soccer / football fast-path) ---
    # Check for soccer/football patterns before other sports checks
    soccer_football_keys = [
        "fc ", " fc", "vs", " v ", "match", "cup", "league", "semifinal", "quarterfinal", "final",
        "barcelona", "real madrid", "manchester", "chelsea", "arsenal", "liverpool", "bayern",
        "juventus", "psg", "inter", "milan", "atletico", "dortmund", "tottenham", "napoli"
    ]
    if any(k in text for k in soccer_football_keys):
        return "sports"
    
    # Also handle "Sports Personality of the Year" etc.
    if "sports personality" in text or "player of the year" in text:
        return "sports"

    # obvious sports patterns (only if there's a league/team pattern or "vs" to avoid false positives)
    sports_leagues = ["nhl", "nfl", "nba", "mlb", "ncaaf", "ncaab", "premier league", "champions league", "epl"]
    has_sports_context = any(league in t or league in s for league in sports_leagues) or " vs " in t or " vs " in s
    
    # Only infer sports if there's a sports context (league/team/vs) AND sports keywords
    if has_sports_context and (any(x in t for x in ["spread:", "moneyline", "total:", "over", "under"]) or any(x in s for x in sports_leagues)):
        return "sports"

    # commodities: Crude Oil, Gold, WTI, Brent, CL, GC (check BEFORE stocks to avoid false positives)
    commodity_keywords = ["crude oil", "wti", "brent", "gold", "silver", "copper", "natural gas", "oil", "cl ", "gc "]
    if any(kw in t for kw in commodity_keywords):
        return "commodities"

    # stocks: titles with (...ticker...) + "after earnings", "up or down"
    # Pattern: (TICKER) or ticker followed by earnings/up or down
    ticker_pattern = r"\([A-Z]{1,5}\)"  # Matches (AAPL), (TSLA), etc.
    if re.search(ticker_pattern, title or ""):
        if any(phrase in t for phrase in ["after earnings", "up or down", "earnings"]):
            return "stocks"
    
    # Also check for common stock tickers without parentheses
    stock_keywords = ["fds", "factset", "earnings", "revenue", "eps", "guidance"]
    if any(kw in t for kw in stock_keywords) and ("up or down" in t or "after earnings" in t):
        return "stocks"

    # macro: eggs/gas/CPI/inflation/jobs/rates
    macro_keywords = ["cpi", "inflation", "unemployment", "jobs report", "fed rate", "interest rate", "gas price", "dozen eggs", "gdp"]
    if any(kw in t for kw in macro_keywords):
        return "macro"

    # celebrity/social: Elon/tweets/celebrity posts
    celebrity_keywords = ["elon", "musk", "tweet", "twitter", "celebrity", "kardashian", "trump tweet"]
    if any(kw in t for kw in celebrity_keywords):
        return "social"

    # obvious crypto patterns (only specific crypto tokens, not generic "up or down")
    crypto_tokens = ["bitcoin", "ethereum", "solana", "xrp", "btc", "eth", "sol", "matic", "avax", "ada", "dot", "link"]
    if any(x in t for x in crypto_tokens) or any(x in s for x in crypto_tokens + ["crypto"]):
        return "crypto"

    # politics/elections
    if any(x in t for x in ["election", "primary", "senate", "president", "congress", "governor", "poll"]) or "election" in s:
        return "politics"

    return None


def get_category_from_trade(trade: Dict) -> str:
    """Extract category from trade data (fallback only, should not be used normally)."""
    # Try to infer from slug or title
    slug = trade.get("slug", "").lower()
    title = trade.get("title", "").lower()
    
    inferred = infer_category_from_title_slug(title, slug)
    if inferred:
        return inferred
    
    if any(word in slug or word in title for word in ["bitcoin", "crypto", "ethereum", "btc", "eth"]):
        return "crypto"
    elif any(word in slug or word in title for word in ["election", "president", "vote", "poll"]):
        return "elections"
    elif any(word in slug or word in title for word in ["sport", "nfl", "nba", "nhl", "mlb", "soccer", "football", "oilers", "lakers", "arsenal"]):
        return "sports"
    elif any(word in slug or word in title for word in ["country", "geo", "nation", "state"]):
        return "geo"
    else:
        return "unknown"  # Default (never lie)


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
        logger.error(
            "whale_stats_fetch_failed",
            extra={
                "event": "whale_stats_fetch_failed",
                "wallet": wallet[:20],
                "error": str(e),
            }
        )
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
        logger.error(
            "whale_stats_fetch_failed",
            extra={
                "event": "whale_stats_fetch_failed",
                "wallet": wallet[:20],
                "error": str(e),
            }
        )
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
    # Only enforce signal limit if MAX_SIGNALS_PER_DAY > 0
    if MAX_SIGNALS_PER_DAY > 0 and len(recent_signals) >= MAX_SIGNALS_PER_DAY:
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


def _parse_dt_any(v) -> Optional[datetime]:
    """
    Accepts:
      - ISO strings: "2025-12-16T09:00:00Z", "2025-12-16T09:00:00.000Z"
      - unix seconds / ms (int/float)
    Returns timezone-aware UTC datetime or None.
    """
    if v is None or v == "":
        return None

    # unix timestamp
    if isinstance(v, (int, float)):
        # detect ms
        ts = float(v)
        if ts > 1e12:
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            return None

    # ISO string
    if isinstance(v, str):
        s = v.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    return None


# Whitelist of ONLY real expiry fields (never startDate, createdAt, etc.)
EXPIRY_KEYS = [
    "endDate", "end_date",
    "endDateIso", "endDateISO", "end_date_iso",
    "closeTime", "close_time",
    "resolutionTime", "resolution_time",
    "expiry", "expiresAt", "expires_at",
]


def _days_to_expiry(market: dict) -> Optional[float]:
    """
    Gamma can use different keys, sometimes nested under event/events.
    ONLY uses whitelisted expiry fields (never startDate, createdAt, etc.).
    """
    if not isinstance(market, dict):
        return None

    ev = market.get("event") if isinstance(market.get("event"), dict) else {}
    ev0 = (market.get("events") or [{}])[0] if isinstance(market.get("events"), list) and market.get("events") else {}

    candidates = []
    for src in (market, ev, ev0):
        for k in EXPIRY_KEYS:
            if k in src:
                candidates.append(src.get(k))

    for v in candidates:
        dt = _parse_dt_any(v)
        if dt:
            now = datetime.now(timezone.utc)
            days = (dt - now).total_seconds() / 86400.0
            # Reject negative values (expired markets) - treat as unknown
            if days < 0:
                return None
            return days

    return None


# Title date parsing for safety net
_TITLE_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})\b",
    re.IGNORECASE
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
}


def _title_days_to_expiry(title: str) -> Optional[float]:
    """
    Parse expiry date from market title (e.g., "Will X happen by December 31, 2025?").
    Returns days to expiry or None if no date found.
    """
    if not title:
        return None
    m = _TITLE_DATE_RE.search(title)
    if not m:
        return None
    mon = _MONTHS[m.group(1).lower()]
    day = int(m.group(2))
    year = int(m.group(3))
    try:
        dt = datetime(year, mon, day, 23, 59, 59, tzinfo=timezone.utc)
    except Exception:
        return None
    now = datetime.now(timezone.utc)
    days = (dt - now).total_seconds() / 86400.0
    # Reject negative values (expired markets) - treat as unknown
    if days < 0:
        return None
    return days


def _passes_strict_expiry_gate(market_obj: dict) -> tuple[bool, str]:
    """
    Check if market passes strict expiry gate at signal emission time.
    Returns (ok, reason) tuple.
    """
    dte = _days_to_expiry(market_obj)
    if dte is None:
        return (not STRICT_SHORT_TERM), "expiry_unknown"
    if dte * 24.0 < float(MIN_HOURS_TO_EXPIRY):
        return False, "too_soon"
    if dte > float(MAX_DAYS_TO_EXPIRY):
        return False, "too_long"
    return True, "ok"


def calculate_discount(whale_entry_price: float, current_price: float, side: str = "BUY") -> Optional[float]:
    """
    Calculate discount as a fraction (edge/advantage).
    For BUY: positive discount means you bought below market (good)
    For SELL: positive discount means you sold above market (good)
    Returns discount as a fraction (e.g., 0.05 for 5%, 0.0005 for 0.05%).
    Multiply by 100 only when displaying to user.
    Returns None if prices are missing/invalid (instead of silently returning 0.0).
    """
    # Reject if either price is missing or invalid
    if whale_entry_price is None or whale_entry_price <= 0:
        return None
    if current_price is None or current_price < 0:
        return None
    
    # Calculate discount based on side
    # Returns fraction (0.05 = 5%), NOT percentage
    if side.upper() == "BUY":
        # For BUY: discount = (current_price - entry_price) / current_price
        # Positive means you bought below market (good)
        discount = (current_price - whale_entry_price) / current_price
    else:
        # For SELL: discount = (entry_price - current_price) / entry_price
        # Positive means you sold above market (good)
        discount = (whale_entry_price - current_price) / whale_entry_price
    
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


async def process_trade(session: aiohttp.ClientSession, trade: Dict, market_category: Optional[str] = None, category_inferred: bool = False, market_obj: Optional[Dict] = None) -> Optional[Dict]:
    """
    Process a trade and generate signal if conditions are met.
    Returns signal dict if generated, None otherwise.
    """
    # Declare all global variables at the top of the function
    global rejected_conflicting, rejected_low_score, rejected_discount_missing
    global rejected_below_cluster_min, rejected_low_discount, rejected_depth
    global rejected_score_unavailable, rejected_other, rejected_other_reasons
    
    # Extract wallet at the very top (before any usage)
    trade_wallet = trade.get("proxyWallet") or trade.get("wallet") or trade.get("makerAddress", "")
    if not trade_wallet:
        trade_wallet = "unknown"
    
    # Check daily limits
    can_proceed, reason = check_daily_limits()
    if not can_proceed:
        rejected_other += 1
        rejected_other_reasons["daily_limit"] = rejected_other_reasons.get("daily_limit", 0) + 1
        logger.debug("trade_rejected_other", wallet=trade_wallet[:8] if trade_wallet != "unknown" else "unknown", specific_reason="daily_limit", details=reason)
        return None
    
    if trade_wallet == "unknown":
        rejected_other += 1
        rejected_other_reasons["no_wallet"] = rejected_other_reasons.get("no_wallet", 0) + 1
        logger.debug("trade_rejected_other", wallet="unknown", specific_reason="no_wallet", details="proxyWallet and makerAddress both missing")
        return None
    
    # Use passed market_category (from market object), fallback to "unknown" if not provided
    category = (market_category or "unknown").lower().strip()
    
    # Exclude categories (early filter, before scoring/discount work)
    if category and category in EXCLUDE_CATEGORIES:
        rejected_other += 1
        rejected_other_reasons["excluded_category"] = rejected_other_reasons.get("excluded_category", 0) + 1
        logger.debug("trade_rejected_other", wallet=trade_wallet[:8], specific_reason="excluded_category", details=f"category={category}")
        return None
    
    side = trade.get("side", "BUY")
    include_sells = os.getenv("INCLUDE_SELL_TRADES", "False") == "True"
    logger.debug("sell_trade_check",
                include_sells=include_sells,
                trade_side=side.upper())
    if not include_sells and side.upper() == "SELL":
        rejected_other += 1
        rejected_other_reasons["sell_trade"] = rejected_other_reasons.get("sell_trade", 0) + 1
        logger.debug("trade_rejected_other",
                    wallet=trade_wallet[:8],
                    specific_reason="sell_trade",
                    details=f"side={side}, INCLUDE_SELL_TRADES={include_sells}")
        return None  # skip SELL trades unless INCLUDE_SELL_TRADES=True
    
    # Check for conflicting whale
    if check_conflicting_whale(trade_wallet, side):
        rejected_conflicting += 1
        logger.debug("conflicting_whale", wallet=trade_wallet[:20])
        return None
    
    # Check if wallet is blacklisted as market maker/bot
    if trade_wallet in _mm_blacklist:
        rejected_other += 1
        rejected_other_reasons["mm_bot_blacklist"] = rejected_other_reasons.get("mm_bot_blacklist", 0) + 1
        logger.debug("trade_rejected_mm_bot", wallet=trade_wallet[:8], reason="blacklisted")
        return None
    
    # Market maker/bot detection: track trades by wallet+market+side
    market_id = trade.get("marketId") or trade.get("market_id") or ""
    if market_id and trade_wallet != "unknown":
        now_ts = time()
        if trade_wallet not in _mm_wallet_trades:
            _mm_wallet_trades[trade_wallet] = {}
        if market_id not in _mm_wallet_trades[trade_wallet]:
            _mm_wallet_trades[trade_wallet][market_id] = {}
        
        # Check if wallet traded opposite side in this market recently
        opposite_side = "SELL" if side.upper() == "BUY" else "BUY"
        if opposite_side in _mm_wallet_trades[trade_wallet][market_id]:
            last_opposite_time = _mm_wallet_trades[trade_wallet][market_id][opposite_side]
            time_diff = now_ts - last_opposite_time
            if time_diff <= MM_DETECTION_WINDOW_SECONDS:
                # Wallet traded both sides within detection window - mark as MM/bot
                _mm_blacklist.add(trade_wallet)
                rejected_other += 1
                rejected_other_reasons["mm_bot_detected"] = rejected_other_reasons.get("mm_bot_detected", 0) + 1
                logger.info("mm_bot_detected", 
                           wallet=trade_wallet[:8], 
                           market_id=market_id[:20],
                           time_diff_seconds=time_diff,
                           side=side,
                           opposite_side=opposite_side)
                return None
        
        # Record this trade
        _mm_wallet_trades[trade_wallet][market_id][side.upper()] = now_ts
        
        # Cleanup old entries (keep only recent trades within detection window)
        for mkt_id in list(_mm_wallet_trades[trade_wallet].keys()):
            for s in list(_mm_wallet_trades[trade_wallet][mkt_id].keys()):
                if now_ts - _mm_wallet_trades[trade_wallet][mkt_id][s] > MM_DETECTION_WINDOW_SECONDS:
                    del _mm_wallet_trades[trade_wallet][mkt_id][s]
            if not _mm_wallet_trades[trade_wallet][mkt_id]:
                del _mm_wallet_trades[trade_wallet][mkt_id]
    
    # Category already set above from market object (never infer from trade)
    
    # Calculate trade USD early for fallback scoring
    whale_entry_price = trade.get("price")
    if whale_entry_price is None or whale_entry_price <= 0:
        rejected_other += 1
        rejected_other_reasons["missing_entry_price"] = rejected_other_reasons.get("missing_entry_price", 0) + 1
        logger.debug("trade_rejected_other", wallet=trade_wallet[:8], specific_reason="missing_entry_price", details=f"price={whale_entry_price}")
        return None
    
    size = trade.get("size", 0.0)
    trade_usd = size * whale_entry_price
    
    # Get whale stats/score (whitelist check only if WHITELIST_ONLY is True)
    if WHITELIST_ONLY:
        whale = await ensure_whale_whitelisted(session, trade_wallet, category, trade_usd)
        if not whale:
            rejected_low_score += 1
            logger.debug("trade_rejected", reason="whale_not_whitelisted", wallet=trade_wallet[:8], category=category)
            return None
    else:
        # Whitelist disabled: just get score, don't enforce whitelist gate
        whale = await get_whale_with_score(session, trade_wallet, category, trade_usd)
        if not whale:
            rejected_low_score += 1
            logger.debug("trade_rejected", reason="whale_score_unavailable", wallet=trade_wallet[:8], category=category)
            return None
    
    # Fetch current price from CLOB midpoint endpoint using token_id
    condition_id = trade.get("conditionId", "")
    if not condition_id:
        logger.debug("trade_rejected", reason="missing_condition_id", wallet=trade_wallet[:8])
        return None
    
    # Extract token_id from trade (Path A: prefer "asset" field - most reliable)
    # "asset" is the outcome token id that the trade is actually for
    token_id = (trade.get("asset") or trade.get("token_id") or 
                trade.get("tokenId") or trade.get("clobTokenId") or 
                trade.get("asset_id") or trade.get("outcomeId"))
    
    outcome_name = trade.get("outcome") or trade.get("name", "")
    outcome_index = trade.get("outcomeIndex")
    
    # Path B: If not in trade, get from conditionId → clobTokenIds mapping
    if not token_id:
        side = trade.get("side", "BUY")
        token_id = get_token_id_for_condition(condition_id, side)
    
    # Path C: Try Gamma API to resolve token_id from condition_id and trade outcome
    if not token_id:
        token_id = await get_token_id(condition_id, trade, session)
        if token_id:
            logger.debug("token_id_resolved",
                        wallet=trade_wallet[:8],
                        condition_id=condition_id[:20],
                        token_id=str(token_id)[:20],
                        outcome=outcome_name)
    
    if not token_id:
        rejected_other += 1
        rejected_other_reasons["token_id_resolve_failed"] = rejected_other_reasons.get("token_id_resolve_failed", 0) + 1
        logger.debug("trade_rejected", 
                    wallet=trade_wallet[:8], 
                    reason="token_id_resolve_failed", 
                    condition_id=condition_id[:20],
                    outcome=outcome_name)
        return None
    
    # Fetch midpoint price: try CLOB first, fallback to Gamma market bestBid/bestAsk
    current_price = await get_midpoint_price_cached(session, str(token_id))
    
    # Fallback to Gamma market midpoint if CLOB fails
    if current_price is None and condition_id:
        current_price = await get_market_midpoint_cached(session, condition_id)
    
    if current_price is None:
        rejected_discount_missing += 1
        logger.debug("trade_rejected", reason="rejected_discount_missing", 
                    wallet=trade_wallet[:8], token_id=str(token_id)[:20] if token_id else None, 
                    condition_id=condition_id[:20])
        return None
    
    # Safety: If trade is for "No" or "Down" outcome and midpoint seems wrong, flip it
    # Binary markets: if outcome is "No"/"Down" and midpoint is very low (< 0.1), 
    # we might have fetched the "Yes"/"Up" midpoint - flip it
    outcome_lower = outcome_name.lower() if outcome_name else ""
    is_no_or_down = outcome_lower in ["no", "down"] or (outcome_index == 1 and outcome_lower != "yes")
    
    if is_no_or_down and current_price is not None and current_price < 0.1:
        # Likely fetched midpoint for opposite outcome - flip it
        flipped_price = 1.0 - current_price
        logger.debug("midpoint_flipped_for_outcome",
                    wallet=trade_wallet[:8],
                    outcome_name=outcome_name,
                    original_midpoint=current_price,
                    flipped_midpoint=flipped_price,
                    token_id=str(token_id)[:20])
        current_price = flipped_price
    
    # Store the token_id we actually used for midpoint fetching (for signal dict and logs)
    token_id_used = str(token_id) if token_id else None
    
    # Calculate discount: entry_price vs current midpoint
    side = trade.get("side", "BUY")
    discount_pct = calculate_discount(whale_entry_price, current_price, side)
    
    # Debug discount calculation
    logger.debug("discount_calc_debug",
                wallet=trade_wallet[:8],
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
                    wallet=trade_wallet[:8], entry_price=whale_entry_price, current_price=current_price)
        return None
    
    # Log ALL whale activity for analysis (before filtering)
    # Note: trade_usd already calculated above
    market_id = trade.get("conditionId", trade.get("slug", "unknown"))
    logger.debug("whale_activity", wallet=trade_wallet[:20], score=whale["score"], discount=discount_pct, size_usd=trade_usd)
    log_all_activity(market_id, trade_wallet, whale["score"], discount_pct, trade_usd)
    
    # Calibration mode: track whale score for histogram analysis
    global whale_score_samples
    if len(whale_score_samples) < WHALE_SCORE_SAMPLES_MAX:
        whale_score_samples.append({
            "wallet": trade_wallet,
            "condition_id": condition_id,
            "trade_usd": trade_usd,
            "whale_score": whale["score"]
        })
    elif len(whale_score_samples) >= WHALE_SCORE_SAMPLES_MAX:
        # Rotate: remove oldest 10% when full
        whale_score_samples = whale_score_samples[int(WHALE_SCORE_SAMPLES_MAX * 0.1):]
        whale_score_samples.append({
            "wallet": trade_wallet,
            "condition_id": condition_id,
            "trade_usd": trade_usd,
            "whale_score": whale["score"]
        })
    
    # Check if trade meets minimum size for clustering (bypass if enabled)
    # Check cluster minimum - respect CLUSTER_MIN_USD from env (or MIN_CLUSTER_USD)
    bypass_cluster = os.getenv("BYPASS_CLUSTER_MIN", "False") == "True"
    cluster_min_usd = float(os.getenv("CLUSTER_MIN_USD", os.getenv("MIN_CLUSTER_USD", "100.0")))
    
    # If cluster min is 0 or negative, bypass the check entirely
    if cluster_min_usd <= 0:
        bypass_cluster = True
    
    logger.debug("trade_cluster_bypass_check",
                bypass_enabled=bypass_cluster,
                trade_usd=trade_usd,
                required=cluster_min_usd)
    
    if not bypass_cluster and trade_usd < cluster_min_usd:
        rejected_below_cluster_min += 1
        logger.debug("trade_rejected_other",
                    wallet=trade_wallet[:8],
                    specific_reason="below_cluster_min",
                    details=f"size_usd={trade_usd}, required={cluster_min_usd}")
        return None
    
    if trade_usd >= MIN_CLUSTER_USD:
        # Single trade already meets threshold - check other filters and generate signal directly
        bypass_discount = os.getenv("BYPASS_LOW_DISCOUNT", "False") == "True"
        # MIN_LOW_DISCOUNT is in percentage (e.g., 0.01 = 0.01%), convert to fraction for comparison
        # discount_pct is now a fraction (0.0005 = 0.05%), so convert threshold to fraction too
        min_discount_pct = float(os.getenv("MIN_LOW_DISCOUNT", "0.0"))
        min_discount = min_discount_pct / 100.0  # Convert percentage to fraction (0.01% -> 0.0001)
        
        logger.debug("discount_bypass_check",
                    bypass_enabled=bypass_discount,
                    calculated_discount=discount_pct,
                    min_required=min_discount,
                    min_required_pct=min_discount_pct,
                    entry_price=whale_entry_price,
                    midpoint=current_price if current_price else "none")
        
        if not bypass_discount and discount_pct < min_discount:
            rejected_low_discount += 1
            logger.debug("trade_rejected_low_discount",
                        wallet=trade_wallet[:8],
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
            logger.debug("trade_rejected", reason="insufficient_depth", depth=depth_ratio, wallet=trade_wallet[:8])
            return None
        
        # --- STRICT SHORT TERM: hard gate at signal emission ---
        # Require expiry to be known and within window when STRICT_SHORT_TERM=1
        if STRICT_SHORT_TERM:
            market_for_expiry = market_obj or {}
            market_title = (market_for_expiry.get("title") or market_for_expiry.get("question") or trade.get("title") or "")
            
            # Paranoia safety net: check title for far-future dates
            title_dte = _title_days_to_expiry(market_title)
            if title_dte is not None and title_dte > MAX_DAYS_TO_EXPIRY:
                rejected_other += 1
                rejected_other_reasons["expiry_title_safety_net"] = rejected_other_reasons.get("expiry_title_safety_net", 0) + 1
                event_id = trade.get("conditionId") or trade.get("condition_id") or "unknown"
                logger.info("signal_rejected_expiry_title_safety_net",
                           title_dte=title_dte,
                           max_days=MAX_DAYS_TO_EXPIRY,
                           market_title=market_title[:120],
                           event_id=event_id[:20] if isinstance(event_id, str) else str(event_id)[:20])
                return None
            
            dte = _days_to_expiry(market_for_expiry)
            if dte is None:
                rejected_other += 1
                rejected_other_reasons["expiry_unknown"] = rejected_other_reasons.get("expiry_unknown", 0) + 1
                event_id = trade.get("conditionId") or trade.get("condition_id") or "unknown"
                logger.info("signal_rejected_expiry",
                           title=market_title[:120],
                           event_id=event_id[:20] if isinstance(event_id, str) else str(event_id)[:20],
                           reason="expiry_unknown_at_emit")
                return None
            if dte > MAX_DAYS_TO_EXPIRY:
                rejected_other += 1
                rejected_other_reasons["expiry_too_long"] = rejected_other_reasons.get("expiry_too_long", 0) + 1
                event_id = trade.get("conditionId") or trade.get("condition_id") or "unknown"
                logger.info("signal_rejected_expiry",
                           title=market_title[:120],
                           event_id=event_id[:20] if isinstance(event_id, str) else str(event_id)[:20],
                           days_to_expiry=dte,
                           reason="too_long_at_emit")
                return None
            if dte * 24.0 < MIN_HOURS_TO_EXPIRY:
                rejected_other += 1
                rejected_other_reasons["expiry_too_soon"] = rejected_other_reasons.get("expiry_too_soon", 0) + 1
                event_id = trade.get("conditionId") or trade.get("condition_id") or "unknown"
                logger.info("signal_rejected_expiry",
                           title=market_title[:120],
                           event_id=event_id[:20] if isinstance(event_id, str) else str(event_id)[:20],
                           days_to_expiry=dte,
                           reason="too_soon_at_emit")
                return None
        
        # Paranoia guard: verify trade's condition_id matches market's condition_id
        trade_condition_id = (
            trade.get("conditionId")
            or trade.get("condition_id")
            or trade.get("marketId")
            or trade.get("market_id")
            or "unknown"
        )
        
        market_condition_id = (
            (market_obj or {}).get("conditionId")
            or (market_obj or {}).get("condition_id")
            or "unknown"
        )
        
        if trade_condition_id != "unknown" and market_condition_id != "unknown":
            # Normalize for comparison (handle hex with/without 0x prefix)
            def _normalize_cid(cid: str) -> str:
                if not cid or cid == "unknown":
                    return ""
                cid = str(cid).lower().strip()
                if cid.startswith("0x"):
                    return cid
                if all(c in "0123456789abcdef" for c in cid):
                    return f"0x{cid}"
                return cid
            
            trade_norm = _normalize_cid(trade_condition_id)
            market_norm = _normalize_cid(market_condition_id)
            
            if trade_norm and market_norm and trade_norm != market_norm:
                rejected_other += 1
                rejected_other_reasons["trade_market_mismatch"] = rejected_other_reasons.get("trade_market_mismatch", 0) + 1
                logger.warning("trade_market_condition_mismatch",
                            requested_market_condition_id=market_condition_id[:20],
                            trade_condition_id=trade_condition_id[:20],
                            wallet=trade_wallet[:8])
                return None
        
        # Calculate days_to_expiry for signal (for debugging/display)
        market_for_expiry = market_obj or {}
        dte = _days_to_expiry(market_for_expiry)
        
        # Generate signal directly (single trade ≥ $10k)
        # Extract outcome fields from trade
        outcome_name = trade.get("outcome") or trade.get("name", "")
        outcome_index = trade.get("outcomeIndex") or trade.get("outcome_index")
        
        signal = {
            "timestamp": datetime.now().isoformat(),
            "wallet": trade_wallet,
            "whale_score": whale["score"],
            "category": category,
            "category_inferred": category_inferred,
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
            "days_to_expiry": dte,  # Add for debugging/display
            "token_id": token_id_used,  # Store the token_id we actually used for midpoint fetching
            "outcome_name": outcome_name,  # Store outcome name for paper trades
            "outcome_index": outcome_index,  # Store outcome index for paper trades
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
    cluster_wallet = trade.get("proxyWallet") or trade.get("wallet") or trade.get("makerAddress", "")
    if not cluster_wallet:
        cluster_wallet = "unknown"
    market_id = trade.get("conditionId", trade.get("slug", "unknown"))
    cluster_key = get_cluster_key(cluster_wallet, market_id)
    
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
            "wallet": cluster_wallet,
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
                wallet=cluster_wallet[:20] if cluster_wallet != "unknown" else "unknown",
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
                            wallet=cluster_wallet[:8] if cluster_wallet != "unknown" else "unknown",
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
                        wallet=cluster_wallet[:20] if cluster_wallet != "unknown" else "unknown")
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
    
    # Extract token_id from first trade (Path A: prefer "asset" field - most reliable)
    # "asset" is the outcome token id that the trade is actually for
    first_trade = cluster["trades"][0]
    token_id = (first_trade.get("asset") or first_trade.get("token_id") or 
                first_trade.get("tokenId") or first_trade.get("clobTokenId") or 
                first_trade.get("asset_id") or first_trade.get("outcomeId"))
    
    outcome_name = first_trade.get("outcome") or first_trade.get("name", "")
    outcome_index = first_trade.get("outcomeIndex")
    
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
                    outcome=outcome_name)
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
    
    # Safety: If trade is for "No" or "Down" outcome and midpoint seems wrong, flip it
    # Binary markets: if outcome is "No"/"Down" and midpoint is very low (< 0.1), 
    # we might have fetched the "Yes"/"Up" midpoint - flip it
    outcome_lower = outcome_name.lower() if outcome_name else ""
    is_no_or_down = outcome_lower in ["no", "down"] or (outcome_index == 1 and outcome_lower != "yes")
    
    if is_no_or_down and current_price is not None and current_price < 0.1:
        # Likely fetched midpoint for opposite outcome - flip it
        flipped_price = 1.0 - current_price
        logger.debug("cluster_midpoint_flipped_for_outcome",
                    wallet=cluster["wallet"][:8],
                    outcome_name=outcome_name,
                    original_midpoint=current_price,
                    flipped_midpoint=flipped_price,
                    token_id=str(token_id)[:20])
        current_price = flipped_price
    
    # Store the token_id we actually used for midpoint fetching (for signal dict and logs)
    token_id_used = str(token_id) if token_id else None
    
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
    # MIN_LOW_DISCOUNT is in percentage (e.g., 0.01 = 0.01%), convert to fraction for comparison
    # discount_pct is now a fraction (0.0005 = 0.05%), so convert threshold to fraction too
    min_discount_pct = float(os.getenv("MIN_LOW_DISCOUNT", "0.0"))
    min_discount = min_discount_pct / 100.0  # Convert percentage to fraction (0.01% -> 0.0001)
    
    logger.debug("cluster_discount_bypass_check",
                bypass_enabled=bypass_discount,
                calculated_discount=discount_pct,
                min_required=min_discount,
                min_required_pct=min_discount_pct,
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
    signal_category = None
    category_inferred = False
    market_title = cluster.get("market_title", "Unknown")
    market_slug = cluster.get("slug", "")
    
    if market_meta and market_meta.get("category"):
        signal_category = market_meta["category"].lower().strip()
        market_title = market_meta.get("title", market_title)
        market_slug = market_meta.get("slug", market_slug)
    else:
        signal_category = cluster.get("category", "").lower().strip()
    
    # Infer category if still unknown
    if not signal_category or signal_category == "unknown":
        inferred = infer_category_from_title_slug(market_title, market_slug)
        if inferred:
            signal_category = inferred
            category_inferred = True
        else:
            signal_category = "unknown"
            # Debug log for unknown categories to discover available fields
            candidate_keys = ["tags", "groupSlug", "eventSlug", "marketType", "category", "raw_category", "marketCategory"]
            available_fields = {}
            for key in candidate_keys:
                val = market_meta.get(key) if market_meta else None
                if val:
                    available_fields[key] = str(val)[:50]  # Truncate long values
            logger.debug("market_category_debug",
                        category="unknown",
                        title=market_title[:100],
                        slug=market_slug[:50],
                        available_fields=available_fields if available_fields else "none",
                        market_meta_keys=list(market_meta.keys())[:20] if market_meta else "none")
    
    # Exclude categories filter (even for normal signals)
    if signal_category and signal_category in EXCLUDE_CATEGORIES:
        logger.debug("signal_rejected", category=signal_category, reason="excluded_category")
        return None
    
    # --- STRICT SHORT TERM: hard gate at signal emission ---
    # Require expiry to be known and within window when STRICT_SHORT_TERM=1
    market_obj_for_expiry = market_meta if market_meta else {
        "title": market_title,
        "slug": market_slug,
        "conditionId": condition_id,
    }
    
    if STRICT_SHORT_TERM:
        # Paranoia safety net: check title for far-future dates
        title_dte = _title_days_to_expiry(market_title)
        if title_dte is not None and title_dte > MAX_DAYS_TO_EXPIRY:
            logger.info("signal_rejected_expiry_title_safety_net",
                       title_dte=title_dte,
                       max_days=MAX_DAYS_TO_EXPIRY,
                       market_title=market_title[:120],
                       event_id=condition_id[:20] if condition_id else "unknown")
            return None
        
        dte = _days_to_expiry(market_obj_for_expiry)
        if dte is None:
            logger.info("signal_rejected_expiry",
                       title=market_title[:120],
                       event_id=condition_id[:20] if condition_id else "unknown",
                       reason="expiry_unknown_at_emit")
            return None
        if dte > MAX_DAYS_TO_EXPIRY:
            logger.info("signal_rejected_expiry",
                       title=market_title[:120],
                       event_id=condition_id[:20] if condition_id else "unknown",
                       days_to_expiry=dte,
                       reason="too_long_at_emit")
            return None
        if dte * 24.0 < MIN_HOURS_TO_EXPIRY:
            logger.info("signal_rejected_expiry",
                       title=market_title[:120],
                       event_id=condition_id[:20] if condition_id else "unknown",
                       days_to_expiry=dte,
                       reason="too_soon_at_emit")
            return None
    
    # Extract outcome fields from first trade
    outcome_name = first_trade.get("outcome") or first_trade.get("name", "")
    outcome_index = first_trade.get("outcomeIndex") or first_trade.get("outcome_index")
    
    signal = {
        "timestamp": datetime.now().isoformat(),
        "wallet": cluster["wallet"],
        "whale_score": cluster["whale"]["score"],
        "category": signal_category,
        "category_inferred": category_inferred,
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
        "days_to_expiry": dte,  # Add for debugging/display
        "token_id": token_id_used,  # Store the token_id we actually used for midpoint fetching
        "outcome_name": outcome_name,  # Store outcome name for paper trades
        "outcome_index": outcome_index,  # Store outcome index for paper trades
    }
    
    logger.info("cluster_signal_generated",
                wallet=cluster["wallet"][:20],
                market=cluster["market_title"][:50],
                cluster_total=cluster["total_usd"],
                trades_count=len(cluster["trades"]),
                discount=discount_pct,
                side=side,
                trade_price=whale_entry_price,
                midpoint=current_price,
                first_trade_outcome_index=cluster["trades"][0].get('outcomeIndex') if cluster["trades"] else None,
                first_trade_outcome=cluster["trades"][0].get('outcome') if cluster["trades"] else None,
                token_id=token_id_used)  # Log the token_id we actually used
    
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
        # Filter out insane outliers (discounts should be fractions between -1.0 and 1.0)
        if 'discount_pct' in df.columns:
            valid_discounts = df['discount_pct'].dropna()
            valid_discounts = valid_discounts[(valid_discounts >= -1.0) & (valid_discounts <= 1.0)]
            avg_discount = valid_discounts.mean() if len(valid_discounts) > 0 else 0.0
        else:
            avg_discount = 0.0
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
        logger.error(
            "audit_failed",
            extra={
                "event": "audit_failed",
                "error": str(e),
            }
        )
        import traceback
        logger.error(
            "audit_traceback",
            extra={
                "event": "audit_traceback",
                "traceback": traceback.format_exc(),
            }
        )


# Telegram functions removed - paper trading mode (CSV + console logging only)

# Global SignalStats instance for periodic Telegram notifications
stats = SignalStats(notify_every_signals=10, notify_every_seconds=15*60)

# Global SignalStore instance for SQLite persistence
# Ensure logs directory exists before initializing
log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
os.makedirs(log_dir, exist_ok=True)
signal_store = SignalStore()

async def main_loop():
    """Main polling loop - polls top markets by volume (gamma-api → conditionId bridge)."""
    # Declare global counters at function start (required for all scopes in this function)
    global rejected_below_cluster_min, rejected_low_score, rejected_low_discount
    global rejected_score_missing, rejected_score_unavailable, rejected_discount_missing
    global rejected_depth, rejected_conflicting, rejected_daily_limit, rejected_other
    global rejected_other_reasons, signals_generated, trades_considered
    
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
    
    logger.info("engine_started", scan_interval_seconds=SCAN_INTERVAL_SECONDS, mode="multi_event", heartbeat_interval_seconds=HEARTBEAT_INTERVAL_SECONDS)
    
    # Clear any legacy rollups from previous runs (prevents old-format rollups from being sent)
    _whale_rollup.clear()
    logger.info("rollups_cleared_on_startup")
    
    # Log config snapshot to confirm MIN_LOW_DISCOUNT is loaded correctly
    logger.info("config_snapshot",
               MIN_LOW_DISCOUNT=MIN_LOW_DISCOUNT,
               MIN_LOW_DISCOUNT_PCT=MIN_LOW_DISCOUNT * 100.0)
    
    # Track last heartbeat time
    last_heartbeat = time()
    
    # Track last dashboard time
    last_dashboard = time()
    
    async with aiohttp.ClientSession() as session:
        while True:
            cycle_started = time()
            try:
                # Reset counters at start of each cycle (globals already declared at function start)
                rejected_below_cluster_min = 0
                rejected_low_score = 0
                rejected_low_discount = 0
                rejected_score_missing = 0
                rejected_score_unavailable = 0
                rejected_discount_missing = 0
                rejected_depth = 0
                rejected_conflicting = 0
                rejected_daily_limit = 0
                rejected_other = 0
                rejected_other_reasons = {}  # Reset reason tracking
                signals_generated = 0
                trades_considered = 0
                
                # 1. Fetch top markets by volume (gamma-api → conditionId bridge)
                # Fetch many markets to increase chance of finding short-term ones
                # Use reasonable page size (200) and fetch multiple pages if needed
                # Note: "closingSoon" order causes 422 error, so we use "volume" (default)
                markets = await fetch_top_markets(session, limit=200, offset=0, order="volume", pages=2 if PRODUCTION_MODE else 3)
                
                if not markets:
                    logger.warning("no_markets_found")
                    # Still sleep for full scan interval even if no markets found
                    elapsed = time() - cycle_started
                    sleep_for = max(0, SCAN_INTERVAL_SECONDS - elapsed)
                    await asyncio.sleep(sleep_for)
                    continue
                
                logger.info("fetched_markets", count=len(markets))
                
                # Filter markets by expiry time (same-day / 1-2 day markets only)
                # Try expiry from market object first (best-effort parsing)
                filtered_markets = []
                for m in markets:
                    # Try to get expiry directly from market object (many endpoints include endDate/closeTime)
                    dte = _days_to_expiry(m)
                    
                    if dte is None:
                        # Expiry missing from market object - log and check STRICT_SHORT_TERM
                        logger.info("market_expiry_unknown",
                                    market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                    condition_id=m.get("conditionId", "unknown")[:20],
                                    strict_short_term=STRICT_SHORT_TERM)
                        if STRICT_SHORT_TERM:
                            # Reject markets with unknown expiry in strict mode
                            logger.debug("market_rejected_expiry",
                                        market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                        condition_id=m.get("conditionId", "unknown")[:20],
                                        reason="expiry_unknown")
                            continue
                        # Non-strict mode: keep market for now, will try metadata fetch later
                        filtered_markets.append(m)
                        continue
                    
                    # Expiry found - apply window filter
                    if dte > MAX_DAYS_TO_EXPIRY:
                        # Too long - skip this market
                        logger.debug("market_rejected_expiry",
                                    market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                    condition_id=m.get("conditionId", "unknown")[:20],
                                    days_to_expiry=dte,
                                    max_days=MAX_DAYS_TO_EXPIRY,
                                    reason="too_long")
                        continue
                    if dte * 24.0 < MIN_HOURS_TO_EXPIRY:
                        # Too close / already ending - skip this market
                        logger.debug("market_rejected_expiry",
                                    market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                    condition_id=m.get("conditionId", "unknown")[:20],
                                    days_to_expiry=dte,
                                    min_hours=MIN_HOURS_TO_EXPIRY,
                                    reason="too_close")
                        continue
                    # Market passes expiry filter
                    filtered_markets.append(m)
                
                logger.info("markets_after_expiry_filter",
                           fetched=len(markets),
                           filtered=len(filtered_markets),
                           max_days=MAX_DAYS_TO_EXPIRY,
                           min_hours=MIN_HOURS_TO_EXPIRY,
                           strict_short_term=STRICT_SHORT_TERM)
                
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
                        
                        # Extract category from market object (once, before processing trades)
                        market_title = (m.get("title") or m.get("question") or m.get("name") or "").strip()
                        market_slug = (m.get("slug") or "").strip()
                        market_category = (m.get("category") or m.get("marketCategory") or "").strip().lower()
                        
                        # Nested event / events fallback
                        ev = m.get("event") if isinstance(m.get("event"), dict) else {}
                        if not market_category:
                            market_category = str(ev.get("category") or "").strip().lower()
                        
                        evs = m.get("events") or []
                        if not market_category and evs and isinstance(evs, list) and len(evs) > 0:
                            ev0 = evs[0] if isinstance(evs[0], dict) else {}
                            market_category = str(ev0.get("category") or "").strip().lower()
                        
                        if not market_category:
                            market_category = "unknown"
                        
                        # Infer category from title/slug if API didn't provide one
                        category_inferred = False
                        if market_category == "unknown":
                            inferred = infer_category_from_title_slug(market_title, market_slug)
                            if inferred:
                                market_category = inferred
                                category_inferred = True
                        
                        # Debug log for unknown categories to discover available fields
                        if market_category == "unknown":
                            candidate_keys = ["tags", "groupSlug", "eventSlug", "marketType", "category", "raw_category", "marketCategory"]
                            available_fields = {}
                            for key in candidate_keys:
                                val = m.get(key)
                                if val:
                                    available_fields[key] = str(val)[:50]  # Truncate long values
                            # Also check nested event fields
                            evs = m.get("events") or []
                            if evs and isinstance(evs, list) and len(evs) > 0:
                                ev0 = evs[0] if isinstance(evs[0], dict) else {}
                                for key in candidate_keys:
                                    val = ev0.get(key)
                                    if val:
                                        available_fields[f"event.{key}"] = str(val)[:50]
                            
                            logger.debug("market_category_debug",
                                       category="unknown",
                                       title=market_title[:100] if market_title else "",
                                       slug=market_slug[:50] if market_slug else "",
                                       available_fields=available_fields if available_fields else "none",
                                       market_keys=list(m.keys())[:20])
                        
                        # Check if we already have expiry from market object (best-effort parsing)
                        dte_from_market = _days_to_expiry(m)
                        
                        # Validate condition_id before fetching metadata (real Polymarket conditionIds are longer)
                        if len(event_id) < 20 or not event_id.startswith("0x"):
                            # Bad condition_id - only keep if we already determined expiry from market object
                            if dte_from_market is None:
                                logger.info("bad_condition_id_no_expiry",
                                            market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                            condition_id=event_id[:30],
                                            strict_short_term=STRICT_SHORT_TERM)
                                if STRICT_SHORT_TERM:
                                    logger.debug("market_rejected_expiry",
                                                market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                                condition_id=event_id[:30],
                                                reason="expiry_unknown_bad_condition_id")
                                    continue
                                # Non-strict mode: keep market and continue processing
                            else:
                                # Expiry known from market object - apply window filter
                                if dte_from_market > MAX_DAYS_TO_EXPIRY:
                                    logger.debug("market_rejected_expiry",
                                                market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                                condition_id=event_id[:30],
                                                days_to_expiry=dte_from_market,
                                                max_days=MAX_DAYS_TO_EXPIRY,
                                                reason="too_long")
                                    continue
                                if dte_from_market * 24.0 < MIN_HOURS_TO_EXPIRY:
                                    logger.debug("market_rejected_expiry",
                                                market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                                condition_id=event_id[:30],
                                                days_to_expiry=dte_from_market,
                                                min_hours=MIN_HOURS_TO_EXPIRY,
                                                reason="too_close")
                                    continue
                                # Market passes expiry filter - continue processing trades
                        else:
                            # Fetch full market metadata to get expiry (only if not already determined from market object)
                            if dte_from_market is None:
                                market_meta = await fetch_market_metadata_by_condition(session, event_id)
                                if market_meta:
                                    # Try to get expiry from full metadata
                                    dte_from_meta = _days_to_expiry(market_meta)
                                    if dte_from_meta is not None:
                                        # Apply expiry filter using full metadata (only when expiry is reliably known)
                                        if dte_from_meta > MAX_DAYS_TO_EXPIRY:
                                            logger.debug("market_rejected_expiry_from_metadata",
                                                        market_title=market_meta.get("title", m.get("title", "unknown"))[:50],
                                                        condition_id=event_id[:30],
                                                        days_to_expiry=dte_from_meta,
                                                        max_days=MAX_DAYS_TO_EXPIRY,
                                                        reason="too_long")
                                            continue
                                        if dte_from_meta * 24.0 < MIN_HOURS_TO_EXPIRY:
                                            logger.debug("market_rejected_expiry_from_metadata",
                                                        market_title=market_meta.get("title", m.get("title", "unknown"))[:50],
                                                        condition_id=event_id[:30],
                                                        days_to_expiry=dte_from_meta,
                                                        min_hours=MIN_HOURS_TO_EXPIRY,
                                                        reason="too_close")
                                            continue
                                        # Expiry found and within limits - keep market
                                    else:
                                        # Expiry missing after full fetch - check STRICT_SHORT_TERM
                                        logger.info("market_expiry_unknown",
                                                    market_title=market_meta.get("title", m.get("title", "unknown"))[:50],
                                                    condition_id=event_id[:30],
                                                    strict_short_term=STRICT_SHORT_TERM)
                                        if STRICT_SHORT_TERM:
                                            logger.debug("market_rejected_expiry",
                                                        market_title=market_meta.get("title", m.get("title", "unknown"))[:50],
                                                        condition_id=event_id[:30],
                                                        reason="expiry_unknown")
                                            continue
                                        # Non-strict mode: continue processing
                                else:
                                    # Metadata fetch failed - check STRICT_SHORT_TERM
                                    logger.info("market_expiry_unknown",
                                                condition_id=event_id[:30],
                                                market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                                strict_short_term=STRICT_SHORT_TERM,
                                                note="metadata_fetch_failed")
                                    if STRICT_SHORT_TERM:
                                        logger.debug("market_rejected_expiry",
                                                    condition_id=event_id[:30],
                                                    market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                                    reason="expiry_unknown_metadata_fetch_failed")
                                        continue
                                    # Non-strict mode: continue processing
                            else:
                                # Expiry already determined from market object - apply window filter if needed
                                if dte_from_market > MAX_DAYS_TO_EXPIRY:
                                    logger.debug("market_rejected_expiry",
                                                market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                                condition_id=event_id[:30],
                                                days_to_expiry=dte_from_market,
                                                max_days=MAX_DAYS_TO_EXPIRY,
                                                reason="too_long")
                                    continue
                                if dte_from_market * 24.0 < MIN_HOURS_TO_EXPIRY:
                                    logger.debug("market_rejected_expiry",
                                                market_title=m.get("title", m.get("slug", "unknown"))[:50],
                                                condition_id=event_id[:30],
                                                days_to_expiry=dte_from_market,
                                                min_hours=MIN_HOURS_TO_EXPIRY,
                                                reason="too_close")
                                    continue
                                # Market passes expiry filter - continue processing
                        
                        # Fetch trades for this market (probe API params to find correct scoping)
                        # Extract market_id from market object (trades may identify by market_id, not just condition_id)
                        market_id = m.get("id") or m.get("marketId") or m.get("market_id")
                        
                        # condition_id MUST be full 66-char hex (0x + 64 chars)
                        requested_condition_id = event_id  # This must be the full one logged in scan_summary
                        if not isinstance(requested_condition_id, str) or len(requested_condition_id) < 60:
                            logger.error("bad_requested_condition_id",
                                       condition_id=requested_condition_id,
                                       condition_id_len=len(str(requested_condition_id)),
                                       market_title=m.get("title", "unknown")[:50])
                            continue
                        
                        # Probe API params to find correct scoping (verifies trades match requested condition_id)
                        trades = await fetch_trades_scanned(
                            session,
                            market_id=str(market_id) if market_id is not None else None,
                            condition_id=str(requested_condition_id) if requested_condition_id is not None else None,
                            api_min_size_usd=API_MIN_SIZE_USD,
                            pages=3,
                            limit=100,
                        )
                        
                        # IMPORTANT: Convert to list immediately to prevent iterator consumption
                        # (logging/debugging can consume generators, leaving empty list for processing)
                        trades = list(trades) if trades else []
                        
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
                            
                            trades_considered += 1
                            # Category already extracted from market object above (with inference fallback)
                            # Pass it to process_trade along with inferred flag and market object for expiry check
                            signal = await process_trade(session, trade, market_category=market_category, category_inferred=category_inferred, market_obj=m)
                            total_trades_processed += 1
                            
                            if signal:
                                # Final validation: reject if score or discount is None
                                if signal.get("whale_score") is None:
                                    rejected_score_missing += 1
                                    logger.debug("signal_rejected", reason="rejected_score_missing", wallet=signal.get("wallet", "unknown")[:8])
                                    continue
                                
                                if signal.get("discount_pct") is None:
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
                                    rejected_below_cluster_min += 1
                                    logger.debug("signal_rejected", reason="below_cluster_min", 
                                               trade_count=trade_count,
                                               required=min_trades,
                                               wallet=signal.get("wallet", "unknown")[:8])
                                    continue
                                
                                # Hard de-dupe cooldown: prevent repeated alerts on same market/outcome
                                # Include wallet in dedupe key to allow multiple distinct whales on same market/side
                                event_id_for_dedup = signal.get("condition_id") or signal.get("market_id") or event_id
                                outcome_index_for_dedup = signal.get("outcome_index") or (trade.get("outcomeIndex") if 'trade' in locals() else None)
                                side_for_dedup = signal.get("side", "BUY")
                                wallet_for_dedup = signal.get("wallet", "unknown")[:10] if signal.get("wallet") else "unknown"
                                dedup_key = (event_id_for_dedup, outcome_index_for_dedup, side_for_dedup, wallet_for_dedup)
                                now_ts = time()
                                last_signal_time = _recent_signal_keys.get(dedup_key)
                                
                                if last_signal_time and (now_ts - last_signal_time) < SIGNAL_COOLDOWN_SECONDS:
                                    rejected_other_reasons["signal_deduped"] = rejected_other_reasons.get("signal_deduped", 0) + 1
                                    logger.debug("signal_deduped", 
                                               key=str(dedup_key), 
                                               age_sec=int(now_ts - last_signal_time),
                                               event_id=event_id_for_dedup[:20] if event_id_for_dedup else None)
                                    continue
                                
                                # Record this signal timestamp
                                _recent_signal_keys[dedup_key] = now_ts
                                
                                signals_generated += 1
                                
                                # Compute confidence from whale_score
                                whale_score = signal.get("whale_score")
                                if whale_score is not None:
                                    try:
                                        confidence = int(round(float(whale_score) * 100))
                                    except Exception:
                                        confidence = 0
                                else:
                                    confidence = signal.get("confidence", 0)
                                
                                # Add confidence to signal dict
                                signal["confidence"] = confidence
                                
                                # Log signal to CSV
                                log_signal_to_csv(signal)
                                
                                # Store signal in SQLite database
                                signal_id = signal_store.insert_signal(signal)
                                recent_signals.append(signal)
                                
                                # Paper trading: create paper trade if enabled and all filters pass
                                if PAPER_TRADING and signal_id and should_paper_trade(confidence):
                                    # Apply paper trading filters for fast feedback
                                    skip_reasons = []
                                    
                                    # Filter 1: days_to_expiry must be present and <= PAPER_MAX_DTE_DAYS
                                    days_to_expiry = signal.get("days_to_expiry")
                                    if days_to_expiry is None:
                                        skip_reasons.append("days_to_expiry_missing")
                                    elif days_to_expiry > PAPER_MAX_DTE_DAYS:
                                        skip_reasons.append(f"days_to_expiry_too_long_{days_to_expiry:.1f}d")
                                    
                                    # Filter 2: discount_pct must be present and >= PAPER_MIN_DISCOUNT_PCT
                                    discount_pct = signal.get("discount_pct")
                                    if discount_pct is None:
                                        skip_reasons.append("discount_pct_missing")
                                    elif discount_pct < PAPER_MIN_DISCOUNT_PCT:
                                        skip_reasons.append(f"discount_too_low_{discount_pct:.6f}")
                                    
                                    # Filter 3: trade_value_usd must be >= PAPER_MIN_TRADE_USD
                                    trade_value_usd = signal.get("trade_value_usd")
                                    if trade_value_usd is None:
                                        skip_reasons.append("trade_value_usd_missing")
                                    elif trade_value_usd < PAPER_MIN_TRADE_USD:
                                        skip_reasons.append(f"trade_value_too_low_{trade_value_usd:.2f}")
                                    
                                    # If any filter fails, skip paper trade creation
                                    if skip_reasons:
                                        logger.debug(
                                            "paper_trade_skipped",
                                            signal_id=signal_id,
                                            confidence=confidence,
                                            reasons=skip_reasons,
                                            days_to_expiry=days_to_expiry,
                                            discount_pct=discount_pct,
                                            trade_value_usd=trade_value_usd,
                                            max_dte_days=PAPER_MAX_DTE_DAYS,
                                            min_discount_pct=PAPER_MIN_DISCOUNT_PCT,
                                            min_trade_usd=PAPER_MIN_TRADE_USD,
                                        )
                                    else:
                                        # All filters passed - create paper trade
                                        # Calculate stake from confidence (stake_eur_from_confidence handles threshold)
                                        from src.polymarket.paper_trading import stake_eur_from_confidence
                                        stake_eur = round(stake_eur_from_confidence(confidence), 2)
                                        
                                        # Skip if stake is 0 (confidence too low)
                                        if stake_eur <= 0:
                                            logger.debug(
                                                "paper_trade_skipped",
                                                signal_id=signal_id,
                                                confidence=confidence,
                                                reason="stake_zero_below_threshold",
                                            )
                                        else:
                                            # Check if there's already an open paper trade for this market
                                            condition_id_for_check = signal.get("condition_id") or signal.get("event_id") or event_id
                                            if condition_id_for_check and signal_store.has_open_paper_trade(condition_id_for_check):
                                                logger.debug(
                                                    "paper_trade_skipped",
                                                    signal_id=signal_id,
                                                    condition_id=condition_id_for_check[:20],
                                                    reason="open_trade_exists_for_market",
                                                )
                                            else:
                                                # Create paper trade with confidence-based stake
                                                trade_dict = open_paper_trade(signal, confidence=confidence)
                                                trade_dict["signal_id"] = signal_id
                                                trade_dict["days_to_expiry"] = days_to_expiry
                                                
                                                # Insert paper trade (pass computed stake_eur)
                                                trade_id = signal_store.insert_paper_trade(
                                                    signal_id, signal, stake_eur, FX_EUR_USD
                                                )
                                                
                                                if trade_id:
                                                    # Notify paper trade opened
                                                    from src.polymarket.telegram import send_telegram
                                                    telegram_msg = format_paper_trade_telegram(trade_dict)
                                                    send_telegram(telegram_msg)
                                
                                # Market/outcome dedupe check: prevent duplicate alerts for same market+outcome
                                market_id = signal.get("market_id") or signal.get("condition_id") or event_id
                                outcome_index = signal.get("outcome_index")
                                dedupe_key = (market_id, outcome_index)
                                now_ts = time()
                                
                                # Check if we've alerted on this market/outcome recently
                                if dedupe_key in _market_outcome_alerts:
                                    last_alert = _market_outcome_alerts[dedupe_key]
                                    if now_ts - last_alert < SIGNAL_COOLDOWN_SECONDS:
                                        # Skip - still in cooldown
                                        logger.debug("signal_deduped", 
                                                   market_id=market_id[:20] if market_id else "unknown",
                                                   outcome_index=outcome_index,
                                                   time_since_last=now_ts - last_alert,
                                                   cooldown=SIGNAL_COOLDOWN_SECONDS)
                                        continue
                                
                                # --- HARD DISCOUNT GATE (normalize keys) - BEFORE ROLLUP ---
                                try:
                                    min_low_discount = float(os.getenv("MIN_LOW_DISCOUNT", "0.02"))
                                except Exception:
                                    min_low_discount = 0.02
                                
                                # Your signal objects might use `discount` or `discount_pct` key
                                signal_discount = signal.get("discount_pct", None)
                                if signal_discount is None:
                                    signal_discount = signal.get("discount", None)
                                
                                # If still missing, treat as 0 (reject)
                                try:
                                    signal_discount = float(signal_discount) if signal_discount is not None else 0.0
                                except Exception:
                                    signal_discount = 0.0
                                
                                if signal_discount < min_low_discount:
                                    # Track rejection (rejected_low_discount is already declared as global at top of main_loop)
                                    rejected_low_discount += 1
                                    logger.info("rejected_low_discount",
                                               discount=signal_discount,
                                               min_low_discount=min_low_discount,
                                               market=(signal.get("market") or "")[:80],
                                               wallet=signal.get("wallet"))
                                    continue
                                # --- END GATE ---
                                
                                # Rollup whale signals instead of sending immediately
                                # (Only signals that passed the discount gate above reach here)
                                condition_id_for_rollup = signal.get("condition_id") or signal.get("event_id") or event_id
                                if condition_id_for_rollup:
                                    r = _whale_rollup[condition_id_for_rollup]
                                    r["market"] = signal.get("market", r["market"])
                                    r["outcome_name"] = signal.get("outcome_name", r["outcome_name"])
                                    r["wallets"].add(signal.get("wallet", "unknown"))
                                    r["trades"] += 1
                                    trade_usd = float(signal.get("trade_value_usd") or signal.get("total_usd") or 0.0)
                                    r["total_usd"] += trade_usd
                                    r["max_trade_usd"] = max(r["max_trade_usd"], trade_usd)
                                    # Store dedupe key for this rollup
                                    r["dedupe_key"] = dedupe_key
                                    # Track minimum discount in rollup (for filtering when flushing)
                                    # Ensure signal_discount is a float (already computed above)
                                    d = float(signal_discount) if signal_discount is not None else 0.0
                                    cur = r.get("min_discount")
                                    r["min_discount"] = d if cur is None else min(cur, d)
                                else:
                                    # No condition_id - send immediately (shouldn't happen)
                                    notify_signal(signal)
                                    # Mark as alerted
                                    _market_outcome_alerts[dedupe_key] = now_ts
                                
                                # Periodic stats update (every 10 signals or 15 min)
                                stats.bump(extra_line="signal recorded")
                                
                                # Console log with debug info for discount diagnosis
                                signal_wallet = signal.get('wallet', 'unknown')
                                # Add debug fields to help diagnose negative discount issue
                                logger.info("signal_generated", 
                                           wallet=signal_wallet[:20] if signal_wallet else "unknown",
                                           discount=signal['discount_pct'],
                                           market=signal['market'][:50],
                                           event_id=event_id,
                                           side=signal.get('side', 'unknown'),
                                           trade_price=signal.get('whale_entry_price'),
                                           midpoint=signal.get('current_price'),
                                           cluster_trades_count=signal.get('cluster_trades_count', 1),
                                           outcome_index=trade.get('outcomeIndex') if 'trade' in locals() else None,
                                           outcome_name=trade.get('outcome') if 'trade' in locals() else None,
                                           token_id=signal.get('token_id'))  # Use token_id from signal dict (the one we actually used)
                                
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
                                extra={
                                    "event": "market_processing_error",
                                    "wallet": wallet_val,
                                    "condition_id": condition_val,
                                    "error": str(e),
                                }
                            )
                        except Exception:
                            # last resort: swallow logging failures
                            pass
                        
                        continue
                
                logger.info("processing_complete", 
                           markets=len(markets), 
                           trades_processed=trades_considered)  # Use trades_considered which tracks all trades that passed initial filters
                
                # Log filter breakdown
                # Sort rejected_other_reasons by count (descending) and take top 15
                top_reasons = dict(sorted(rejected_other_reasons.items(), key=lambda x: x[1], reverse=True)[:15]) if rejected_other_reasons else {}
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
                           rejected_other_reasons=top_reasons,
                           signals_generated=signals_generated)
                
                # Track rolling metrics for dashboard (last hour)
                now_ts = time()
                _rolling_metrics["signals"].append((now_ts, signals_generated))
                _rolling_metrics["trades_considered"].append((now_ts, trades_considered))
                _rolling_metrics["timestamps"].append(now_ts)
                
                # Track rejections
                if rejected_low_discount > 0:
                    _rolling_metrics["rejections"]["low_discount"] = _rolling_metrics["rejections"].get("low_discount", 0) + rejected_low_discount
                if rejected_low_score > 0:
                    _rolling_metrics["rejections"]["low_score"] = _rolling_metrics["rejections"].get("low_score", 0) + rejected_low_score
                if rejected_discount_missing > 0:
                    _rolling_metrics["rejections"]["discount_missing"] = _rolling_metrics["rejections"].get("discount_missing", 0) + rejected_discount_missing
                if rejected_below_cluster_min > 0:
                    _rolling_metrics["rejections"]["below_cluster_min"] = _rolling_metrics["rejections"].get("below_cluster_min", 0) + rejected_below_cluster_min
                
                # Clean old metrics (keep only last hour)
                cutoff = now_ts - 3600  # 1 hour ago
                _rolling_metrics["signals"] = [(ts, val) for ts, val in _rolling_metrics["signals"] if ts > cutoff]
                _rolling_metrics["trades_considered"] = [(ts, val) for ts, val in _rolling_metrics["trades_considered"] if ts > cutoff]
                _rolling_metrics["timestamps"] = [ts for ts in _rolling_metrics["timestamps"] if ts > cutoff]
                
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
                
                # Flush whale signal rollups (send aggregated summaries)
                now = time()
                
                # Clean up old dedupe entries (keep only entries within cooldown window)
                cutoff_ts = now - SIGNAL_COOLDOWN_SECONDS
                expired_keys = [k for k, ts in _market_outcome_alerts.items() if ts < cutoff_ts]
                for k in expired_keys:
                    del _market_outcome_alerts[k]
                from src.polymarket.telegram import send_telegram
                
                for cid, r in list(_whale_rollup.items()):
                    last = _last_whale_alert_at.get(cid, 0)
                    if now - last < WHALE_SIGNAL_COOLDOWN_SECONDS:
                        continue
                    
                    if r["trades"] <= 0:
                        continue
                    
                    # --- DISCOUNT GATE FOR ROLLUP (filter low-discount rollups) ---
                    try:
                        min_low_discount = float(os.getenv("MIN_LOW_DISCOUNT", "0.02"))
                    except Exception:
                        min_low_discount = 0.02
                    
                    # Get minimum discount from rollup
                    md = r.get("min_discount")
                    market_text = r.get("market") or "Unknown"
                    
                    # OLD ROLLUP FORMAT (no discount tracking) => DO NOT KEEP IT AROUND
                    if md is None:
                        logger.info("rejected_rollup_missing_discount",
                                   condition_id=cid[:20],
                                   market=market_text[:80])
                        del _whale_rollup[cid]
                        continue
                    
                    # Low discount rollup => reject and delete
                    if md < min_low_discount:
                        logger.info("rejected_rollup_low_discount",
                                   condition_id=cid[:20],
                                   min_discount=md,
                                   min_low_discount=min_low_discount,
                                   market=market_text[:80],
                                   trades=r["trades"])
                        del _whale_rollup[cid]
                        continue
                    # --- END DISCOUNT GATE FOR ROLLUP ---
                    
                    # Check market/outcome dedupe before sending
                    dedupe_key = r.get("dedupe_key")
                    if dedupe_key and dedupe_key in _market_outcome_alerts:
                        last_alert = _market_outcome_alerts[dedupe_key]
                        if now - last_alert < SIGNAL_COOLDOWN_SECONDS:
                            # Skip - still in cooldown for this market/outcome
                            logger.debug("rollup_deduped", 
                                       condition_id=cid[:20],
                                       dedupe_key=dedupe_key,
                                       time_since_last=now - last_alert,
                                       cooldown=SIGNAL_COOLDOWN_SECONDS)
                            continue
                    
                    wallets_n = len(r["wallets"])
                    outcome = r["outcome_name"] or "UNKNOWN"
                    market_text = r["market"] or "Unknown"
                    market_short = (market_text[:80] + "...") if len(market_text) > 80 else market_text
                    
                    # --- HARD GATE: DO NOT SEND ROLLUPS BELOW THRESHOLD ---
                    # Re-check min_discount right before sending (defense in depth)
                    # Use global MIN_LOW_DISCOUNT constant (already loaded from env at startup)
                    md_gate = r.get("min_discount", None)
                    
                    if md_gate is None:
                        logger.info("rejected_rollup_missing_discount",
                                   condition_id=cid[:20],
                                   market=market_text[:80],
                                   outcome=outcome,
                                   min_discount=md_gate,
                                   min_low_discount=MIN_LOW_DISCOUNT)
                        try:
                            del _whale_rollup[cid]
                        except Exception:
                            _whale_rollup.pop(cid, None)
                        continue
                    
                    if md_gate < MIN_LOW_DISCOUNT:
                        logger.info("rejected_rollup_low_discount",
                                   condition_id=cid[:20],
                                   market=market_text[:80],
                                   outcome=outcome,
                                   min_discount=md_gate,
                                   min_low_discount=MIN_LOW_DISCOUNT,
                                   min_discount_pct=md_gate * 100.0,
                                   min_low_discount_pct=MIN_LOW_DISCOUNT * 100.0)
                        try:
                            del _whale_rollup[cid]
                        except Exception:
                            _whale_rollup.pop(cid, None)
                        continue
                    # --- END HARD GATE ---
                    
                    # Format min_discount for display (convert fraction to percentage)
                    min_discount_display = md_gate * 100.0 if md_gate is not None else 0.0
                    
                    # Log right before sending (proves this code path is executing)
                    logger.info("about_to_send_rollup",
                               min_discount=md_gate,
                               min_low_discount=MIN_LOW_DISCOUNT,
                               min_discount_pct=min_discount_display,
                               min_low_discount_pct=MIN_LOW_DISCOUNT * 100.0,
                               pid=os.getpid(),
                               condition_id=cid[:20],
                               market=market_short[:80])
                    
                    msg = (
                        "🐋 Whale activity (rollup)\n"
                        f"Market: {market_short}\n"
                        f"Outcome: {outcome}\n"
                        f"Wallets: {wallets_n}\n"
                        f"Trades: {r['trades']}\n"
                        f"Total USD: ${r['total_usd']:.2f}\n"
                        f"Max single trade: ${r['max_trade_usd']:.2f}\n"
                        f"Min discount: {min_discount_display:.4f}%\n"
                        f"{ENGINE_FINGERPRINT}"
                    )
                    
                    try:
                        send_telegram(msg)
                    except Exception:
                        pass  # Don't crash on Telegram errors
                    
                    # Mark as alerted (both condition_id and dedupe_key)
                    _last_whale_alert_at[cid] = now
                    if dedupe_key:
                        _market_outcome_alerts[dedupe_key] = now
                    
                    del _whale_rollup[cid]
                
                # Calibration mode: log histogram every 10 cycles
                global CALIBRATION_CYCLE_COUNT
                CALIBRATION_CYCLE_COUNT += 1
                if CALIBRATION_CYCLE_COUNT % 10 == 0:
                    log_calibration_histogram()
                
            except Exception as e:
                logger.error(
                    "loop_error",
                    extra={
                        "event": "loop_error",
                        "error": str(e),
                    }
                )
            
            # Send heartbeat if interval has passed (with gate_breakdown status)
            now = time()
            if (now - last_heartbeat) >= HEARTBEAT_INTERVAL_SECONDS:
                # Globals already declared at function start
                try:
                    from src.polymarket.telegram import send_telegram
                    
                    # Build heartbeat message with latest gate_breakdown stats
                    # Get top rejection reason
                    top_reason = "none"
                    top_reason_count = 0
                    if rejected_other_reasons:
                        top_reason, top_reason_count = max(rejected_other_reasons.items(), key=lambda x: x[1])
                    elif rejected_low_discount > 0:
                        top_reason = "low_discount"
                        top_reason_count = rejected_low_discount
                    elif rejected_low_score > 0:
                        top_reason = "low_score"
                        top_reason_count = rejected_low_score
                    elif rejected_discount_missing > 0:
                        top_reason = "discount_missing"
                        top_reason_count = rejected_discount_missing
                    elif rejected_below_cluster_min > 0:
                        top_reason = "below_cluster_min"
                        top_reason_count = rejected_below_cluster_min
                    
                    heartbeat_msg = (
                        f"✅ Alive ({ENGINE_FINGERPRINT})\n"
                        f"Last cycle:\n"
                        f"• Trades processed: {trades_considered}\n"
                        f"• Signals generated: {signals_generated}\n"
                        f"• Top reject: {top_reason} ({top_reason_count})"
                    )
                    
                    # Add rejection breakdown if there were any rejects
                    if trades_considered > 0 and signals_generated == 0:
                        heartbeat_msg += (
                            f"\n\nReject breakdown:\n"
                            f"• Low discount: {rejected_low_discount}\n"
                            f"• Low score: {rejected_low_score}\n"
                            f"• Missing discount: {rejected_discount_missing}\n"
                            f"• Below cluster min: {rejected_below_cluster_min}\n"
                            f"• Depth: {rejected_depth}\n"
                            f"• Other: {rejected_other}"
                        )
                    
                    send_telegram(heartbeat_msg)
                    last_heartbeat = now
                except Exception as e:
                    logger.warning(
                        "heartbeat_failed",
                        extra={
                            "event": "heartbeat_failed",
                            "error": str(e),
                        }
                    )
            
            # Send operator dashboard if interval has passed
            dashboard_now = time()
            if DASHBOARD_INTERVAL_SECONDS > 0 and (dashboard_now - last_dashboard) >= DASHBOARD_INTERVAL_SECONDS:
                try:
                    from src.polymarket.telegram import send_telegram
                    import sqlite3
                    from pathlib import Path
                    
                    # Calculate metrics from last hour
                    hour_ago = dashboard_now - 3600
                    signals_last_hour = sum(val for ts, val in _rolling_metrics["signals"] if ts > hour_ago)
                    trades_last_hour = sum(val for ts, val in _rolling_metrics["trades_considered"] if ts > hour_ago)
                    
                    # Get top rejection reason
                    top_reject_reason = "none"
                    top_reject_count = 0
                    if _rolling_metrics["rejections"]:
                        top_reject_reason, top_reject_count = max(_rolling_metrics["rejections"].items(), key=lambda x: x[1])
                    
                    # Get paper trade stats
                    script_dir = Path(__file__).parent.parent.parent
                    db_path = script_dir / "logs" / "paper_trading.sqlite"
                    paper_open = 0
                    paper_resolved = 0
                    paper_open_delta = 0
                    paper_resolved_delta = 0
                    
                    if db_path.exists():
                        conn = sqlite3.connect(str(db_path))
                        conn.row_factory = sqlite3.Row
                        
                        def one(sql, params=()):
                            cur = conn.execute(sql, params)
                            row = cur.fetchone()
                            return row[0] if row else 0
                        
                        paper_open = one("SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'")
                        paper_resolved = one("SELECT COUNT(*) FROM paper_trades WHERE status='RESOLVED'")
                        
                        # Get delta (new opens/resolves in last hour)
                        hour_ago_iso = datetime.fromtimestamp(hour_ago, tz=timezone.utc).isoformat()
                        paper_open_delta = one(
                            "SELECT COUNT(*) FROM paper_trades WHERE status='OPEN' AND created_at > ?",
                            (hour_ago_iso,)
                        )
                        paper_resolved_delta = one(
                            "SELECT COUNT(*) FROM paper_trades WHERE status='RESOLVED' AND resolved_at > ?",
                            (hour_ago_iso,)
                        )
                        
                        conn.close()
                    
                    # Format dashboard message
                    dashboard_msg = (
                        f"📊 Operator Dashboard ({ENGINE_FINGERPRINT})\n"
                        f"Last hour:\n"
                        f"• Signals: {signals_last_hour}\n"
                        f"• Trades considered: {trades_last_hour}\n"
                        f"• Top reject: {top_reject_reason} ({top_reject_count})\n"
                        f"\nPaper trades:\n"
                        f"• OPEN: {paper_open} (+{paper_open_delta})\n"
                        f"• RESOLVED: {paper_resolved} (+{paper_resolved_delta})"
                    )
                    
                    send_telegram(dashboard_msg)
                    last_dashboard = dashboard_now
                    
                    # Reset rejection counters for next period
                    _rolling_metrics["rejections"] = {}
                except Exception as e:
                    logger.warning(
                        "dashboard_failed",
                        extra={
                            "event": "dashboard_failed",
                            "error": str(e),
                        }
                    )
            
            # Calculate elapsed time and sleep until next cycle
            elapsed = time() - cycle_started
            sleep_for = max(0, SCAN_INTERVAL_SECONDS - elapsed)
            logger.info("cycle_complete", elapsed_s=round(elapsed, 2), sleep_s=round(sleep_for, 2))
            await asyncio.sleep(sleep_for)


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
    
    # Notify engine start with fingerprint and config
    from src.polymarket.telegram import send_telegram
    startup_msg = (
        f"✅ Engine started ({ENGINE_FINGERPRINT}) | "
        f"MIN_LOW_DISCOUNT={MIN_LOW_DISCOUNT} ({MIN_LOW_DISCOUNT*100:.2f}%)"
    )
    send_telegram(startup_msg)
    
    # Log file location
    day = datetime.utcnow().strftime("%Y-%m-%d")
    log_file = Path("logs") / f"engine_{day}.log"
    logger.info("engine_starting", mode="paper_trading", logging="csv_and_console", log_file=str(log_file))
    print(f"\n📝 Console output is being logged to: {log_file}\n")
    
    resolver_task = None
    telegram_poll_task = None
    
    try:
        # Start Telegram command polling in background
        try:
            from src.polymarket.telegram import poll_telegram_commands
            logger.info("telegram_commands_started", interval_seconds=5)
            telegram_poll_task = asyncio.create_task(poll_telegram_commands(interval_seconds=5))
        except Exception as e:
            logger.warning("telegram_commands_failed_to_start", error=str(e))
        
        # Start resolver loop in background if paper trading is enabled
        if PAPER_TRADING:
            logger.info("resolver_started", interval_seconds=RESOLVER_INTERVAL_SECONDS)
            resolver_task = asyncio.create_task(
                run_resolver_loop(signal_store, fetch_outcome, RESOLVER_INTERVAL_SECONDS)
            )
        
        # Run main loop (runs forever until KeyboardInterrupt or exception)
        await main_loop()
        
        # Cancel background tasks (should never reach here if main_loop runs forever)
        if resolver_task:
            resolver_task.cancel()
            try:
                await resolver_task
            except asyncio.CancelledError:
                pass
        
        if telegram_poll_task:
            telegram_poll_task.cancel()
            try:
                await telegram_poll_task
            except asyncio.CancelledError:
                pass
                
    except KeyboardInterrupt:
        logger.info("shutdown_requested", reason="keyboard_interrupt")
        notify_engine_stop()
        await shutdown()
    except Exception as e:
        logger.exception("engine_crashed", error=str(e))
        from src.polymarket.telegram import notify_engine_crash
        try:
            notify_engine_crash(f"{type(e).__name__}: {e}")
        except Exception:
            pass  # Don't crash on Telegram failure
        await shutdown()
        raise


if __name__ == "__main__":
    asyncio.run(main())

