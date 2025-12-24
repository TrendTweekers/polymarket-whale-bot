#!/usr/bin/env python3
"""Inspect condition_ids stored in database."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.storage import SignalStore
import sqlite3

store = SignalStore()
conn = store._get_connection()
cursor = conn.cursor()

# Get NFL/sports trades
cursor.execute("""
    SELECT id, event_id, condition_id, market, opened_at 
    FROM paper_trades 
    WHERE market LIKE '%Raiders%' OR market LIKE '%Texans%' OR market LIKE '%NFL%'
    LIMIT 5
""")

print("NFL/Sports Trades:")
print("=" * 80)
for row in cursor.fetchall():
    trade_id, event_id, condition_id, market, opened_at = row
    print(f"\nTrade ID: {trade_id}")
    print(f"  Market: {market}")
    print(f"  Opened: {opened_at}")
    print(f"  event_id: {event_id}")
    print(f"  condition_id: {condition_id}")
    print(f"  event_id length: {len(event_id) if event_id else 0}")
    print(f"  condition_id length: {len(condition_id) if condition_id else 0}")

# Check a few recent trades
print("\n\nRecent Trades:")
print("=" * 80)
cursor.execute("""
    SELECT id, event_id, condition_id, market, opened_at 
    FROM paper_trades 
    ORDER BY opened_at DESC
    LIMIT 5
""")

for row in cursor.fetchall():
    trade_id, event_id, condition_id, market, opened_at = row
    print(f"\nTrade ID: {trade_id}")
    print(f"  Market: {market[:60]}")
    print(f"  Opened: {opened_at}")
    print(f"  event_id: {event_id[:66] if event_id else None}")
    print(f"  condition_id: {condition_id[:66] if condition_id else None}")

conn.close()

