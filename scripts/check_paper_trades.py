#!/usr/bin/env python3
"""Check paper trading status"""
import sqlite3
from pathlib import Path

db_path = Path("logs/paper_trading.sqlite")

if not db_path.exists():
    print("❌ No paper trading database found")
    print(f"   Expected: {db_path}")
    exit(1)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Count paper trades
cursor.execute("SELECT COUNT(*) FROM paper_trades")
total = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM paper_trades WHERE status = 'open'")
open_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM paper_trades WHERE status = 'closed'")
closed_count = cursor.fetchone()[0]

print("=" * 60)
print("📊 PAPER TRADING STATUS")
print("=" * 60)
print(f"\nTotal Paper Trades: {total}")
print(f"  • Open: {open_count}")
print(f"  • Closed: {closed_count}")

if total > 0:
    print(f"\n📋 Recent Paper Trades:")
    cursor.execute("""
        SELECT 
            pt.trade_id,
            pt.wallet,
            pt.market,
            pt.status,
            pt.stake_eur,
            pt.created_at
        FROM paper_trades pt
        ORDER BY pt.created_at DESC
        LIMIT 10
    """)
    
    for row in cursor.fetchall():
        trade_id, wallet, market, status, stake, created = row
        print(f"\n  Trade ID: {trade_id}")
        print(f"  Wallet: {wallet[:16]}...")
        print(f"  Market: {market[:50]}...")
        print(f"  Status: {status}")
        print(f"  Stake: €{stake}")
        print(f"  Created: {created}")

conn.close()
print("\n" + "=" * 60)
