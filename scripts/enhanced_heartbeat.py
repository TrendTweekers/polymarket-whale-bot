"""
Enhanced Heartbeat Monitor - Detects bot process and sends Telegram status updates
Properly detects if bot is running using process monitoring
"""

import asyncio
import os
import json
import aiohttp
import psutil
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

# Bot process identifiers
BOT_SCRIPTS = [
    'engine.py',
    'bot.py',
    'main.py'
]

# Track bot detection to reset uptime when heartbeat restarts
_bot_pid_cache = None
_bot_detection_time = None


def find_bot_process():
    """Find running bot process"""
    current_pid = os.getpid()
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            # Skip self
            if proc.info['pid'] == current_pid:
                continue
            
            cmdline = proc.info.get('cmdline', [])
            if not cmdline:
                continue
            
            # Check if this is a Python process running our bot
            cmdline_str = ' '.join(cmdline).lower()
            
            # Check for bot scripts
            is_bot = any(script in cmdline_str for script in BOT_SCRIPTS)
            is_polymarket = 'polymarket' in cmdline_str.lower()
            
            if is_bot or is_polymarket:
                # Make sure it's actually our bot (check for project path)
                if str(ROOT).lower() in cmdline_str:
                    return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    return None


# Track bot PID to detect restarts
_bot_pid_cache = None
_bot_detection_time = None

def get_bot_uptime(proc):
    """Get bot uptime - tracks from when heartbeat first detected it (resets when heartbeat restarts)"""
    global _bot_pid_cache, _bot_detection_time
    
    if not proc:
        # Reset cache if bot not found
        _bot_pid_cache = None
        _bot_detection_time = None
        return None
    
    try:
        current_pid = proc.pid
        
        # If bot PID changed, it restarted - reset tracking
        if _bot_pid_cache is not None and _bot_pid_cache != current_pid:
            _bot_detection_time = datetime.now().timestamp()
            _bot_pid_cache = current_pid
        
        # If first time detecting this bot (or heartbeat just restarted), start tracking from NOW
        # This ensures uptime resets when heartbeat script restarts
        if _bot_pid_cache is None:
            _bot_detection_time = datetime.now().timestamp()
            _bot_pid_cache = current_pid
        
        # Calculate uptime from when we first detected it (resets on heartbeat restart)
        uptime_seconds = datetime.now().timestamp() - _bot_detection_time
        return uptime_seconds
    except Exception:
        return None


def format_uptime(seconds):
    """Format seconds into human-readable uptime"""
    if seconds is None:
        return "Unknown"
    
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


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


def get_last_activity() -> str:
    """Get last activity timestamp"""
    stats = load_stats()
    last_updated = stats.get('last_updated')
    
    if not last_updated:
        return "Never"
    
    try:
        if isinstance(last_updated, str):
            update_time = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
            now = datetime.now(update_time.tzinfo)
            time_diff = now - update_time
            
            if time_diff.total_seconds() < 60:
                return "Just now"
            elif time_diff.total_seconds() < 3600:
                minutes = int(time_diff.total_seconds() / 60)
                return f"{minutes}m ago"
            elif time_diff.total_seconds() < 86400:
                hours = int(time_diff.total_seconds() / 3600)
                return f"{hours}h ago"
            else:
                days = int(time_diff.total_seconds() / 86400)
                return f"{days}d ago"
    except Exception:
        pass
    
    return "Unknown"


def format_status_message() -> str:
    """Format the status message"""
    stats = load_stats()
    trades = load_trades()
    whale_count = count_whales()
    
    # Check if bot process is running
    bot_proc = find_bot_process()
    is_running = bot_proc is not None
    
    # Get uptime
    uptime_seconds = get_bot_uptime(bot_proc)
    uptime_str = format_uptime(uptime_seconds) if uptime_seconds else "N/A"
    
    # Format time
    now = datetime.now()
    time_str = now.strftime("%I:%M %p")
    
    # Status emoji
    status_emoji = "✅" if is_running else "❌"
    status_text = "RUNNING" if is_running else "STOPPED"
    
    # Win rate
    completed = stats.get('completed_trades', 0)
    wins = stats.get('wins', 0)
    win_rate = (wins / completed * 100) if completed > 0 else 0.0
    
    # P&L
    pnl = stats.get('total_pnl', 0.0)
    pnl_str = f"${pnl:+,.2f}" if pnl != 0 else "$0.00"
    
    # Last activity
    last_activity = get_last_activity()
    
    message = f"""📊 <b>BOT STATUS</b> - {time_str}
━━━━━━━━━━━━━━━━━━━━━━
🤖 Status: <b>{status_text}</b> {status_emoji}
⏱️  Uptime: <b>{uptime_str}</b>
🕐 Last Activity: <b>{last_activity}</b>
🐋 Whales Monitored: <b>{whale_count}</b>
📈 Trading Stats:
   • Total Trades: <b>{stats.get('total_trades', 0)}</b>
   • Active: <b>{len([t for t in trades if t.get('status') == 'active'])}</b>
   • Win Rate: <b>{win_rate:.1f}%</b>
   • P&L: <b>{pnl_str}</b>
⏰ Next check: 1 hour"""
    
    return message


async def heartbeat_loop(interval_hours: int = 1):
    """Main heartbeat loop"""
    interval_seconds = interval_hours * 3600
    
    print("\n" + "="*80)
    print("💓 ENHANCED HEARTBEAT MONITOR STARTED")
    print("="*80)
    print(f"\n✅ Sending status updates every {interval_hours} hour(s)")
    
    if CHAT_ID:
        # Mask chat ID for privacy
        chat_display = CHAT_ID[:10] + "..." if len(CHAT_ID) > 10 else CHAT_ID
        print(f"📱 To Telegram chat: {chat_display}")
    else:
        print("⚠️  No Telegram chat ID configured!")
    
    # Check if bot is running
    bot_proc = find_bot_process()
    if bot_proc:
        uptime = get_bot_uptime(bot_proc)
        print(f"✅ Bot process detected! PID: {bot_proc.pid}, Uptime: {format_uptime(uptime)}")
    else:
        print("⚠️  Bot process not detected - may not be running")
    
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
                
                # Check bot status
                bot_proc = find_bot_process()
                status = "✅ RUNNING" if bot_proc else "❌ STOPPED"
                
                print(f"✅ [{now.strftime('%I:%M %p')}] Heartbeat sent! Bot: {status} | Next: {next_time.strftime('%I:%M %p')}")
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
    
    # Check psutil
    try:
        import psutil
    except ImportError:
        print("❌ ERROR: psutil not installed!")
        print("\nPlease install:")
        print("  pip install psutil --break-system-packages")
        return
    
    # Get interval from user
    print("\n" + "="*80)
    print("💓 ENHANCED HEARTBEAT MONITOR")
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
