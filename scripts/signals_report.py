#!/usr/bin/env python3
"""
Query and display signal statistics from SQLite database.
Usage: python scripts/signals_report.py
"""
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

DB_PATH = project_root / "logs" / "paper_trading.sqlite"


def print_recent_signals(limit=20):
    """Print the most recent signals."""
    if not DB_PATH.exists():
        print("❌ Database not found. Run the engine first to generate signals.")
        return
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            ts, confidence, category, market, side, outcome_name, wallet_prefix10
        FROM signals
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("No signals found in database.")
        return
    
    print(f"\n📊 Last {len(rows)} Signals:")
    print("-" * 100)
    print(f"{'Time':<20} {'Conf':<6} {'Category':<12} {'Side':<6} {'Outcome':<15} {'Wallet':<12} {'Market':<30}")
    print("-" * 100)
    
    for row in rows:
        ts, confidence, category, market, side, outcome, wallet = row
        # Truncate market name
        market_short = (market[:27] + "...") if market and len(market) > 30 else (market or "N/A")
        # Format confidence with tier
        conf_str = f"{confidence}/100" if confidence is not None else "N/A"
        # Format timestamp
        ts_str = ts[:19] if ts and len(ts) > 19 else (ts or "N/A")
        
        print(f"{ts_str:<20} {conf_str:<6} {category or 'N/A':<12} {side or 'N/A':<6} {outcome or 'N/A':<15} {wallet or 'N/A':<12} {market_short:<30}")


def print_confidence_buckets():
    """Print signal counts by confidence bucket."""
    if not DB_PATH.exists():
        return
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    buckets = {
        "🟢 Strong (80-100)": "confidence >= 80",
        "🟡 Medium (60-79)": "confidence >= 60 AND confidence < 80",
        "🟠 Weak (40-59)": "confidence >= 40 AND confidence < 60",
        "🔴 Skip (0-39)": "confidence < 40",
        "❓ Unknown": "confidence IS NULL"
    }
    
    print("\n📈 Signals by Confidence Tier:")
    print("-" * 50)
    
    total = 0
    for label, condition in buckets.items():
        cursor.execute(f"SELECT COUNT(*) FROM signals WHERE {condition}")
        count = cursor.fetchone()[0]
        total += count
        print(f"{label:<25} {count:>6}")
    
    cursor.execute("SELECT COUNT(*) FROM signals")
    all_count = cursor.fetchone()[0]
    print("-" * 50)
    print(f"{'Total Signals':<25} {all_count:>6}")
    
    conn.close()


def print_category_counts(limit=10):
    """Print top categories by signal count."""
    if not DB_PATH.exists():
        return
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT category, COUNT(*) as count
        FROM signals
        WHERE category IS NOT NULL AND category != ''
        GROUP BY category
        ORDER BY count DESC
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return
    
    print(f"\n🏷️  Top {len(rows)} Categories:")
    print("-" * 50)
    print(f"{'Category':<20} {'Count':>6}")
    print("-" * 50)
    
    for category, count in rows:
        print(f"{category:<20} {count:>6}")


def print_open_paper_trades():
    """Print open paper trades."""
    if not DB_PATH.exists():
        return
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            pt.opened_at, s.confidence, s.category, s.market, pt.side, pt.outcome_name, pt.stake_usd
        FROM paper_trades pt
        LEFT JOIN signals s ON pt.signal_id = s.id
        WHERE pt.status = 'OPEN'
        ORDER BY pt.opened_at DESC
        LIMIT 20
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return
    
    print(f"\n📋 Open Paper Trades ({len(rows)}):")
    print("-" * 100)
    print(f"{'Opened':<20} {'Conf':<6} {'Category':<12} {'Side':<6} {'Outcome':<15} {'Stake USD':<12} {'Market':<30}")
    print("-" * 100)
    
    for row in rows:
        opened_at, confidence, category, market, side, outcome, stake_usd = row
        market_short = (market[:27] + "...") if market and len(market) > 30 else (market or "N/A")
        conf_str = f"{confidence}/100" if confidence is not None else "N/A"
        opened_str = opened_at[:19] if opened_at and len(opened_at) > 19 else (opened_at or "N/A")
        
        print(f"{opened_str:<20} {conf_str:<6} {category or 'N/A':<12} {side or 'N/A':<6} {outcome or 'N/A':<15} ${stake_usd:.2f} {'':<6} {market_short:<30}")


def print_pnl_summary():
    """Print PnL summary."""
    if not DB_PATH.exists():
        return
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Total PnL
    cursor.execute("""
        SELECT 
            COUNT(*) as total_trades,
            SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open_trades,
            SUM(CASE WHEN status = 'RESOLVED' THEN 1 ELSE 0 END) as resolved_trades,
            SUM(CASE WHEN won = 1 THEN 1 ELSE 0 END) as won_trades,
            SUM(CASE WHEN won = 0 AND status = 'RESOLVED' THEN 1 ELSE 0 END) as lost_trades,
            COALESCE(SUM(pnl_usd), 0.0) as total_pnl
        FROM paper_trades
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    if not row or row[0] == 0:
        return
    
    total_trades, open_trades, resolved_trades, won_trades, lost_trades, total_pnl = row
    
    print(f"\n💰 Paper Trading Summary:")
    print("-" * 50)
    print(f"Total Trades: {total_trades}")
    print(f"Open: {open_trades}")
    print(f"Resolved: {resolved_trades}")
    if resolved_trades > 0:
        win_rate = (won_trades / resolved_trades * 100) if resolved_trades > 0 else 0.0
        print(f"Won: {won_trades} | Lost: {lost_trades}")
        print(f"Win Rate: {win_rate:.1f}%")
    print(f"Total PnL: ${total_pnl:.2f} USD")


def main():
    """Main entry point."""
    print("=" * 100)
    print("🐋 Polymarket Signal Report")
    print("=" * 100)
    
    if not DB_PATH.exists():
        print(f"\n❌ Database not found at: {DB_PATH}")
        print("   Run the engine first to generate signals.")
        return
    
    print(f"\n📁 Database: {DB_PATH}")
    print(f"📅 Generated: {datetime.fromtimestamp(DB_PATH.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
    
    print_recent_signals(20)
    print_confidence_buckets()
    print_category_counts(10)
    print_open_paper_trades()
    print_pnl_summary()
    
    print("\n" + "=" * 100)


if __name__ == "__main__":
    main()

