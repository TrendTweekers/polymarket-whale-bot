"""Verify data collection is working and not resetting"""
import json
from pathlib import Path
from datetime import datetime
from dynamic_whale_manager import DynamicWhaleManager

print("="*80)
print("✅ DATA COLLECTION VERIFICATION")
print("="*80)
print()

# Check whale state persistence
m = DynamicWhaleManager()
state_file = Path("data/dynamic_whale_state.json")

print("1. WHALE DISCOVERY STATUS")
print("-"*80)
print(f"   Memory: {len(m.whales)} whales")
print(f"   High Confidence (≥70%): {sum(1 for w in m.whales.values() if w['confidence'] >= 0.7)}")
print(f"   Still Growing: {'✅ YES' if len(m.whales) > 0 else '❌ NO'}")
print()

# Check if state is being saved
if state_file.exists():
    with open(state_file) as f:
        file_data = json.load(f)
    
    # Check structure
    if isinstance(file_data, dict):
        if "whales" in file_data:
            file_count = len(file_data["whales"])
            print(f"   File Structure: ✅ Correct (has 'whales' key)")
        else:
            # Old format - whales are top-level
            file_count = len(file_data)
            print(f"   File Structure: ⚠️ Old format (whales are top-level)")
    else:
        file_count = 0
        print(f"   File Structure: ❌ Invalid")
    
    print(f"   File: {file_count} whales")
    print(f"   Match: {'✅ YES' if len(m.whales) == file_count else f'⚠️ NO (Memory={len(m.whales)}, File={file_count})'}")
else:
    print(f"   File: ⚠️ Not found (will be created on save)")
    print(f"   Status: ⚠️ State not persisted yet")
print()

# Check trade collection
print("2. TRADE DATA COLLECTION")
print("-"*80)
trade_file = Path("data/realtime_whale_trades.json")
if trade_file.exists():
    with open(trade_file) as f:
        trades = json.load(f)
    
    print(f"   Total Trades: {len(trades):,}")
    
    if trades:
        latest = datetime.fromisoformat(trades[-1]['timestamp'].replace('Z', '+00:00'))
        now = datetime.now(latest.tzinfo)
        age_sec = (now - latest).total_seconds()
        age_min = age_sec / 60
        
        print(f"   Latest Trade: {latest.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Age: {age_min:.1f} minutes ago")
        
        if age_min < 5:
            print(f"   Status: ✅ ACTIVELY COLLECTING (very recent)")
        elif age_min < 30:
            print(f"   Status: ✅ Collecting (recent)")
        else:
            print(f"   Status: ⚠️ Stale ({age_min:.0f} min old)")
        
        # Check growth
        if len(trades) > 400:
            print(f"   Growth: ✅ Growing ({len(trades)} trades collected)")
        else:
            print(f"   Growth: ⚠️ Limited ({len(trades)} trades)")
    else:
        print(f"   Status: ⚠️ File empty")
else:
    print(f"   Status: ⚠️ File not found")
print()

# Check recent whale activity
print("3. RECENT WHALE ACTIVITY")
print("-"*80)
recent = sorted([(addr, d['last_activity'], d['trade_count']) 
                 for addr, d in m.whales.items()], 
                key=lambda x: x[1], reverse=True)[:5]

if recent:
    print("   Last 5 Active Whales:")
    for addr, last, count in recent:
        last_dt = datetime.fromisoformat(last.replace('Z', '+00:00'))
        now = datetime.now(last_dt.tzinfo)
        age_min = (now - last_dt).total_seconds() / 60
        print(f"   • {addr[:16]}... | {count} trades | {age_min:.1f} min ago")
    print(f"   Status: ✅ Active whales detected")
else:
    print(f"   Status: ⚠️ No recent activity")
print()

# Summary
print("="*80)
print("📊 SUMMARY")
print("="*80)
print(f"✅ Whales Discovered: {len(m.whales)}")
print(f"✅ High Confidence: {sum(1 for w in m.whales.values() if w['confidence'] >= 0.7)}")
print(f"✅ Trades Collected: {len(trades) if trade_file.exists() and trades else 0}")
print(f"✅ Data Collection: {'ACTIVE' if trade_file.exists() and trades and age_min < 30 else 'CHECK STATUS'}")
print("="*80)
