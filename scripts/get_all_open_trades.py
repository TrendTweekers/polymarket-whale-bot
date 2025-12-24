#!/usr/bin/env python3
"""Get all open trades with condition_ids."""
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
    SELECT pt.id, pt.event_id, s.market, pt.outcome_name, pt.opened_at, pt.stake_usd
    FROM paper_trades pt
    LEFT JOIN signals s ON pt.signal_id = s.id
    WHERE pt.status = 'OPEN'
    ORDER BY pt.stake_usd DESC, pt.opened_at DESC
""")

trades = cursor.fetchall()
print(f"Total open trades: {len(trades)}")
print("=" * 100)
print("\n# Condition IDs for all open trades (sorted by stake, highest first):\n")

for trade in trades:
    cond_id = trade['event_id']
    cond_prefix = cond_id[:20] if cond_id else 'N/A'
    market = trade['market'][:70] if trade['market'] else 'Unknown'
    outcome = trade['outcome_name'] or 'N/A'
    stake = trade['stake_usd'] or 0.0
    
    print(f'    "{cond_prefix}": {{  # {market} | Stake: ${stake:.2f} | Outcome: {outcome}')
    print(f'        "winning_outcome_index": 0,  # TODO: Set based on result')
    print(f'        "note": "TODO: Add result"')
    print(f'    }},')

conn.close()

