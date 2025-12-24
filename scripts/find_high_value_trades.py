#!/usr/bin/env python3
"""Find high-value trades sorted by stake."""
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
    SELECT pt.id, pt.event_id, s.market, pt.outcome_name, pt.stake_usd, pt.confidence, pt.opened_at
    FROM paper_trades pt
    LEFT JOIN signals s ON pt.signal_id = s.id
    WHERE pt.status = 'OPEN'
    AND pt.event_id IS NOT NULL
    AND pt.event_id != ''
    ORDER BY pt.stake_usd DESC, pt.confidence DESC
    LIMIT 50
""")

trades = cursor.fetchall()
print(f"Top {len(trades)} High-Value Trades:")
print("=" * 100)
print(f"{'ID':<6} {'Stake':<10} {'Conf':<6} {'Market':<50} {'Event ID':<25}")
print("-" * 100)

for trade in trades:
    trade_id = trade['id']
    stake = trade.get('stake_usd', 0.0)
    conf = trade.get('confidence', 0)
    market = (trade.get('market') or 'Unknown')[:48]
    event_id = (trade.get('event_id') or '')[:23]
    
    stake_str = f"${stake:.2f}" if stake else "$0.00"
    conf_str = str(conf) if conf else "0"
    market_str = market[:48] if market else "Unknown"
    event_id_str = event_id[:23] if event_id else "N/A"
    print(f"{trade_id:<6} {stake_str:<10} {conf_str:<6} {market_str:<50} {event_id_str:<25}")

print("\n" + "=" * 100)
print(f"Total stake in top {len(trades)}: ${sum(t.get('stake_usd', 0) for t in trades):.2f}")

conn.close()

