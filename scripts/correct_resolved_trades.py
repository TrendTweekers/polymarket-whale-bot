#!/usr/bin/env python3
"""
Script to correct already-resolved trades that have incorrect outcomes.
This resets trades with suspicious outcomes back to OPEN status so they can be re-resolved correctly.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.storage import SignalStore
import sqlite3

def reset_suspicious_trades():
    """Reset trades with suspicious outcomes back to OPEN."""
    store = SignalStore()
    conn = store._get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Find resolved trades that might have incorrect outcomes
    # Look for trades with very small PnL (might indicate wrong resolution)
    # or trades resolved recently (last batch)
    cursor.execute("""
        SELECT pt.id, pt.event_id, s.market, pt.outcome_name, pt.status, pt.pnl_usd, pt.resolved_at
        FROM paper_trades pt
        LEFT JOIN signals s ON pt.signal_id = s.id
        WHERE pt.status = 'RESOLVED'
        AND pt.resolved_at IS NOT NULL
        ORDER BY pt.resolved_at DESC
        LIMIT 50
    """)
    
    suspicious_trades = []
    for row in cursor.fetchall():
        # Check for suspicious patterns
        pnl = row.get('pnl_usd', 0.0)
        market = row.get('market', '')
        
        # Flag if PnL is suspiciously small (might be wrong resolution)
        # or if market name contains patterns that suggest false positives
        is_suspicious = False
        if pnl and abs(pnl) < 0.10:  # Very small PnL
            is_suspicious = True
        
        if is_suspicious:
            suspicious_trades.append({
                'id': row['id'],
                'event_id': row['event_id'],
                'market': market,
                'pnl': pnl
            })
    
    if not suspicious_trades:
        print("No suspicious trades found to reset.")
        return
    
    print(f"Found {len(suspicious_trades)} suspicious resolved trades:")
    print("=" * 100)
    for trade in suspicious_trades:
        print(f"  ID: {trade['id']}, Market: {trade['market'][:50]}, PnL: ${trade['pnl']:.2f}")
    
    print("\n" + "=" * 100)
    response = input(f"\nReset these {len(suspicious_trades)} trades back to OPEN? (yes/no): ")
    
    if response.lower() != 'yes':
        print("Cancelled.")
        return
    
    # Reset trades
    reset_count = 0
    for trade in suspicious_trades:
        try:
            cursor.execute("""
                UPDATE paper_trades
                SET status = 'OPEN',
                    resolved_at = NULL,
                    resolved_outcome_index = NULL,
                    won = NULL,
                    pnl_usd = NULL
                WHERE id = ?
            """, (trade['id'],))
            reset_count += 1
        except Exception as e:
            print(f"Error resetting trade {trade['id']}: {e}")
    
    conn.commit()
    print(f"\n✅ Reset {reset_count} trades back to OPEN status.")
    print("💡 Now run: python scripts/manual_resolve_trades.py --all-known")
    
    conn.close()

if __name__ == "__main__":
    reset_suspicious_trades()

