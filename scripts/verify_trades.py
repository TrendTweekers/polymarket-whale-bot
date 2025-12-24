#!/usr/bin/env python3
"""Verify trade question text."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.storage import SignalStore
import sqlite3

store = SignalStore()
conn = store._get_connection()
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("""
    SELECT pt.id, s.market, pt.market_question, pt.event_id, pt.status
    FROM paper_trades pt
    LEFT JOIN signals s ON pt.signal_id = s.id
    WHERE pt.id IN (241, 243)
""")

print("Trade Verification:")
print("=" * 100)
for row in cursor.fetchall():
    print(f"\nTrade ID: {row['id']}")
    print(f"Market: {row['market']}")
    print(f"Status: {row['status']}")
    print(f"Event ID: {row['event_id'][:40]}...")
    print(f"Question Length: {len(row['market_question']) if row['market_question'] else 0}")
    if row['market_question']:
        print(f"Question Preview: {row['market_question'][:200]}...")
    else:
        print("Question: NULL")

conn.close()

