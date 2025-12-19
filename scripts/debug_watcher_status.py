"""Debug watcher status - check if it's processing trades"""
import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("="*80)
print("🔍 WATCHER DEBUG STATUS")
print("="*80)
print()

# Check trade data file
try:
    with open('data/realtime_whale_trades.json', 'r') as f:
        trades = json.load(f)
    
    if not trades:
        print("❌ No trades in data file")
    else:
        print(f"✅ Found {len(trades):,} total trades in file")
        
        # Get latest trade
        latest_trade = max(trades, key=lambda x: x.get('timestamp', ''))
        latest_time = latest_trade.get('timestamp', '')
        
        print(f"\n📊 LATEST TRADE:")
        print(f"  Timestamp: {latest_time}")
        print(f"  Wallet: {latest_trade.get('wallet', 'N/A')[:16]}...")
        print(f"  Market: {latest_trade.get('market', 'N/A')[:60]}")
        print(f"  Value: ${latest_trade.get('value', 0):,.2f}")
        print(f"  Is monitored whale: {latest_trade.get('is_monitored_whale', False)}")
        
        # Calculate time since latest trade
        try:
            if 'T' in latest_time:
                latest_dt = datetime.fromisoformat(latest_time.replace('Z', '+00:00'))
                now = datetime.now(latest_dt.tzinfo) if latest_dt.tzinfo else datetime.now()
                minutes_ago = (now - latest_dt.replace(tzinfo=None)).total_seconds() / 60
                
                print(f"\n⏰ TIME ANALYSIS:")
                print(f"  Latest trade: {minutes_ago:.1f} minutes ago")
                
                if minutes_ago < 5:
                    print(f"  ✅ Status: ACTIVE (trades detected recently)")
                elif minutes_ago < 30:
                    print(f"  ⚠️  Status: SLOW (no trades in {minutes_ago:.0f} min)")
                else:
                    print(f"  ❌ Status: INACTIVE (no trades in {minutes_ago:.0f} min)")
                
                # Check trades in last hour
                hour_ago = now.replace(tzinfo=None) - timedelta(hours=1)
                recent_trades = [t for t in trades if 'T' in t.get('timestamp', '')]
                recent_count = 0
                for t in recent_trades:
                    try:
                        t_dt = datetime.fromisoformat(t['timestamp'].replace('Z', '+00:00'))
                        if t_dt.replace(tzinfo=None) > hour_ago:
                            recent_count += 1
                    except:
                        pass
                
                print(f"\n📈 LAST HOUR:")
                print(f"  Trades detected: {recent_count}")
                if recent_count == 0:
                    print(f"  ⚠️  WARNING: No trades in last hour!")
                    print(f"     Possible issues:")
                    print(f"     • WebSocket disconnected")
                    print(f"     • Markets quiet")
                    print(f"     • Watcher stopped processing")
                
        except Exception as e:
            print(f"\n⚠️ Could not parse timestamp: {e}")
        
        # Check for monitored whale trades
        monitored = [t for t in trades if t.get('is_monitored_whale')]
        print(f"\n🐋 MONITORED WHALE TRADES:")
        print(f"  Total: {len(monitored)}")
        if monitored:
            latest_monitored = max(monitored, key=lambda x: x.get('timestamp', ''))
            print(f"  Latest: {latest_monitored.get('timestamp', '')[:19]}")
            print(f"  Wallet: {latest_monitored.get('wallet', '')[:16]}...")
            print(f"  Value: ${latest_monitored.get('value', 0):,.2f}")
        
except FileNotFoundError:
    print("❌ Trade data file not found: data/realtime_whale_trades.json")
except Exception as e:
    print(f"❌ Error reading trade data: {e}")
    import traceback
    traceback.print_exc()

print()
print("="*80)
print("💡 NEXT STEPS:")
print("="*80)
print("1. Check if watcher process is running")
print("2. Check watcher terminal output for errors")
print("3. Check WebSocket connection status")
print("4. Verify markets are active")
print("="*80)
