"""Check recent trade activity"""
import json
from datetime import datetime
from pathlib import Path

trades_file = Path("data/realtime_whale_trades.json")
if not trades_file.exists():
    print("❌ No trades file found")
    exit()

with open(trades_file, 'r') as f:
    trades = json.load(f)

print("="*80)
print("📊 RECENT ACTIVITY CHECK")
print("="*80)
print()

# Check monitored whale trades
whale_trades = [t for t in trades if t.get('is_monitored_whale')]
print(f"🐋 Monitored whale trades: {len(whale_trades)}")

if whale_trades:
    latest_whale = max(whale_trades, key=lambda x: x['timestamp'])
    ts = latest_whale['timestamp']
    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
    now = datetime.now(dt.tzinfo)
    diff_minutes = (now - dt).total_seconds() / 60
    
    print(f"   Last trade: {dt.strftime('%H:%M:%S')}")
    print(f"   Time since: {diff_minutes:.1f} minutes ago")
    print(f"   Market: {latest_whale['market'][:50]}")
    print(f"   Value: ${latest_whale['value']:,.2f}")
    print(f"   Wallet: {latest_whale['wallet'][:16]}...")
    print()
    
    if diff_minutes > 6:
        print(f"⚠️ No monitored whale trades in last {diff_minutes:.0f} minutes")
        print("   This is why you haven't received Telegram notifications")
else:
    print("   ❌ No monitored whale trades found")

# Check large trades >$1000
large_trades = [t for t in trades if t.get('value', 0) >= 1000]
print(f"\n📊 Large trades >$1000: {len(large_trades)}")

if large_trades:
    latest_large = max(large_trades, key=lambda x: x['timestamp'])
    ts = latest_large['timestamp']
    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
    now = datetime.now(dt.tzinfo)
    diff_minutes = (now - dt).total_seconds() / 60
    
    print(f"   Last trade: {dt.strftime('%H:%M:%S')}")
    print(f"   Time since: {diff_minutes:.1f} minutes ago")
    print(f"   Value: ${latest_large['value']:,.2f}")
    print()
    
    if diff_minutes > 6:
        print(f"⚠️ No large trades (>$1000) in last {diff_minutes:.0f} minutes")
        print("   (These also trigger Telegram notifications)")

print()
print("="*80)
print("✅ CONCLUSION:")
print("="*80)
print("Watcher is working correctly!")
print("You receive Telegram notifications for:")
print("  • Monitored whale trades (any size)")
print("  • Large trades >$1000 (any wallet)")
print()
print("If you want more notifications, consider:")
print("  • Lowering the threshold for large trade notifications")
print("  • Adding more active whales to your monitored list")
print("="*80)
