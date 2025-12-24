#!/usr/bin/env python3
"""Find recently resolved trades with suspicious outcomes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.storage import SignalStore
import sqlite3

store = SignalStore()
conn = store._get_connection()
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Find recently resolved trades with suspicious notes or outcomes
cursor.execute("""
    SELECT pt.id, pt.event_id, s.market, pt.outcome_name, pt.status, pt.pnl_usd, pt.resolved_at
    FROM paper_trades pt
    LEFT JOIN signals s ON pt.signal_id = s.id
    WHERE pt.status = 'COMPLETED'
    AND pt.resolved_at IS NOT NULL
    ORDER BY pt.resolved_at DESC
    LIMIT 50
""")

trades = cursor.fetchall()

print("Recently Resolved Trades (Last 50):")
print("=" * 100)
print(f"{'ID':<6} {'Market':<50} {'Outcome':<20} {'PnL':<10} {'Event ID':<25}")
print("-" * 100)

suspicious_count = 0
for trade in trades:
    trade_id = trade['id']
    market = (trade.get('market') or 'Unknown')[:48]
    outcome = (trade.get('outcome_name') or '')[:18]
    pnl = trade.get('pnl_usd', 0.0)
    event_id = (trade.get('event_id') or '')[:23]
    
    # Check for suspicious patterns
    is_suspicious = False
    if pnl and abs(pnl) < 0.10:  # Very small PnL might indicate wrong resolution
        is_suspicious = True
    if "960" in str(market) or "960" in str(outcome):
        is_suspicious = True
    
    marker = " ⚠️ " if is_suspicious else "   "
    if is_suspicious:
        suspicious_count += 1
    
    print(f"{marker}{trade_id:<6} {market:<50} {outcome:<20} ${pnl:<9.2f} {event_id:<25}")

print("\n" + "=" * 100)
print(f"Total resolved: {len(trades)}")
print(f"Suspicious (needs review): {suspicious_count}")

conn.close()

