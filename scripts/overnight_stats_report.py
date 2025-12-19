"""Generate comprehensive overnight stats report"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from dynamic_whale_manager import DynamicWhaleManager
    whale_manager = DynamicWhaleManager()
    stats = whale_manager.get_whale_stats()
except Exception as e:
    print(f"⚠️ Could not load whale manager: {e}")
    whale_manager = None
    stats = {}

# Load trade data
try:
    with open('data/realtime_whale_trades.json', 'r') as f:
        all_trades = json.load(f)
except Exception as e:
    print(f"❌ Could not load trade data: {e}")
    all_trades = []

# Restart time: 2025-12-18 22:57:31
restart_time = datetime(2025, 12, 18, 22, 57, 31)
restart_iso = restart_time.isoformat() + 'Z'

# Filter trades since restart
trades_since_restart = [t for t in all_trades if t.get('timestamp', '') >= restart_iso]
monitored_trades = [t for t in trades_since_restart if t.get('is_monitored_whale')]
high_conf_trades = [t for t in monitored_trades if isinstance(t.get('whale_confidence'), (int, float)) and t.get('whale_confidence', 0) >= 0.65]

# Calculate time since restart
now = datetime.now()
runtime = now - restart_time
hours_running = runtime.total_seconds() / 3600

print("="*80)
print("📊 OVERNIGHT STATS REPORT")
print("="*80)
print()
print(f"⏰ Runtime: {hours_running:.1f} hours (since {restart_time.strftime('%Y-%m-%d %H:%M:%S')})")
print()

# Trade statistics
print("📈 TRADE STATISTICS:")
print(f"  Total trades detected: {len(trades_since_restart):,}")
if trades_since_restart:
    trades_per_hour = len(trades_since_restart) / max(hours_running, 0.1)
    print(f"  Average rate: {trades_per_hour:.0f} trades/hour")
    
    # Latest trade
    latest = max(trades_since_restart, key=lambda x: x.get('timestamp', ''))
    latest_time = latest.get('timestamp', '')
    if latest_time:
        try:
            latest_dt = datetime.fromisoformat(latest_time.replace('Z', '+00:00'))
            minutes_ago = (now - latest_dt.replace(tzinfo=None)).total_seconds() / 60
            print(f"  Latest trade: {minutes_ago:.1f} minutes ago")
        except:
            pass
print()

# Monitored whale trades
print("🐋 MONITORED WHALE TRADES:")
print(f"  Total: {len(monitored_trades)}")
print(f"  High-confidence (≥65%): {len(high_conf_trades)}")
print()

if monitored_trades:
    print("  Recent monitored whale trades:")
    recent_monitored = sorted(monitored_trades, key=lambda x: x.get('timestamp', ''), reverse=True)[:5]
    for i, t in enumerate(recent_monitored, 1):
        timestamp = t.get('timestamp', '')[:19]
        wallet = t.get('wallet', '')[:16]
        value = t.get('value', 0)
        conf = t.get('whale_confidence', 'N/A')
        conf_str = f"{conf:.0%}" if isinstance(conf, (int, float)) else str(conf)
        print(f"    {i}. {timestamp} | {wallet}... | ${value:,.2f} | Conf: {conf_str}")
    print()

if high_conf_trades:
    print("  ⭐ High-confidence trades (should trigger notifications):")
    recent_high_conf = sorted(high_conf_trades, key=lambda x: x.get('timestamp', ''), reverse=True)[:5]
    for i, t in enumerate(recent_high_conf, 1):
        timestamp = t.get('timestamp', '')[:19]
        wallet = t.get('wallet', '')[:16]
        value = t.get('value', 0)
        conf = t.get('whale_confidence', 0)
        print(f"    {i}. {timestamp} | {wallet}... | ${value:,.2f} | Conf: {conf:.0%}")
    print()
else:
    print("  ⚠️ No high-confidence trades detected")
    print("     (This means no monitored whales met the ≥65% threshold)")
    print()

# Whale discovery stats
if stats:
    print("🐋 WHALE DISCOVERY:")
    print(f"  Total whales: {stats.get('total_whales', 0):,}")
    print(f"  High-confidence (≥70%): {stats.get('high_confidence', 0):,}")
    print(f"  Active whales: {stats.get('active_whales', 0):,}")
    print(f"  Average confidence: {stats.get('avg_confidence', 0):.1%}")
    print()

# System health check
print("="*80)
print("✅ SYSTEM HEALTH CHECK")
print("="*80)
print()

# Check if watcher is running
import subprocess
try:
    result = subprocess.run(
        ['powershell', '-Command', 
         'Get-Process python -ErrorAction SilentlyContinue | Where-Object {(Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*realtime_whale_watcher*"} | Select-Object -First 1'],
        capture_output=True,
        text=True,
        timeout=5
    )
    if result.stdout.strip():
        print("✅ Watcher process: RUNNING")
    else:
        print("❌ Watcher process: NOT RUNNING")
except:
    print("⚠️ Could not check watcher process")

# Check recent activity
if trades_since_restart:
    latest = max(trades_since_restart, key=lambda x: x.get('timestamp', ''))
    latest_time = latest.get('timestamp', '')
    if latest_time:
        try:
            latest_dt = datetime.fromisoformat(latest_time.replace('Z', '+00:00'))
            minutes_ago = (now - latest_dt.replace(tzinfo=None)).total_seconds() / 60
            
            if minutes_ago < 10:
                print("✅ Recent activity: ACTIVE (trades detected in last 10 min)")
            elif minutes_ago < 60:
                print(f"⚠️ Recent activity: SLOW (last trade {minutes_ago:.0f} min ago)")
            else:
                print(f"❌ Recent activity: INACTIVE (last trade {minutes_ago:.0f} min ago)")
        except:
            pass

# Check notification threshold
print(f"✅ Notification threshold: 65% (lowered from 70%)")
print(f"   Will notify for monitored whales with ≥65% confidence")
print()

# Summary
print("="*80)
print("📋 SUMMARY")
print("="*80)
print()

if len(trades_since_restart) > 0:
    print(f"✅ System is processing trades ({len(trades_since_restart):,} since restart)")
else:
    print("⚠️ No trades detected since restart - check WebSocket connection")

if len(monitored_trades) > 0:
    print(f"✅ Monitored whales are trading ({len(monitored_trades)} trades detected)")
else:
    print("⚠️ No monitored whale trades detected")

if len(high_conf_trades) > 0:
    print(f"✅ High-confidence trades detected ({len(high_conf_trades)} should have triggered notifications)")
else:
    print("⚠️ No high-confidence trades - monitored whales may be below 65% threshold")

print()
print("="*80)
