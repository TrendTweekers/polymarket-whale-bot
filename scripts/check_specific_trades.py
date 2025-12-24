#!/usr/bin/env python3
"""Check specific trade details."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.storage import SignalStore

store = SignalStore()
conn = store._get_connection()
conn.row_factory = lambda cursor, row: {
    col[0]: row[idx] for idx, col in enumerate(cursor.description)
}
cursor = conn.cursor()

cursor.execute("""
    SELECT pt.id, pt.outcome_name, pt.side, pt.event_id, s.market
    FROM paper_trades pt
    LEFT JOIN signals s ON pt.signal_id = s.id
    WHERE pt.id IN (242, 261)
""")

print("Trade Details:")
print("=" * 100)
for trade in cursor.fetchall():
    print(f"\nTrade ID: {trade['id']}")
    print(f"  Market: {trade['market']}")
    print(f"  Outcome Name: {trade['outcome_name']}")
    print(f"  Side: {trade['side']}")
    print(f"  Event ID: {trade['event_id'][:40]}...")

conn.close()

