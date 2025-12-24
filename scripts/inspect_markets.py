#!/usr/bin/env python3
"""Inspect market names to understand formats."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.storage import SignalStore
import sqlite3

store = SignalStore()
conn = store._get_connection()
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get sample markets
cursor.execute("""
    SELECT DISTINCT s.market, pt.outcome_name
    FROM paper_trades pt
    LEFT JOIN signals s ON pt.signal_id = s.id
    WHERE pt.status = 'OPEN'
    ORDER BY s.market
    LIMIT 30
""")

print("Sample Market Names:")
print("=" * 100)
for row in cursor.fetchall():
    market = row['market'] or 'Unknown'
    outcome = row['outcome_name'] or ''
    print(f"{market[:70]:<70} | Outcome: {outcome[:30]}")

conn.close()

