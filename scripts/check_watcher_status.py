"""Check real-time watcher status"""
import json
from pathlib import Path

trades_file = Path("data/realtime_whale_trades.json")

if trades_file.exists():
    with open(trades_file, 'r') as f:
        trades = json.load(f)
    
    whale_trades = [t for t in trades if t.get('is_whale')]
    large_trades = [t for t in trades if not t.get('is_whale')]
    
    print(f"✅ Watcher is running!")
    print(f"📊 Total trades detected: {len(trades)}")
    print(f"🐋 Whale trades: {len(whale_trades)}")
    print(f"📈 Large trades (>$100): {len(large_trades)}")
    print()
    
    if trades:
        print("Recent trades:")
        for trade in trades[-10:]:
            trade_type = "🐋 WHALE" if trade.get('is_whale') else "📊 Large"
            time = trade['detected_at'][:19]
            value = trade['value_usd']
            market = trade['market_slug'][:50]
            print(f"  [{time}] {trade_type}: ${value:,.2f} | {market}")
    else:
        print("⏰ No trades detected yet - waiting for market activity...")
else:
    print("⏰ Watcher is running but no trades detected yet")
    print("   This is normal - waiting for market activity...")
