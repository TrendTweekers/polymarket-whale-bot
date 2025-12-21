"""Check current system stats and progress"""
import json
from pathlib import Path
from datetime import datetime
from dynamic_whale_manager import DynamicWhaleManager

print("="*80)
print("📊 SYSTEM STATS & PROGRESS REPORT")
print("="*80)
print()

# 1. Dynamic Whale Stats
print("🐋 DYNAMIC WHALE DISCOVERY")
print("-"*80)
m = DynamicWhaleManager()
stats = m.get_whale_stats()
print(f"Total Whales Discovered: {stats['total_whales']}")
print(f"High Confidence (≥70%): {stats['high_confidence']}")
print(f"Active Whales: {stats['active_whales']}")
print(f"Avg Confidence: {stats['avg_confidence']:.1%}")
print()

# Check if growing
state_file = Path("data/dynamic_whale_state.json")
if state_file.exists():
    with open(state_file) as f:
        file_data = json.load(f)
    file_count = len(file_data.get("whales", {}))
    memory_count = len(m.whales)
    print(f"Whales in Memory: {memory_count}")
    print(f"Whales in File: {file_count}")
    if memory_count == file_count:
        print("✅ Data Persisting (Memory = File)")
    else:
        print(f"⚠️ Mismatch: Memory={memory_count}, File={file_count}")
print()

# Top whales
high_conf = [(addr, data['confidence'], data['trade_count'], data['total_value']) 
             for addr, data in m.whales.items() 
             if data['confidence'] >= 0.7]
high_conf.sort(key=lambda x: x[1], reverse=True)

if high_conf:
    print("🏆 TOP 5 HIGH-CONFIDENCE WHALES")
    print("-"*80)
    for i, (addr, conf, trades, value) in enumerate(high_conf[:5], 1):
        print(f"{i}. {addr[:16]}... | Conf: {conf:.0%} | Trades: {trades:3} | Value: ${value:,.0f}")
    print()

# Recent activity
recent = sorted([(addr, d['last_activity']) for addr, d in m.whales.items()], 
                key=lambda x: x[1], reverse=True)[:5]
if recent:
    print("⏰ RECENT ACTIVITY (Last 5 Whales)")
    print("-"*80)
    for addr, last in recent:
        print(f"  {addr[:16]}... | {last[:19]}")
    print()

# 2. Trade Data Collection
print("📈 TRADE DATA COLLECTION")
print("-"*80)
trade_file = Path("data/realtime_whale_trades.json")
if trade_file.exists():
    with open(trade_file) as f:
        trades = json.load(f)
    print(f"Total Trades Saved: {len(trades):,}")
    
    if trades:
        latest = datetime.fromisoformat(trades[-1]['timestamp'].replace('Z', '+00:00'))
        now = datetime.now(latest.tzinfo)
        age_min = (now - latest).total_seconds() / 60
        print(f"Latest Trade: {latest.strftime('%Y-%m-%d %H:%M:%S')} ({age_min:.1f} min ago)")
        
        whale_trades = sum(1 for t in trades if t.get('is_monitored_whale'))
        large_trades = sum(1 for t in trades if t.get('value', 0) >= 100)
        print(f"Monitored Whale Trades: {whale_trades}")
        print(f"Large Trades (>$100): {large_trades}")
        
        # Check if still collecting
        if age_min < 5:
            print("✅ ACTIVELY COLLECTING DATA (latest trade < 5 min ago)")
        elif age_min < 30:
            print("⚠️ Recent activity (latest trade < 30 min ago)")
        else:
            print(f"⚠️ No recent activity (latest trade {age_min:.0f} min ago)")
    else:
        print("⚠️ File exists but empty")
else:
    print("⚠️ Trade file not found")
print()

# 3. Simulation Data
print("🎯 SIMULATION DATA COLLECTION")
print("-"*80)
sim_dir = Path("data/simulations")
if sim_dir.exists():
    sims = list(sim_dir.glob("*.json"))
    print(f"Simulation Files: {len(sims)}")
    if sims:
        latest = max(sims, key=lambda p: p.stat().st_mtime)
        latest_time = datetime.fromtimestamp(latest.stat().st_mtime)
        age_min = (datetime.now() - latest_time).total_seconds() / 60
        print(f"Latest Simulation: {latest.name}")
        print(f"Created: {latest_time.strftime('%Y-%m-%d %H:%M:%S')} ({age_min:.1f} min ago)")
        if age_min < 60:
            print("✅ Simulations Active")
        else:
            print(f"⚠️ No recent simulations ({age_min:.0f} min ago)")
    else:
        print("⚠️ No simulation files yet")
else:
    print("⚠️ Simulation directory not found")
print()

# 4. Watcher Status
print("🔍 WATCHER STATUS")
print("-"*80)
log_file = Path("C:/Users/User/.cursor/projects/c-Users-User-Documents-polymarket-whale-engine/terminals/856976.txt")
if log_file.exists():
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    # Count recent activity
    recent_trades = sum(1 for line in lines if "LARGE TRADE" in line or "WHALE TRADE" in line)
    new_whales = sum(1 for line in lines if "New whale discovered" in line)
    
    print(f"Total Trade Detections (in log): {recent_trades}")
    print(f"New Whales Discovered (in log): {new_whales}")
    
    # Check last activity
    for line in reversed(lines[-50:]):
        if "LARGE TRADE" in line or "WHALE TRADE" in line:
            print(f"✅ Watcher Active (recent trades detected)")
            break
else:
    print("⚠️ Log file not accessible")

print()
print("="*80)
print("✅ STATS CHECK COMPLETE")
print("="*80)
