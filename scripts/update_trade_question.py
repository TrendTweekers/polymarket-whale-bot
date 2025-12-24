#!/usr/bin/env python3
"""Manually update market_question for specific trades."""
import sys
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.storage import SignalStore

# Pre-defined templates for known trades
TEMPLATES = {
    241: "Will the Houston Texans win by more than 14.5 points against the Las Vegas Raiders on December 21, 2025? This market will resolve to 'Yes' if the Houston Texans win by more than 14.5 points according to the official NFL score at the end of regulation, including overtime if necessary. Otherwise, it will resolve to 'No'. If the game is cancelled or postponed, the market will resolve to 'No'.",
    243: "Will the Las Vegas Raiders win against the Houston Texans on December 21, 2025? This market will resolve to 'Yes' if the Las Vegas Raiders win the game according to the official NFL score at the end of regulation, including overtime if necessary. Otherwise, it will resolve to 'No'. If the game is cancelled or postponed, the market will resolve to 'No'.",
}

def update_trade_question(trade_id: int, question: str, dry_run: bool = False):
    """Update market_question for a specific trade."""
    store = SignalStore()
    
    # Verify trade exists
    conn = store._get_connection()
    conn.row_factory = lambda cursor, row: {
        col[0]: row[idx] for idx, col in enumerate(cursor.description)
    }
    cursor = conn.cursor()
    cursor.execute("SELECT id, market_question FROM paper_trades WHERE id = ?", (trade_id,))
    trade = cursor.fetchone()
    conn.close()
    
    if not trade:
        print(f"❌ Trade ID {trade_id} not found")
        return False
    
    print(f"Trade ID: {trade_id}")
    print(f"Current question: {trade['market_question'][:100] if trade['market_question'] else 'NULL'}...")
    print(f"New question: {question[:100]}...")
    
    if dry_run:
        print(f"[DRY RUN] Would update trade {trade_id}")
        return True
    
    # Update database
    try:
        conn = store._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE paper_trades
            SET market_question = ?
            WHERE id = ?
        """, (question, trade_id))
        conn.commit()
        conn.close()
        
        print(f"✅ Updated trade {trade_id} successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to update: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Manually update market_question for specific trades")
    parser.add_argument("--trade-id", type=int, help="Trade ID to update")
    parser.add_argument("--question", type=str, help="Full question text")
    parser.add_argument("--template", action="store_true", help="Use pre-defined template for trade ID")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without updating")
    parser.add_argument("--list-templates", action="store_true", help="List available templates")
    
    args = parser.parse_args()
    
    if args.list_templates:
        print("Available templates:")
        for tid, question in TEMPLATES.items():
            print(f"\nTrade ID {tid}:")
            print(f"  {question[:150]}...")
        return
    
    if not args.trade_id:
        print("❌ --trade-id is required")
        parser.print_help()
        return
    
    if args.template:
        if args.trade_id not in TEMPLATES:
            print(f"❌ No template found for trade ID {args.trade_id}")
            print(f"Available template IDs: {list(TEMPLATES.keys())}")
            return
        question = TEMPLATES[args.trade_id]
    elif args.question:
        question = args.question
    else:
        print("❌ Either --question or --template is required")
        parser.print_help()
        return
    
    update_trade_question(args.trade_id, question, dry_run=args.dry_run)

if __name__ == "__main__":
    main()

