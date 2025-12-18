"""Quick status check"""
import json
from pathlib import Path
from datetime import datetime

trades_file = Path("data/realtime_whale_trades.json")

print("Current Status:")
print(f"  Time: {datetime.now().strftime('%H:%M:%S')}")
print(f"  Trades file exists: {trades_file.exists()}")

if trades_file.exists():
    with open(trades_file, 'r') as f:
        trades = json.load(f)
    print(f"  Total trades: {len(trades)}")
    print(f"  File size: {trades_file.stat().st_size:,} bytes")
else:
    print("  No trades file yet")

print()
print("When you return at 19:00, run:")
print("  python scripts/check_whale_data_summary.py")
