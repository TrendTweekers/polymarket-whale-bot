#!/usr/bin/env python3
"""Find recent trades that might have resolved."""
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

# Find sports trades from Dec 21-22 that are still open
cursor.execute("""
    SELECT pt.id, pt.event_id, s.market, pt.outcome_name, pt.opened_at, pt.status
    FROM paper_trades pt
    LEFT JOIN signals s ON pt.signal_id = s.id
    WHERE pt.status = 'OPEN'
    AND (s.market LIKE '%vs%' OR s.market LIKE '%NFL%' OR s.market LIKE '%NBA%' OR s.market LIKE '%Bulls%' OR s.market LIKE '%Hawks%' OR s.market LIKE '%Raiders%' OR s.market LIKE '%Texans%' OR s.market LIKE '%Bucks%' OR s.market LIKE '%Timberwolves%')
    AND pt.opened_at LIKE '2025-12-2%'
    ORDER BY pt.opened_at DESC
    LIMIT 30
""")

print("Recent Sports Trades (Dec 21-22):")
print("=" * 100)
trades = []
for trade in cursor.fetchall():
    trades.append(trade)
    print(f"\nTrade ID: {trade['id']}")
    print(f"  Market: {trade['market']}")
    print(f"  Outcome: {trade['outcome_name']}")
    print(f"  Event ID: {trade['event_id'][:40]}...")
    print(f"  Opened: {trade['opened_at']}")

print(f"\n\nTotal found: {len(trades)}")
conn.close()

