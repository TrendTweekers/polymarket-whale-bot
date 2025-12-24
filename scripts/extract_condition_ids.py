#!/usr/bin/env python3
"""Extract condition_ids for specific markets."""
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

# Find specific markets
markets_to_find = [
    "Bulls", "Hawks", "Magic", "Jazz", "Lakers", "Clippers",
    "Raiders", "Texans", "Bucks", "Timberwolves"
]

print("Condition IDs for Target Markets:")
print("=" * 100)

for market_term in markets_to_find:
    cursor.execute("""
        SELECT pt.id, pt.event_id, s.market, pt.outcome_name, pt.status
        FROM paper_trades pt
        LEFT JOIN signals s ON pt.signal_id = s.id
        WHERE pt.status = 'OPEN'
        AND s.market LIKE ?
        ORDER BY pt.opened_at DESC
        LIMIT 5
    """, (f'%{market_term}%',))
    
    trades = cursor.fetchall()
    if trades:
        print(f"\n{market_term}:")
        for trade in trades:
            cond_id_preview = trade['event_id'][:20] if trade['event_id'] else 'N/A'
            print(f"  Trade {trade['id']}: {trade['market'][:60]}")
            print(f"    Condition ID: {cond_id_preview}...")
            print(f"    Outcome: {trade['outcome_name']}")
            print(f"    Full Event ID: {trade['event_id']}")

conn.close()

