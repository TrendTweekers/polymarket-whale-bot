#!/usr/bin/env python3
"""Check detailed trade information."""
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
    SELECT pt.id, pt.outcome_index, pt.outcome_name, pt.side, pt.entry_price, pt.stake_usd, s.market
    FROM paper_trades pt
    LEFT JOIN signals s ON pt.signal_id = s.id
    WHERE pt.id IN (241, 243)
""")

print("Trade Details:")
print("=" * 100)
for trade in cursor.fetchall():
    print(f"\nTrade ID: {trade['id']}")
    print(f"  Market: {trade['market']}")
    print(f"  Outcome Index: {trade['outcome_index']}")
    print(f"  Outcome Name: {trade['outcome_name']}")
    print(f"  Side: {trade['side']}")
    print(f"  Entry Price: {trade['entry_price']}")
    print(f"  Stake: ${trade['stake_usd']:.2f}")

conn.close()

