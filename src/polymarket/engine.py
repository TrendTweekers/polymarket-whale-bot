"""
Polymarket Whale Signal Engine
Polls trades, scores whales, and sends Telegram alerts for buy signals.
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

# Import our modules
import sys
import os

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(parent_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.polymarket.scraper import fetch_recent_trades, BASE, HEADERS
from src.polymarket.profiler import get_whale_stats
from src.polymarket.score import whale_score, whitelist_whales

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("Warning: python-telegram-bot not installed. Telegram features disabled.")

logger = structlog.get_logger()

# Configuration
POLL_INTERVAL_SECONDS = 30
MIN_WHALE_SCORE = 0.70
MIN_DISCOUNT_PCT = 5.0
MIN_ORDERBOOK_DEPTH_MULTIPLIER = 3.0
CONFLICT_WINDOW_MINUTES = 5
MAX_SIGNALS_PER_DAY = 3
MAX_DAILY_LOSS_USD = 50.0
MAX_BANKROLL_PCT_PER_TRADE = 5.0

# State tracking
whitelist_cache: Dict[str, Dict] = {}  # {wallet: {stats, score, category}}
recent_signals: List[Dict] = []  # Track signals sent today
daily_loss_usd = 0.0
conflicting_whales: Dict[str, datetime] = {}  # {wallet: timestamp} for opposite side trades
telegram_app: Optional[Application] = None
telegram_chat_id: Optional[str] = None


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
        logger.debug("daily_limit_hit", reason=reason)
        return None
    
    wallet = trade.get("proxyWallet") or trade.get("makerAddress", "")
    if not wallet:
        return None
    
    side = trade.get("side", "BUY")
    if side != "BUY":
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
        return None
    
    # Calculate discount
    whale_entry_price = trade.get("price", 0.0)
    current_price = whale_entry_price  # In production, fetch from orderbook
    discount_pct = calculate_discount(whale_entry_price, current_price)
    
    if discount_pct < MIN_DISCOUNT_PCT:
        logger.debug("discount_too_low", discount=discount_pct, wallet=wallet[:20])
        return None
    
    # Check orderbook depth
    size = trade.get("size", 0.0)
    depth_ratio = await get_orderbook_depth(session, trade.get("conditionId", ""), size)
    
    if depth_ratio < MIN_ORDERBOOK_DEPTH_MULTIPLIER:
        logger.debug("insufficient_depth", depth=depth_ratio, wallet=wallet[:20])
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


async def send_telegram_signal(signal: Dict):
    """Send signal to Telegram with approve/reject buttons."""
    if not TELEGRAM_AVAILABLE or not telegram_app or not telegram_chat_id:
        logger.warning("telegram_not_configured")
        return
    
    message = f"""
🐋 **WHALE SIGNAL**

**Market:** {signal['market']}
**Whale:** `{signal['wallet'][:20]}...`
**Score:** {signal['whale_score']:.2%}
**Category:** {signal['category'].upper()}

**Entry Price:** ${signal['whale_entry_price']:.4f}
**Current Price:** ${signal['current_price']:.4f}
**Discount:** {signal['discount_pct']:.2f}%

**Size:** {signal['size']:.2f}
**Value:** ${signal['trade_value_usd']:.2f}
**Depth:** {signal['orderbook_depth_ratio']:.1f}x

[View on Polymarket](https://polymarket.com/event/{signal['slug']})
"""
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{signal['transaction_hash']}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{signal['transaction_hash']}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await telegram_app.bot.send_message(
            chat_id=telegram_chat_id,
            text=message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        logger.info("telegram_signal_sent", signal_id=signal['transaction_hash'][:20])
    except Exception as e:
        logger.error("telegram_send_failed", error=str(e))


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle approve/reject button clicks."""
    query = update.callback_query
    await query.answer()
    
    action, tx_hash = query.data.split("_", 1)
    
    if action == "approve":
        await query.edit_message_text(f"✅ Signal approved: {tx_hash[:20]}...")
        logger.info("signal_approved", tx_hash=tx_hash[:20])
    elif action == "reject":
        await query.edit_message_text(f"❌ Signal rejected: {tx_hash[:20]}...")
        logger.info("signal_rejected", tx_hash=tx_hash[:20])


async def main_loop():
    """Main polling loop."""
    logger.info("engine_started", poll_interval=POLL_INTERVAL_SECONDS)
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # Fetch recent large trades
                trades = await fetch_recent_trades(session, min_size_usd=10000, limit=100)
                
                logger.info("processing_trades", count=len(trades))
                
                # Process each trade
                for trade in trades:
                    signal = await process_trade(session, trade)
                    
                    if signal:
                        # Log signal
                        log_signal_to_csv(signal)
                        recent_signals.append(signal)
                        
                        # Send Telegram alert
                        await send_telegram_signal(signal)
                        
                        logger.info("signal_generated", 
                                   wallet=signal['wallet'][:20],
                                   discount=signal['discount_pct'],
                                   market=signal['market'][:50])
                
                # Clean up old conflicting whales
                cutoff_time = datetime.now() - timedelta(minutes=CONFLICT_WINDOW_MINUTES)
                conflicting_whales.clear()  # Simplified cleanup
                
            except Exception as e:
                logger.error("loop_error", error=str(e))
            
            # Wait before next poll
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def init_telegram(token: str, chat_id: str):
    """Initialize Telegram bot."""
    global telegram_app, telegram_chat_id
    
    if not TELEGRAM_AVAILABLE:
        logger.warning("telegram_not_available")
        return
    
    telegram_chat_id = chat_id
    telegram_app = Application.builder().token(token).build()
    
    # Add callback handler
    telegram_app.add_handler(CallbackQueryHandler(button_callback))
    
    # Start bot
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    
    logger.info("telegram_initialized", chat_id=chat_id)


async def shutdown():
    """Cleanup on shutdown."""
    if telegram_app:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
    logger.info("engine_shutdown")


async def main():
    """Main entry point."""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Initialize Telegram if configured
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if telegram_token and telegram_chat_id:
        await init_telegram(telegram_token, telegram_chat_id)
    else:
        logger.warning("telegram_not_configured", 
                      message="Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
    
    try:
        await main_loop()
    except KeyboardInterrupt:
        logger.info("shutdown_requested")
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())

