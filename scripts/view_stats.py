"""
View bot statistics and performance
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.storage.trade_database import TradeDatabase
from datetime import datetime
import json


def print_separator(char="=", length=100):
    print(char * length)


def view_stats():
    """Display comprehensive statistics"""
    
    db = TradeDatabase()
    stats = db.get_stats_summary()
    
    print("\n")
    print_separator()
    print("🐋 POLYMARKET WHALE BOT - STATISTICS DASHBOARD")
    print_separator()
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Overview
    print("📊 OVERVIEW")
    print_separator("-")
    overview = stats['overview']
    for key, value in overview.items():
        print(f"  {key.replace('_', ' ').title():.<30} {value:>20}")
    print()
    
    # Performance
    print("🎯 PERFORMANCE")
    print_separator("-")
    performance = stats['performance']
    for key, value in performance.items():
        print(f"  {key.replace('_', ' ').title():.<30} {value:>20}")
    print()
    
    # Volume
    print("💰 VOLUME")
    print_separator("-")
    volume = stats['volume']
    for key, value in volume.items():
        print(f"  {key.replace('_', ' ').title():.<30} {value:>20}")
    print()
    
    # Top Whales
    print("🐋 TOP WHALES")
    print_separator("-")
    whales = stats['whales']
    if whales:
        for whale_id, whale_stats in list(whales.items())[:5]:
            print(f"\n  Whale: {whale_id[:16]}...")
            print(f"    Trades: {whale_stats['trades']}")
            print(f"    Wins: {whale_stats['wins']}")
            print(f"    P&L: ${whale_stats['pnl']:+,.2f}")
            if whale_stats['trades'] > 0:
                win_rate = whale_stats['wins'] / whale_stats['trades']
                print(f"    Win Rate: {win_rate:.1%}")
    else:
        print("  No whale data yet")
    print()
    
    # Recent Trades
    print("📝 RECENT TRADES (Last 5)")
    print_separator("-")
    recent = stats['recent_trades']
    if recent:
        for i, trade in enumerate(recent, 1):
            status_emoji = "✅" if trade.get('outcome') == 'win' else "❌" if trade.get('outcome') == 'loss' else "⏳"
            pnl = trade.get('pnl', 0)
            pnl_str = f"${pnl:+.2f}" if pnl != 0 else "Pending"
            
            print(f"\n  {i}. {status_emoji} {trade['trade_id']}")
            print(f"     Market: {trade.get('market_question', 'Unknown')[:60]}")
            print(f"     Direction: {trade['direction']} | Size: ${trade['position_size']:.2f}")
            print(f"     Status: {trade['status'].upper()} | P&L: {pnl_str}")
            print(f"     Time: {trade['timestamp'][:19]}")
    else:
        print("  No trades yet")
    print()
    
    print_separator()
    print()


def view_all_trades():
    """Display all trades in detail"""
    
    db = TradeDatabase()
    
    print("\n")
    print_separator()
    print("📋 ALL TRADES")
    print_separator()
    print()
    
    trades = db.trades
    
    if not trades:
        print("  No trades recorded yet.")
        print()
        return
    
    for i, trade in enumerate(trades, 1):
        status_emoji = "✅" if trade.get('outcome') == 'win' else "❌" if trade.get('outcome') == 'loss' else "⏳"
        
        print(f"{i}. {status_emoji} {trade['trade_id']}")
        print(f"   Whale: {trade.get('whale_name', 'Unknown')} ({trade['whale_id'][:16]}...)")
        print(f"   Market: {trade.get('market_question', 'Unknown')}")
        print(f"   Direction: {trade['direction']} | Size: ${trade['position_size']:.2f} | Price: ${trade.get('entry_price', 0):.3f}")
        print(f"   Confidence: {trade['confidence']:.2%}")
        print(f"   Opened: {trade['timestamp'][:19]}")
        
        if trade.get('status') == 'completed':
            pnl = trade.get('pnl', 0)
            duration = trade.get('duration_days', 0)
            print(f"   Closed: {trade.get('closed_at', 'N/A')[:19]}")
            print(f"   Result: {trade.get('outcome', 'Unknown').upper()} | P&L: ${pnl:+.2f} | Duration: {duration} days")
        else:
            print(f"   Status: ACTIVE")
        
        print()
    
    print_separator()
    print()


def export_trades_csv():
    """Export trades to CSV"""
    
    db = TradeDatabase()
    csv_file = Path("data/trades_export.csv")
    
    import csv
    
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow([
            'Trade ID', 'Timestamp', 'Whale ID', 'Whale Name',
            'Market Question', 'Direction', 'Position Size', 'Entry Price',
            'Confidence', 'Status', 'Outcome', 'P&L', 'Duration Days', 'Closed At'
        ])
        
        # Data
        for trade in db.trades:
            writer.writerow([
                trade['trade_id'],
                trade['timestamp'],
                trade['whale_id'],
                trade.get('whale_name', 'Unknown'),
                trade.get('market_question', 'Unknown'),
                trade['direction'],
                trade['position_size'],
                trade.get('entry_price', 0),
                trade['confidence'],
                trade['status'],
                trade.get('outcome', ''),
                trade.get('pnl', 0),
                trade.get('duration_days', 0),
                trade.get('closed_at', '')
            ])
    
    print(f"\n✅ Trades exported to: {csv_file}")
    print()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "all":
            view_all_trades()
        elif command == "export":
            export_trades_csv()
        else:
            print(f"Unknown command: {command}")
            print("Usage: python scripts/view_stats.py [all|export]")
    else:
        view_stats()
