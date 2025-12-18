"""Check watcher status and recent activity"""
import json
from datetime import datetime, timedelta
from pathlib import Path

print("="*80)
print("🔍 WATCHER STATUS CHECK")
print("="*80)
print()

# Check if watcher is running
import psutil
watcher_running = False
for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if proc.info['name'] == 'python.exe':
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'realtime_whale_watcher' in cmdline:
                watcher_running = True
                print(f"✅ Watcher is RUNNING (PID: {proc.info['pid']})")
                break
    except:
        pass

if not watcher_running:
    print("❌ Watcher is NOT running!")
    print()

# Check recent trades
trades_file = Path("data/realtime_whale_trades.json")
if trades_file.exists():
    with open(trades_file, 'r') as f:
        trades = json.load(f)
    
    print(f"📊 Total trades detected: {len(trades)}")
    
    # Check monitored whale trades
    whale_trades = [t for t in trades if t.get('is_monitored_whale')]
    print(f"🐋 Monitored whale trades: {len(whale_trades)}")
    
    # Check large trades
    large_trades = [t for t in trades if t.get('value', 0) >= 100]
    print(f"📊 Large trades (>$100): {len(large_trades)}")
    
    if trades:
        # Get latest trade
        latest = max(trades, key=lambda x: x.get('timestamp', ''))
        latest_time_str = latest.get('timestamp', '')
        
        try:
            if isinstance(latest_time_str, str):
                if 'T' in latest_time_str:
                    latest_time = datetime.fromisoformat(latest_time_str.replace('Z', '+00:00'))
                else:
                    latest_time = datetime.fromtimestamp(int(latest_time_str))
            else:
                latest_time = datetime.fromtimestamp(int(latest_time_str))
            
            now = datetime.now()
            if latest_time.tzinfo:
                now = datetime.now(latest_time.tzinfo)
                time_diff = now - latest_time
            else:
                time_diff = datetime.now() - latest_time.replace(tzinfo=None) if latest_time.tzinfo else datetime.now() - latest_time
            
            print()
            print(f"⏰ Latest trade: {latest_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Time since: {time_diff.total_seconds() / 60:.1f} minutes ago")
            print(f"   Market: {latest.get('market', 'Unknown')}")
            print(f"   Value: ${latest.get('value', 0):,.2f}")
            print(f"   Is monitored whale: {'✅ YES' if latest.get('is_monitored_whale') else '❌ NO'}")
            
            if time_diff.total_seconds() > 600:  # 10 minutes
                print()
                print("⚠️ WARNING: No trades detected in last 10 minutes!")
                print("   This could mean:")
                print("   • Markets are quiet")
                print("   • WebSocket connection issue")
                print("   • No large trades happening")
        except Exception as e:
            print(f"⚠️ Error parsing timestamp: {e}")
            print(f"   Raw timestamp: {latest_time_str}")
    
    # Check monitored whales
    print()
    print("="*80)
    print("📋 MONITORED WHALES STATUS")
    print("="*80)
    
    config_file = Path("config/whale_list.json")
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        monitored = config.get('whales', [])
        print(f"Total monitored whales: {len(monitored)}")
        
        # Check which monitored whales have traded recently
        monitored_addresses = {w['address'].lower() for w in monitored}
        recent_whale_trades = [
            t for t in trades 
            if t.get('wallet', '').lower() in monitored_addresses
            and t.get('timestamp')
        ]
        
        if recent_whale_trades:
            print(f"✅ {len(recent_whale_trades)} trades from monitored whales")
            latest_whale = max(recent_whale_trades, key=lambda x: x.get('timestamp', ''))
            print(f"   Latest: {latest_whale.get('wallet', '')[:16]}... at {latest_whale.get('timestamp', '')[:19]}")
        else:
            print("❌ No trades from monitored whales in recorded data")
            print("   This is normal if:")
            print("   • Your whales haven't traded recently")
            print("   • Their trades are below $100 threshold")
            print("   • They're inactive")
    else:
        print("❌ No whale config found!")
else:
    print("❌ No trades file found - watcher may not have detected any trades yet")

print()
print("="*80)
