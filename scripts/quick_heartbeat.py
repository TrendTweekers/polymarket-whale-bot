"""
Quick Heartbeat Monitor - Sends hourly Telegram status updates
"""

import asyncio
import os
import json
import aiohttp
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

# Telegram config
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Data paths
DATA_DIR = ROOT / "data"
STATS_FILE = DATA_DIR / "statistics.json"
TRADES_FILE = DATA_DIR / "trades.json"
WHALE_LIST_FILE = ROOT / "config" / "whale_list.json"


async def send_telegram_message(message: str) -> bool:
    """Send message to Telegram"""
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Telegram credentials not configured!")
        return False
    
    try:
        url = f"{API_URL}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Telegram API error: {response.status} - {error_text[:200]}")
                    return False
    except Exception as e:
        print(f"❌ Error sending message: {e}")
        return False


def load_stats() -> dict:
    """Load statistics from file"""
    try:
        if STATS_FILE.exists():
            with open(STATS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️  Could not load stats: {e}")
    
    # Return default stats
    return {
        'total_trades': 0,
        'active_trades': 0,
        'completed_trades': 0,
        'wins': 0,
        'losses': 0,
        'win_rate': 0.0,
        'total_pnl': 0.0,
        'last_updated': None
    }


def load_trades() -> list:
    """Load trades from file"""
    try:
        if TRADES_FILE.exists():
            with open(TRADES_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return []


def count_whales() -> int:
    """Count whales in watchlist"""
    try:
        if WHALE_LIST_FILE.exists():
            with open(WHALE_LIST_FILE, 'r') as f:
                data = json.load(f)
                return len(data.get('whales', []))
    except Exception:
        pass
    return 0


def check_bot_running() -> bool:
    """Check if bot is running by looking at last update time"""
    stats = load_stats()
    last_updated = stats.get('last_updated')
    
    if not last_updated:
        return False
    
    try:
        # Parse ISO format timestamp
        if isinstance(last_updated, str):
            update_time = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
        else:
            return False
        
        # Consider bot running if updated within last 10 minutes
        time_diff = datetime.now(update_time.tzinfo) - update_time
        return time_diff.total_seconds() < 600  # 10 minutes
    except Exception:
        return False


def format_status_message() -> str:
    """Format the status message"""
    stats = load_stats()
    trades = load_trades()
    whale_count = count_whales()
    is_running = check_bot_running()
    
    # Calculate active trades
    active_trades = [t for t in trades if t.get('status') == 'active']
    
    # Format time
    now = datetime.now()
    time_str = now.strftime("%I:%M %p")
    
    # Status emoji
    status_emoji = "✅" if is_running else "⚠️"
    status_text = "RUNNING" if is_running else "UNKNOWN"
    
    # Win rate
    completed = stats.get('completed_trades', 0)
    wins = stats.get('wins', 0)
    win_rate = (wins / completed * 100) if completed > 0 else 0.0
    
    # P&L
    pnl = stats.get('total_pnl', 0.0)
    pnl_str = f"${pnl:+,.2f}" if pnl != 0 else "$0.00"
    
    message = f"""📊 <b>BOT STATUS</b> - {time_str}
━━━━━━━━━━━━━━━━━━━━━━
🤖 Status: <b>{status_text}</b> {status_emoji}
🐋 Whales Monitored: <b>{whale_count}</b>
📈 Trading Stats:
   • Total Trades: <b>{stats.get('total_trades', 0)}</b>
   • Active: <b>{len(active_trades)}</b>
   • Win Rate: <b>{win_rate:.1f}%</b>
   • P&L: <b>{pnl_str}</b>
⏰ Next check: 1 hour"""
    
    return message


async def heartbeat_loop(interval_hours: int = 1):
    """Main heartbeat loop"""
    interval_seconds = interval_hours * 3600
    
    print("\n" + "="*80)
    print("💓 HEARTBEAT MONITOR STARTED")
    print("="*80)
    print(f"\n✅ Sending status updates every {interval_hours} hour(s)")
    
    if CHAT_ID:
        # Mask chat ID for privacy
        chat_display = CHAT_ID[:10] + "..." if len(CHAT_ID) > 10 else CHAT_ID
        print(f"📱 To Telegram chat: {chat_display}")
    else:
        print("⚠️  No Telegram chat ID configured!")
    
    # Calculate next heartbeat time
    next_time = datetime.now() + timedelta(seconds=interval_seconds)
    print(f"\n⏰ Next heartbeat: {next_time.strftime('%I:%M %p')}")
    print("\nPress Ctrl+C to stop\n")
    
    try:
        while True:
            # Send heartbeat
            message = format_status_message()
            success = await send_telegram_message(message)
            
            if success:
                now = datetime.now()
                next_time = now + timedelta(seconds=interval_seconds)
                print(f"✅ [{now.strftime('%I:%M %p')}] Heartbeat sent! Next: {next_time.strftime('%I:%M %p')}")
            else:
                print(f"❌ [{datetime.now().strftime('%I:%M %p')}] Failed to send heartbeat")
            
            # Wait for next interval
            await asyncio.sleep(interval_seconds)
    
    except KeyboardInterrupt:
        print("\n\n⏸️  Heartbeat monitor stopped by user")
    except Exception as e:
        print(f"\n❌ Error in heartbeat loop: {e}")


def main():
    """Main entry point"""
    # Check Telegram config
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ ERROR: Telegram credentials not found!")
        print("\nPlease set in .env file:")
        print("  TELEGRAM_BOT_TOKEN=your_token")
        print("  TELEGRAM_CHAT_ID=your_chat_id")
        return
    
    # Get interval from user
    print("\n" + "="*80)
    print("💓 QUICK HEARTBEAT MONITOR")
    print("="*80)
    
    try:
        user_input = input("\nHow often do you want status updates?\nEnter hours (or press Enter for 1): ").strip()
        
        if user_input:
            interval_hours = int(user_input)
            if interval_hours < 1:
                print("⚠️  Minimum interval is 1 hour. Using 1 hour.")
                interval_hours = 1
        else:
            interval_hours = 1
        
        # Run heartbeat loop
        asyncio.run(heartbeat_loop(interval_hours))
    
    except ValueError:
        print("❌ Invalid input. Using default 1 hour interval.")
        asyncio.run(heartbeat_loop(1))
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()
