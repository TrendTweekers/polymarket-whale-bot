#!/usr/bin/env python3
"""Check if elite whales are trading"""
import json
from pathlib import Path
from datetime import datetime, timedelta

# Load elite addresses
with open('data/api_validation_results.json', 'r') as f:
    elite_data = json.load(f)

if isinstance(elite_data, list):
    results = elite_data
else:
    results = elite_data.get('results', [])

elite_addrs = {w['address'].lower() for w in results if w.get('passes', False)}
print(f"✅ Elite addresses loaded: {len(elite_addrs)}")
print()

# Load recent trades
with open('data/realtime_whale_trades.json', 'r') as f:
    trades = json.load(f)

# Check last 50 trades
recent_trades = trades[-50:] if len(trades) > 50 else trades
print(f"Recent trades checked: {len(recent_trades)}")

# Find elite whales in recent trades
elite_in_recent = [t for t in recent_trades if t.get('wallet', '').lower() in elite_addrs]
print(f"Elite whale trades in recent: {len(elite_in_recent)}")
print()

if elite_in_recent:
    print("✅ ELITE WHALES FOUND IN RECENT TRADES:")
    for t in elite_in_recent[-5:]:
        print(f"  {t['wallet'][:16]}... at {t['timestamp'][:19]}")
else:
    print("❌ NO elite whales in recent trades")
    print("This explains why no elite simulations yet")
print()

# Check dynamic whale pool
print("=" * 70)
print("DYNAMIC WHALE POOL CHECK")
print("=" * 70)

whale_file = Path('data/dynamic_whale_state.json')
if whale_file.exists():
    with open(whale_file, 'r') as f:
        whales = json.load(f)
    
    # Check for elite whales
    elite_in_pool = {addr: data for addr, data in whales.items() 
                     if addr.lower() in elite_addrs}
    
    print(f"Total whales in pool: {len(whales)}")
    print(f"Elite whales in pool: {len(elite_in_pool)}")
    print()
    
    if elite_in_pool:
        # Find elite whales meeting threshold
        meets_threshold = [(addr, data) for addr, data in elite_in_pool.items() 
                          if data.get('confidence', 0) >= 50]
        
        print(f"Elite whales with confidence ≥50%: {len(meets_threshold)}")
        print()
        
        if meets_threshold:
            print("Top 5 Elite Whales ≥50%:")
            for addr, data in sorted(meets_threshold, 
                                    key=lambda x: x[1].get('confidence', 0), 
                                    reverse=True)[:5]:
                conf = data.get('confidence', 0)
                trades = data.get('trade_count', 0)
                value = data.get('total_value', 0)
                print(f"  {addr[:16]}... - {conf:.0f}% - {trades} trades - ${value:,.0f}")
        else:
            print("❌ NO elite whales meet ≥50% threshold yet")
            print("They're still building confidence...")
            print()
            print("Top 5 Elite Whales (any confidence):")
            for addr, data in sorted(elite_in_pool.items(), 
                                    key=lambda x: x[1].get('confidence', 0), 
                                    reverse=True)[:5]:
                conf = data.get('confidence', 0)
                trades = data.get('trade_count', 0)
                print(f"  {addr[:16]}... - {conf:.0f}% - {trades} trades")
    else:
        print("❌ NO elite whales in dynamic pool yet")
        print("Watcher just restarted - pool is rebuilding")
else:
    print("❌ Dynamic whale state file not found")
