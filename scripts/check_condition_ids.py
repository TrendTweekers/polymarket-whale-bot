#!/usr/bin/env python3
"""Check condition IDs for specific markets."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.storage import SignalStore
import sqlite3

store = SignalStore()
conn = store._get_connection()
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

markets = ["Jazz", "Nuggets", "Raptors", "Nets", "Mavericks", "Pelicans", "Grizzlies", "Thunder", "Rockets", "Kings", "Spurs", "Wizards", "Patriots", "Ravens", "Steelers", "Lions"]

for market in markets:
    cursor.execute("""
        SELECT pt.id, pt.event_id, s.market, pt.outcome_name
        FROM paper_trades pt
        LEFT JOIN signals s ON pt.signal_id = s.id
        WHERE pt.status = 'OPEN'
        AND s.market LIKE ?
        LIMIT 5
    """, (f"%{market}%",))
    
    rows = cursor.fetchall()
    if rows:
        print(f"\n{market}:")
        for row in rows:
            print(f"  ID: {row['id']}, Market: {row['market'][:50]}, Event ID: {row['event_id'][:20]}..., Outcome: {row['outcome_name']}")

conn.close()

