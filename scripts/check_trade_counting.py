"""Check if trades are being counted correctly"""
import json
from datetime import datetime
from pathlib import Path

# Check trade file
trades_file = Path("data/realtime_whale_trades.json")
if trades_file.exists():
    with open(trades_file, 'r') as f:
        trades = json.load(f)
    
    print("="*80)
    print("TRADE COUNTING ANALYSIS")
    print("="*80)
    print()
    
    total = len(trades)
    print(f"Total trades in file: {total:,}")
    
    if trades:
        last_trade = trades[-1]
        last_time = datetime.fromisoformat(last_trade['timestamp'].replace('Z', '+00:00'))
        now = datetime.now(last_time.tzinfo)
        time_diff = now - last_time
        
        print(f"Last trade timestamp: {last_trade['timestamp']}")
        print(f"Time since last trade: {time_diff}")
        print()
        
        # Check last 3 hours
        three_hours_ago = now.replace(hour=now.hour-3) if now.hour >= 3 else now.replace(day=now.day-1, hour=now.hour+21)
        recent_trades = [t for t in trades if datetime.fromisoformat(t['timestamp'].replace('Z', '+00:00')) > three_hours_ago.replace(tzinfo=last_time.tzinfo)]
        
        print(f"Trades in last 3 hours: {len(recent_trades):,}")
        print()
        
        # Check hourly breakdown
        print("Hourly breakdown (last 3 hours):")
        for hour_offset in range(3):
            hour_start = now.replace(hour=now.hour-hour_offset-1, minute=0, second=0, microsecond=0)
            hour_end = now.replace(hour=now.hour-hour_offset, minute=0, second=0, microsecond=0)
            hour_trades = [t for t in trades 
                          if hour_start <= datetime.fromisoformat(t['timestamp'].replace('Z', '+00:00')) < hour_end]
            print(f"  Hour {hour_offset+1} ago: {len(hour_trades):,} trades")
        
        print()
        print("="*80)
        print("CONCLUSION:")
        print("="*80)
        
        if len(recent_trades) > 0:
            print("✅ TRADES ARE BEING DETECTED AND SAVED")
            print(f"   {len(recent_trades):,} trades in last 3 hours")
            print()
            print("⚠️ ISSUE: Counter showing 0 in hourly summary")
            print("   Possible causes:")
            print("   1. Counter reset happening at wrong time")
            print("   2. Counter not incrementing properly")
            print("   3. Watcher restarted (counters reset)")
        else:
            print("❌ NO TRADES IN LAST 3 HOURS")
            print("   This explains why summary shows 0")
    else:
        print("No trades found in file")
else:
    print("Trade file not found")
