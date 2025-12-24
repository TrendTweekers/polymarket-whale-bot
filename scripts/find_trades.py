#!/usr/bin/env python3
"""Find trades matching specific criteria."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.storage import SignalStore
import sqlite3

store = SignalStore()
conn = store._get_connection()
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Find Raiders/Texans trades
cursor.execute("""
    SELECT pt.id, s.market, pt.market_question, pt.event_id, pt.opened_at, pt.outcome_index, pt.outcome_name
    FROM paper_trades pt
    LEFT JOIN signals s ON pt.signal_id = s.id
    WHERE s.market LIKE '%Raiders%' OR s.market LIKE '%Texans%' OR s.market LIKE '%LV%' OR s.market LIKE '%HOU%'
    ORDER BY pt.opened_at DESC
    LIMIT 20
""")

print("Raiders/Texans Trades:")
print("=" * 100)
for row in cursor.fetchall():
    print(f"\nTrade ID: {row['id']}")
    print(f"  Market: {row['market']}")
    print(f"  Current Question: {row['market_question'][:80] if row['market_question'] else 'NULL'}...")
    print(f"  Event ID: {row['event_id'][:40]}...")
    print(f"  Outcome: {row['outcome_name']} (index: {row['outcome_index']})")
    print(f"  Opened: {row['opened_at']}")

conn.close()

