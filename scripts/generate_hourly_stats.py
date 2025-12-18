"""Generate hourly stats report"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

trades_file = Path("data/realtime_whale_trades.json")
config_file = Path("config/whale_list.json")

if not trades_file.exists():
    print("No trades data yet")
    exit(0)

# Load data
with open(trades_file, 'r') as f:
    trades = json.load(f)

with open(config_file, 'r') as f:
    config = json.load(f)

monitored_whales = {w.get('address', '').lower() for w in config.get('whales', [])}
whale_names = {w.get('address', '').lower(): w.get('name', 'Unknown') for w in config.get('whales', [])}

# Filter last hour
now = datetime.now()
one_hour_ago = now - timedelta(hours=1)

recent_trades = []
for trade in trades:
    try:
        trade_time = datetime.fromisoformat(trade['detected_at'].replace('Z', '+00:00'))
        if trade_time.replace(tzinfo=None) >= one_hour_ago:
            recent_trades.append(trade)
    except:
        continue

# Analyze
whale_trades = [t for t in recent_trades if t.get('wallet', '').lower() in monitored_whales]
large_trades = [t for t in recent_trades if t['value_usd'] >= 100 and t.get('wallet', '').lower() not in monitored_whales]

# Group whale activity
whale_activity = defaultdict(lambda: {'count': 0, 'value': 0.0, 'markets': set()})
for trade in whale_trades:
    wallet = trade['wallet'].lower()
    whale_activity[wallet]['count'] += 1
    whale_activity[wallet]['value'] += trade['value_usd']
    whale_activity[wallet]['markets'].add(trade['market_slug'])

# Generate report
report = []
report.append("="*80)
report.append("📊 HOURLY STATS REPORT")
report.append("="*80)
report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
report.append(f"Time Range: Last 1 hour")
report.append("")
report.append("="*80)
report.append("🐋 WHALE ACTIVITY")
report.append("="*80)
report.append("")

if whale_trades:
    report.append(f"✅ {len(whale_trades)} trades from your monitored whales!")
    report.append("")
    
    for wallet, data in sorted(whale_activity.items(), key=lambda x: x[1]['value'], reverse=True):
        name = whale_names.get(wallet, 'Unknown')
        report.append(f"🐋 {name}")
        report.append(f"   Address: {wallet[:12]}...")
        report.append(f"   Trades: {data['count']}")
        report.append(f"   Total Value: ${data['value']:,.2f}")
        report.append(f"   Markets: {len(data['markets'])}")
        report.append("")
else:
    report.append("⏰ No trades from monitored whales in the last hour")
    report.append("")

report.append("="*80)
report.append("📈 OVERALL ACTIVITY")
report.append("="*80)
report.append("")
report.append(f"Total trades (last hour): {len(recent_trades)}")
report.append(f"Whale trades: {len(whale_trades)}")
report.append(f"Large trades (>$100): {len(large_trades)}")
report.append(f"Total value: ${sum(t['value_usd'] for t in recent_trades):,.2f}")
report.append("")

# Top markets
market_volume = defaultdict(float)
for trade in recent_trades:
    market_volume[trade['market_slug']] += trade['value_usd']

if market_volume:
    report.append("="*80)
    report.append("🏆 TOP MARKETS (by volume)")
    report.append("="*80)
    report.append("")
    for market, volume in sorted(market_volume.items(), key=lambda x: x[1], reverse=True)[:10]:
        report.append(f"  ${volume:,.2f} | {market[:60]}")
    report.append("")

# Save report
report_file = Path("data/hourly_stats_report.txt")
with open(report_file, 'w', encoding='utf-8') as f:
    f.write("\n".join(report))

# Print to console
print("\n".join(report))
print()
print(f"📁 Full report saved to: {report_file}")
