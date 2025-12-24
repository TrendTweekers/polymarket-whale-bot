#!/usr/bin/env python3
"""Quick script to check trade counts and find sports trades."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.storage import SignalStore
import sqlite3

s = SignalStore()

# Get total counts
conn = s._get_connection()
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM paper_trades WHERE status = "OPEN"')
open_count = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(*) FROM paper_trades WHERE status = "RESOLVED"')
resolved_count = cursor.fetchone()[0]
conn.close()

print(f"Total OPEN trades: {open_count}")
print(f"Total RESOLVED trades: {resolved_count}")

# Get all open trades
all_trades = s.get_open_paper_trades(limit=1000)
print(f"\nTrades retrieved (limit 1000): {len(all_trades)}")

# Find sports/NFL trades
sports_keywords = ['nfl', 'raiders', 'texans', 'basketball', 'nba', 'ncaa', 'football', 'game']
sports_trades = []
for t in all_trades:
    market = t.get('market', '').lower()
    if any(kw in market for kw in sports_keywords):
        sports_trades.append(t)

print(f"\nSports/NFL trades found: {len(sports_trades)}")
for t in sports_trades[:10]:
    print(f"  Trade {t['id']}: {t.get('market', '')[:70]}")
    print(f"    Condition ID: {t.get('event_id') or t.get('condition_id', '')[:42]}...")
    print(f"    Outcome Index: {t.get('outcome_index')}")

