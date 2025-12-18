"""Comprehensive Whale Data Summary - Run when checking back"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

print("\n" + "="*80)
print("🐋 WHALE DATA SUMMARY REPORT")
print("="*80)
print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Load monitored whales
config_file = Path("config/whale_list.json")
if not config_file.exists():
    print("❌ No whale config found")
    exit(1)

with open(config_file, 'r') as f:
    config = json.load(f)

monitored_whales = {w.get('address', '').lower() for w in config.get('whales', [])}
whale_names = {w.get('address', '').lower(): w.get('name', 'Unknown') for w in config.get('whales', [])}

print(f"📊 Monitoring: {len(monitored_whales)} whale addresses")
print()

# Load trades
trades_file = Path("data/realtime_whale_trades.json")
if not trades_file.exists():
    print("❌ No trades data file found")
    print("   Watcher may not have detected any trades yet")
    exit(1)

with open(trades_file, 'r') as f:
    trades = json.load(f)

if not trades:
    print("⚠️ Trades file exists but is empty")
    print("   Watcher is running but no trades detected yet")
    exit(0)

print(f"📈 Total trades in database: {len(trades)}")
print()

# Filter whale trades
whale_trades = [t for t in trades if t.get('wallet', '').lower() in monitored_whales]
large_trades = [t for t in trades if t.get('value', 0) >= 100 and t.get('wallet', '').lower() not in monitored_whales]

print("="*80)
print("🐋 WHALE ACTIVITY")
print("="*80)
print()

if whale_trades:
    print(f"✅ Found {len(whale_trades)} trades from your monitored whales!")
    print()
    
    # Group by whale
    whale_activity = defaultdict(lambda: {'trades': [], 'total_value': 0.0, 'markets': set(), 'first_trade': None, 'last_trade': None})
    
    for trade in whale_trades:
        wallet = trade.get('wallet', '').lower()
        whale_activity[wallet]['trades'].append(trade)
        whale_activity[wallet]['total_value'] += trade.get('value', 0)
        whale_activity[wallet]['markets'].add(trade.get('market', 'Unknown'))
        
        trade_time = trade.get('timestamp', '')
        if not whale_activity[wallet]['first_trade'] or trade_time < whale_activity[wallet]['first_trade']:
            whale_activity[wallet]['first_trade'] = trade_time
        if not whale_activity[wallet]['last_trade'] or trade_time > whale_activity[wallet]['last_trade']:
            whale_activity[wallet]['last_trade'] = trade_time
    
    # Sort by total value
    sorted_whales = sorted(whale_activity.items(), key=lambda x: x[1]['total_value'], reverse=True)
    
    for wallet, data in sorted_whales:
        name = whale_names.get(wallet, 'Unknown')
        print(f"🐋 {name}")
        print(f"   Address: {wallet}")
        print(f"   Total Trades: {len(data['trades'])}")
        print(f"   Total Value: ${data['total_value']:,.2f}")
        print(f"   Markets Traded: {len(data['markets'])}")
        if data['first_trade']:
            print(f"   First Trade: {data['first_trade'][:19]}")
            print(f"   Last Trade: {data['last_trade'][:19]}")
        print()
        
        # Show top 5 trades
        top_trades = sorted(data['trades'], key=lambda x: x.get('value', 0), reverse=True)[:5]
        print("   Top Trades:")
        for trade in top_trades:
            value = trade.get('value', 0)
            market = trade.get('market', 'Unknown')[:50]
            time = trade.get('timestamp', '')[:19]
            print(f"      ${value:,.2f} | {market} | {time}")
        print()
    
    print("="*80)
    print("📊 WHALE PERFORMANCE SUMMARY")
    print("="*80)
    print()
    print(f"Total Whale Trades: {len(whale_trades)}")
    print(f"Total Whale Value: ${sum(t.get('value', 0) for t in whale_trades):,.2f}")
    print(f"Average Trade Size: ${sum(t.get('value', 0) for t in whale_trades) / len(whale_trades):,.2f}")
    print(f"Active Whales: {len(sorted_whales)}")
    print()
    
else:
    print("⏰ No trades from your monitored whales detected")
    print()
    print("This could mean:")
    print("  • Your whales haven't traded during this period")
    print("  • They may be waiting for opportunities")
    print("  • Markets may be quiet")
    print()

print("="*80)
print("📈 OVERALL MARKET ACTIVITY")
print("="*80)
print()

# Time range
if trades:
    times = [t.get('timestamp', '') for t in trades if t.get('timestamp')]
    if times:
        print(f"First Trade: {min(times)[:19]}")
        print(f"Last Trade: {max(times)[:19]}")
        print()

print(f"Total Trades Detected: {len(trades)}")
print(f"Whale Trades: {len(whale_trades)}")
print(f"Large Trades (>$100): {len(large_trades)}")
print(f"Total Value Tracked: ${sum(t.get('value', 0) for t in trades):,.2f}")
print()

# Top markets
market_volume = defaultdict(float)
for trade in trades:
    market = trade.get('market', 'Unknown')
    market_volume[market] += trade.get('value', 0)

if market_volume:
    print("="*80)
    print("🏆 TOP MARKETS (by volume)")
    print("="*80)
    print()
    for market, volume in sorted(market_volume.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  ${volume:,.2f} | {market[:70]}")
    print()

# Save summary to file
summary_file = Path("data/whale_data_summary.txt")
with open(summary_file, 'w', encoding='utf-8') as f:
    f.write(f"Whale Data Summary - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("="*80 + "\n\n")
    f.write(f"Total Trades: {len(trades)}\n")
    f.write(f"Whale Trades: {len(whale_trades)}\n")
    f.write(f"Active Whales: {len(sorted_whales) if whale_trades else 0}\n")
    f.write(f"Total Whale Value: ${sum(t.get('value', 0) for t in whale_trades):,.2f}\n")

print("="*80)
print("✅ SUMMARY SAVED")
print("="*80)
print(f"📁 Full summary: {summary_file}")
print(f"📁 Raw data: {trades_file}")
print()
