#!/usr/bin/env python3
"""Quick progress check for paper trading"""
import json
from pathlib import Path
from datetime import datetime

def check_progress():
    """Check paper trading progress"""
    trades_file = Path('data/paper_trades.json')
    
    if not trades_file.exists():
        print("📊 Paper Trading: No trades yet")
        return
    
    with open(trades_file, 'r') as f:
        trades = json.load(f)
    
    if not trades:
        print("📊 Paper Trading: No trades yet")
        return
    
    open_trades = [t for t in trades if t.get('status') == 'open']
    pending_trades = [t for t in trades if t.get('status') == 'pending_entry']
    completed_trades = [t for t in trades if t.get('status') == 'completed']
    
    print("=" * 60)
    print("📊 PAPER TRADING PROGRESS")
    print("=" * 60)
    print(f"\nTotal Trades: {len(trades)}")
    print(f"  • Open: {len(open_trades)}")
    print(f"  • Pending Entry: {len(pending_trades)}")
    print(f"  • Completed: {len(completed_trades)}")
    
    trades_with_entry = [t for t in trades if 'our_entry_price' in t]
    if trades_with_entry:
        costs = [t.get('delay_cost_percent', 0) for t in trades_with_entry]
        avg_cost = sum(costs) / len(costs)
        min_cost = min(costs)
        max_cost = max(costs)
        
        print(f"\nDelay Cost Statistics:")
        print(f"  • Average: {avg_cost:+.2%}")
        print(f"  • Minimum: {min_cost:+.2%}")
        print(f"  • Maximum: {max_cost:+.2%}")
        print(f"  • Trades analyzed: {len(trades_with_entry)}")
    
    if trades:
        latest = trades[-1]
        print(f"\nLatest Trade:")
        print(f"  • Time: {latest.get('timestamp', 'N/A')[:19]}")
        print(f"  • Whale: {latest.get('whale', 'N/A')[:16]}...")
        print(f"  • Market: {latest.get('market', 'N/A')[:40]}...")
        print(f"  • Status: {latest.get('status', 'N/A')}")
        if 'our_entry_price' in latest:
            print(f"  • Delay Cost: {latest.get('delay_cost_percent', 0):+.2%}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    check_progress()
