#!/usr/bin/env python3
"""List all condition_ids for open trades in a format easy to copy."""
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
    SELECT pt.id, pt.event_id, s.market, pt.outcome_name, pt.opened_at
    FROM paper_trades pt
    LEFT JOIN signals s ON pt.signal_id = s.id
    WHERE pt.status = 'OPEN'
    AND pt.opened_at LIKE '2025-12-2%'
    ORDER BY pt.opened_at DESC
    LIMIT 50
""")

print("Condition IDs for Open Trades (Dec 21-22):")
print("=" * 100)
print("\n# Copy these to add to KNOWN_OUTCOMES_BY_CONDITION:")
print()

for trade in cursor.fetchall():
    cond_id = trade['event_id']
    cond_prefix = cond_id[:20] if cond_id else 'N/A'
    market = trade['market'][:60] if trade['market'] else 'Unknown'
    outcome = trade['outcome_name'] or 'N/A'
    
    print(f'    "{cond_prefix}": {{  # {market}')
    print(f'        "winning_outcome_index": 0,  # TODO: Set based on result')
    print(f'        "note": "TODO: Add result"')
    print(f'    }},')
    print()

conn.close()

