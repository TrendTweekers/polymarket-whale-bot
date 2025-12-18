"""Check if monitored whales have traded"""
import json
from pathlib import Path
from collections import defaultdict

# Load monitored whales
config_file = Path("config/whale_list.json")
with open(config_file, 'r') as f:
    config = json.load(f)

monitored_whales = {w.get('address', '').lower() for w in config.get('whales', [])}
whale_names = {w.get('address', '').lower(): w.get('name', 'Unknown') for w in config.get('whales', [])}

# Load trades
trades_file = Path("data/realtime_whale_trades.json")
if not trades_file.exists():
    print("No trades file yet")
    exit(0)

with open(trades_file, 'r') as f:
    trades = json.load(f)

# Check for whale trades
whale_trades = [t for t in trades if t.get('wallet', '').lower() in monitored_whales]

# Group by whale
whale_activity = defaultdict(lambda: {'trades': [], 'total_value': 0.0, 'markets': set()})
for trade in whale_trades:
    wallet = trade['wallet'].lower()
    whale_activity[wallet]['trades'].append(trade)
    whale_activity[wallet]['total_value'] += trade['value_usd']
    whale_activity[wallet]['markets'].add(trade['market_slug'])

print("="*80)
print("WHALE ACTIVITY REPORT")
print("="*80)
print()

if whale_trades:
    print(f"Found {len(whale_trades)} trades from your monitored whales!")
    print()
    
    for wallet, data in sorted(whale_activity.items(), key=lambda x: x[1]['total_value'], reverse=True):
        name = whale_names.get(wallet, 'Unknown')
        print(f"WHALE: {name}")
        print(f"   Address: {wallet}")
        print(f"   Trades: {len(data['trades'])}")
        print(f"   Total Value: ${data['total_value']:,.2f}")
        print(f"   Markets: {len(data['markets'])}")
        print()
        
        # Show recent trades
        recent = sorted(data['trades'], key=lambda x: x['detected_at'], reverse=True)[:5]
        for trade in recent:
            time = trade['detected_at'][:19]
            value = trade['value_usd']
            market = trade['market_slug'][:50]
            print(f"      [{time}] ${value:,.2f} | {market}")
        print()
else:
    print("No trades from your monitored whales yet")
    print()
    print("This means:")
    print("  - Your whales haven't traded in the monitoring period")
    print("  - They may be waiting for opportunities")
    print("  - The watcher is working - it's detected other trades")
    print()

# Overall stats
print("="*80)
print("OVERALL STATS")
print("="*80)
print()
print(f"Total trades detected: {len(trades)}")
print(f"Whale trades: {len(whale_trades)}")
print(f"Large trades (>$100): {len([t for t in trades if t['value_usd'] >= 100])}")
print(f"Total value tracked: ${sum(t['value_usd'] for t in trades):,.2f}")
print()

# Time range
if trades:
    times = [t['detected_at'] for t in trades]
    print(f"First trade: {min(times)[:19]}")
    print(f"Last trade: {max(times)[:19]}")
    print()
