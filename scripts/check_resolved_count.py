#!/usr/bin/env python3
"""Check resolved trade counts."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.storage import SignalStore

store = SignalStore()
conn = store._get_connection()
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM paper_trades WHERE status = "RESOLVED"')
resolved = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM paper_trades WHERE status = "OPEN"')
open_count = cursor.fetchone()[0]

cursor.execute('SELECT SUM(pnl_usd) FROM paper_trades WHERE status = "RESOLVED"')
total_pnl = cursor.fetchone()[0] or 0.0

cursor.execute('SELECT COUNT(*) FROM paper_trades WHERE status = "RESOLVED" AND won = 1')
wins = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM paper_trades WHERE status = "RESOLVED" AND won = 0')
losses = cursor.fetchone()[0]

print(f"Resolved: {resolved}")
print(f"Open: {open_count}")
print(f"Total PnL: ${total_pnl:.2f}")
print(f"Wins: {wins}")
print(f"Losses: {losses}")
if resolved > 0:
    print(f"Win Rate: {(wins/resolved*100):.1f}%")

conn.close()

