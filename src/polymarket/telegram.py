"""
Telegram alert module for Polymarket Whale Signal Engine.
Sends signals via Telegram with approve/reject buttons for manual mode.
"""

import os
import asyncio
import structlog
from typing import Dict, Optional

logger = structlog.get_logger()

# Telegram configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Check if Telegram is configured
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


async def send_alert(signal_data: Dict) -> bool:
    """
    Send signal alert to Telegram with approve/reject buttons.
    
    Args:
        signal_data: Dictionary containing signal information
        
    Returns:
        True if sent successfully, False otherwise
    """
    if not TELEGRAM_ENABLED:
        logger.debug("telegram_disabled", reason="missing_token_or_chat_id")
        return False
    
    try:
        from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
        
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
        # Extract signal data
        wallet = signal_data.get("wallet", "Unknown")[:20]
        market = signal_data.get("market", "Unknown")[:50]
        score = signal_data.get("whale_score", 0.0)
        cluster_total = signal_data.get("trade_value_usd", 0.0)
        discount_pct = signal_data.get("discount_pct", 0.0)
        cluster_trades = signal_data.get("cluster_trades_count", 1)
        
        # Format message (exact format as specified)
        message = (
            f"Signal: Wallet {wallet}, Market {market}, Score {score:.2f}, "
            f"Cluster ${cluster_total:,.2f}, Discount {discount_pct:.2f}%"
        )
        
        # Create approve/reject buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{signal_data.get('timestamp', '')}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{signal_data.get('timestamp', '')}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send message
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        logger.info("telegram_alert_sent",
                   wallet=wallet,
                   market=market[:30],
                   chat_id=TELEGRAM_CHAT_ID)
        
        return True
        
    except ImportError:
        logger.error("telegram_import_failed", error="python-telegram-bot not installed")
        return False
    except Exception as e:
        logger.error("telegram_send_failed", error=str(e))
        return False


async def send_text_message(text: str) -> bool:
    """
    Send a simple text message to Telegram (for status updates, errors, etc.).
    
    Args:
        text: Message text to send
        
    Returns:
        True if sent successfully, False otherwise
    """
    if not TELEGRAM_ENABLED:
        return False
    
    try:
        from telegram import Bot
        
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
        return True
        
    except Exception as e:
        logger.error("telegram_text_send_failed", error=str(e))
        return False


def is_telegram_enabled() -> bool:
    """Check if Telegram is configured and enabled."""
    return TELEGRAM_ENABLED

