#!/usr/bin/env python3
"""
Paper Trading Report - Detailed statistics and performance metrics.
Usage: python scripts/paper_report.py
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


def get_total_signals():
    """Get total signal count."""
    if not DB_PATH.exists():
        return 0
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM signals")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_open_paper_trades_count():
    """Get count of open paper trades."""
    if not DB_PATH.exists():
        return 0
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM paper_trades WHERE status = 'OPEN'")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_resolved_paper_trades_count():
    """Get count of resolved paper trades."""
    if not DB_PATH.exists():
        return 0
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM paper_trades WHERE status = 'RESOLVED'")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_total_pnl():
    """Get total PnL in USD."""
    if not DB_PATH.exists():
        return 0.0
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(pnl_usd), 0.0) FROM paper_trades WHERE status = 'RESOLVED'")
    pnl = cursor.fetchone()[0]
    conn.close()
    return float(pnl) if pnl else 0.0


def get_winrate_overall():
    """Get overall win rate."""
    if not DB_PATH.exists():
        return None
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN won = 1 THEN 1 ELSE 0 END) as won
        FROM paper_trades
        WHERE status = 'RESOLVED'
    """)
    row = cursor.fetchone()
    conn.close()
    
    if not row or row[0] == 0:
        return None
    
    total, won = row
    return (won / total * 100) if total > 0 else 0.0


def get_winrate_by_confidence_tier():
    """Get win rate by confidence tier."""
    if not DB_PATH.exists():
        return {}
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    tiers = {
        "🟢 Strong (80-100)": "confidence >= 80",
        "🟡 Medium (60-79)": "confidence >= 60 AND confidence < 80",
        "🟠 Weak (40-59)": "confidence >= 40 AND confidence < 60",
        "🔴 Skip (0-39)": "confidence < 40",
    }
    
    results = {}
    for tier_name, condition in tiers.items():
        cursor.execute(f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN pt.won = 1 THEN 1 ELSE 0 END) as won
            FROM paper_trades pt
            LEFT JOIN signals s ON pt.signal_id = s.id
            WHERE pt.status = 'RESOLVED' AND ({condition})
        """)
        row = cursor.fetchone()
        if row and row[0] > 0:
            total, won = row
            winrate = (won / total * 100) if total > 0 else 0.0
            results[tier_name] = {
                "total": total,
                "won": won,
                "winrate": winrate
            }
    
    conn.close()
    return results


def get_last_resolved_trades(limit=20):
    """Get last N resolved trades."""
    if not DB_PATH.exists():
        return []
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            pt.resolved_at,
            s.confidence,
            s.market,
            pt.outcome_name,
            pt.side,
            pt.entry_price,
            pt.resolved_at,
            pt.won,
            pt.pnl_usd
        FROM paper_trades pt
        LEFT JOIN signals s ON pt.signal_id = s.id
        WHERE pt.status = 'RESOLVED'
        ORDER BY pt.resolved_at DESC
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return rows


def print_summary():
    """Print overall summary."""
    total_signals = get_total_signals()
    open_trades = get_open_paper_trades_count()
    resolved_trades = get_resolved_paper_trades_count()
    total_pnl = get_total_pnl()
    winrate = get_winrate_overall()
    
    print("=" * 100)
    print("📊 Paper Trading Report")
    print("=" * 100)
    
    if not DB_PATH.exists():
        print(f"\n❌ Database not found at: {DB_PATH}")
        print("   Run the engine with PAPER_TRADING=1 to generate paper trades.")
        return
    
    print(f"\n📁 Database: {DB_PATH}")
    print(f"📅 Updated: {datetime.fromtimestamp(DB_PATH.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
    
    print(f"\n📈 Overall Statistics:")
    print("-" * 100)
    print(f"Total Signals: {total_signals}")
    print(f"Open Paper Trades: {open_trades}")
    print(f"Resolved Paper Trades: {resolved_trades}")
    
    if resolved_trades > 0:
        print(f"Total PnL: ${total_pnl:.2f} USD")
        if winrate is not None:
            print(f"Overall Win Rate: {winrate:.1f}%")
    else:
        print("Total PnL: $0.00 USD (no resolved trades yet)")
        print("Overall Win Rate: N/A (no resolved trades yet)")
    
    print()


def print_winrate_by_tier():
    """Print win rate by confidence tier."""
    tiers = get_winrate_by_confidence_tier()
    
    if not tiers:
        print("📊 Win Rate by Confidence Tier:")
        print("-" * 100)
        print("No resolved trades yet.")
        print()
        return
    
    print("📊 Win Rate by Confidence Tier:")
    print("-" * 100)
    print(f"{'Tier':<25} {'Total':>8} {'Won':>8} {'Win Rate':>12}")
    print("-" * 100)
    
    for tier_name, stats in tiers.items():
        print(f"{tier_name:<25} {stats['total']:>8} {stats['won']:>8} {stats['winrate']:>11.1f}%")
    
    print()


def print_last_resolved_trades(limit=20):
    """Print last N resolved trades."""
    trades = get_last_resolved_trades(limit)
    
    if not trades:
        print("📋 Last Resolved Trades:")
        print("-" * 100)
        print("No resolved trades yet.")
        print()
        return
    
    print(f"📋 Last {len(trades)} Resolved Trades:")
    print("-" * 100)
    print(f"{'Resolved':<20} {'Conf':<6} {'Side':<6} {'Outcome':<15} {'Entry':<10} {'Won':<6} {'PnL USD':<12} {'Market':<30}")
    print("-" * 100)
    
    for row in trades:
        resolved_at, confidence, market, outcome, side, entry_price, _, won, pnl_usd = row
        
        resolved_str = resolved_at[:19] if resolved_at and len(resolved_at) > 19 else (resolved_at or "N/A")
        conf_str = f"{confidence}/100" if confidence is not None else "N/A"
        side_str = side or "N/A"
        outcome_str = (outcome[:13] + "...") if outcome and len(outcome) > 15 else (outcome or "N/A")
        entry_str = f"{entry_price:.4f}" if entry_price else "N/A"
        won_str = "✅" if won == 1 else "❌"
        pnl_str = f"${pnl_usd:.2f}" if pnl_usd is not None else "$0.00"
        market_short = (market[:27] + "...") if market and len(market) > 30 else (market or "N/A")
        
        print(f"{resolved_str:<20} {conf_str:<6} {side_str:<6} {outcome_str:<15} {entry_str:<10} {won_str:<6} {pnl_str:<12} {market_short:<30}")
    
    print()


def main():
    """Main entry point."""
    print_summary()
    print_winrate_by_tier()
    print_last_resolved_trades(20)
    print("=" * 100)


if __name__ == "__main__":
    main()

