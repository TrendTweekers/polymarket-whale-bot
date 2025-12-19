"""Check notification status and why no recent notifications"""
import json
import sys
from pathlib import Path
from datetime import datetime

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
        trades = json.load(f)
except Exception as e:
    print(f"❌ Could not load trade data: {e}")
    trades = []

print("="*80)
print("📊 NOTIFICATION STATUS & ANALYSIS")
print("="*80)
print()

# Whale discovery stats
if stats:
    print("🐋 WHALE DISCOVERY STATS:")
    print(f"  Total Whales: {stats.get('total_whales', 0):,}")
    print(f"  High-Confidence (≥70%): {stats.get('high_confidence', 0):,}")
    print(f"  Active Whales: {stats.get('active_whales', 0):,}")
    print(f"  Average Confidence: {stats.get('avg_confidence', 0):.1%}")
    print()

# Trade analysis
monitored_trades = [t for t in trades if t.get('is_monitored_whale')]
high_conf_trades = [t for t in monitored_trades if t.get('whale_confidence', 0) >= 0.70]

print("📈 TRADE ANALYSIS:")
print(f"  Total trades detected: {len(trades):,}")
print(f"  Monitored whale trades: {len(monitored_trades)}")
print(f"  High-confidence (≥70%) trades: {len(high_conf_trades)}")
print()

# Recent activity
if trades:
    latest_trade = max(trades, key=lambda x: x.get('timestamp', ''))
    latest_time = latest_trade.get('timestamp', '')
    if latest_time:
        try:
            if 'T' in latest_time:
                latest_dt = datetime.fromisoformat(latest_time.replace('Z', '+00:00'))
            else:
                latest_dt = datetime.fromtimestamp(float(latest_time))
            now = datetime.now(latest_dt.tzinfo) if latest_dt.tzinfo else datetime.now()
            minutes_ago = (now - latest_dt.replace(tzinfo=None)).total_seconds() / 60
            
            print("⏰ LATEST ACTIVITY:")
            print(f"  Last trade detected: {latest_time[:19]}")
            print(f"  Time since: {minutes_ago:.1f} minutes ago")
            print(f"  Market: {latest_trade.get('market', 'Unknown')[:60]}")
            print(f"  Value: ${latest_trade.get('value', 0):,.2f}")
            print(f"  Is monitored whale: {'✅ YES' if latest_trade.get('is_monitored_whale') else '❌ NO'}")
            print()
        except Exception as e:
            print(f"  ⚠️ Could not parse timestamp: {e}")
            print()

# Recent monitored trades
if monitored_trades:
    print("🐋 RECENT MONITORED WHALE TRADES:")
    recent_monitored = sorted(monitored_trades, key=lambda x: x.get('timestamp', ''), reverse=True)[:5]
    for i, t in enumerate(recent_monitored, 1):
        timestamp = t.get('timestamp', '')[:19]
        wallet = t.get('wallet', '')[:16]
        value = t.get('value', 0)
        conf = t.get('whale_confidence', 'N/A')
        conf_str = f"{conf:.0%}" if isinstance(conf, (int, float)) else str(conf)
        
        print(f"  {i}. {timestamp} | {wallet}... | ${value:,.2f} | Conf: {conf_str}")
    print()

# High-confidence trades
if high_conf_trades:
    print("⭐ RECENT HIGH-CONFIDENCE TRADES (≥70%):")
    recent_high_conf = sorted(high_conf_trades, key=lambda x: x.get('timestamp', ''), reverse=True)[:5]
    for i, t in enumerate(recent_high_conf, 1):
        timestamp = t.get('timestamp', '')[:19]
        wallet = t.get('wallet', '')[:16]
        value = t.get('value', 0)
        conf = t.get('whale_confidence', 0)
        
        print(f"  {i}. {timestamp} | {wallet}... | ${value:,.2f} | Conf: {conf:.0%}")
    print()
else:
    print("⚠️ NO HIGH-CONFIDENCE TRADES FOUND")
    print("   (These are the ones that trigger Telegram notifications)")
    print()

# Why no notifications?
print("="*80)
print("💡 WHY NO RECENT NOTIFICATIONS?")
print("="*80)
print()
print("Telegram notifications are sent for:")
print("  ✅ High-confidence monitored whales (≥70% confidence)")
print("  ❌ Large trades >$1000 (DISABLED per your request)")
print()
print("Current situation:")
if len(high_conf_trades) == 0:
    print("  ⚠️ No high-confidence trades detected yet")
    print("  → System is working, but no whales meet the ≥70% threshold")
elif len(high_conf_trades) > 0:
    latest_high_conf = max(high_conf_trades, key=lambda x: x.get('timestamp', ''))
    latest_high_conf_time = latest_high_conf.get('timestamp', '')
    if latest_high_conf_time:
        try:
            if 'T' in latest_high_conf_time:
                latest_dt = datetime.fromisoformat(latest_high_conf_time.replace('Z', '+00:00'))
            else:
                latest_dt = datetime.fromtimestamp(float(latest_high_conf_time))
            now = datetime.now(latest_dt.tzinfo) if latest_dt.tzinfo else datetime.now()
            minutes_ago = (now - latest_dt.replace(tzinfo=None)).total_seconds() / 60
            
            print(f"  ✅ Last high-confidence trade: {minutes_ago:.1f} minutes ago")
            print(f"  → You should have received a notification for this")
            if minutes_ago > 30:
                print(f"  ⚠️ No notification in {minutes_ago:.0f} minutes - check Telegram connection")
        except:
            pass

print()
print("="*80)
