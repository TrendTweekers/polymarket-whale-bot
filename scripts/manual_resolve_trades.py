#!/usr/bin/env python3
"""
Manual resolution script to force-resolve trades based on known outcomes.

This bypasses UMA/API checks and directly updates the database with known results.
Useful when markets haven't resolved on-chain yet but outcomes are known.
"""
import sys
import argparse
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.storage import SignalStore

# Known outcomes by condition_id (event_id) - based on real results
# Format: condition_id_prefix: {winning_outcome_index, note}
# Use first ~20 chars of condition_id for matching
KNOWN_OUTCOMES_BY_CONDITION = {
    # Raiders vs Texans - Dec 21, 2025
    "0x802a414d66f82720b3": {  # Spread: Texans (-14.5)
        "winning_outcome_index": 1,  # NO (didn't cover -14.5)
        "note": "Texans won by 2 points, didn't cover -14.5 spread"
    },
    "0x0e4ccd69c581deb1aa": {  # Raiders vs. Texans moneyline
        "winning_outcome_index": 0,  # Raiders win
        "note": "Raiders won 24-19"
    },
    # Bulls vs Hawks - Dec 21, 2025
    "0x986c255d16e062c4c9": {  # Bulls vs. Hawks
        "winning_outcome_index": 0,  # Bulls win (Bulls won 152-150)
        "note": "Bulls won 152-150"
    },
    # Bucks vs Timberwolves - Dec 22, 2025
    "0xf8d7c5239870557ee6": {  # Bucks vs. Timberwolves
        "winning_outcome_index": 1,  # Timberwolves win (assuming 0=Bucks, 1=Timberwolves)
        "note": "Timberwolves won"
    },
    # Jazz vs Nuggets - Dec 22, 2025 (verified - corrected)
    "0xd5213fb46cf57eae0f": {  # Jazz vs. Nuggets
        "winning_outcome_index": 1,  # Nuggets won 135-112
        "note": "Nuggets won 135-112"
    },
    # Raptors vs Nets - Dec 22, 2025 (verified - corrected)
    "0x92f7b97220f6ba3494": {  # Raptors vs. Nets
        "winning_outcome_index": 1,  # Nets won 96-81
        "note": "Nets won 96-81"
    },
    # Mavericks vs Pelicans - Dec 22, 2025 (verified - corrected)
    "0xee7c7b4574d76aea6e": {  # Mavericks vs. Pelicans
        "winning_outcome_index": 1,  # Pelicans won 119-113
        "note": "Pelicans won 119-113"
    },
    # Grizzlies vs Thunder - Dec 22, 2025 (verified - corrected)
    "0x3d902714b7e37063d3": {  # Grizzlies vs. Thunder
        "winning_outcome_index": 1,  # Thunder won 119-103
        "note": "Thunder won 119-103"
    },
    # Rockets vs Kings - Dec 22, 2025 (verified)
    "0x350af0373772d85da1": {  # Rockets vs. Kings
        "winning_outcome_index": 1,  # Kings won 125-124
        "note": "Kings won 125-124"
    },
    # Spurs vs Wizards - Dec 22, 2025 (verified)
    "0x70eac4e2b255c1ea8a": {  # Spurs vs. Wizards
        "winning_outcome_index": 0,  # Spurs won 124-113
        "note": "Spurs won 124-113"
    },
    "0x70eac4e2b255c1ea7a": {  # Spurs vs. Wizards (actual DB ID)
        "winning_outcome_index": 0,  # Spurs won 124-113
        "note": "Spurs won 124-113"
    },
    # Patriots vs Ravens - Dec 22, 2025 (verified)
    "0x780408b161c548a5c6": {  # Patriots vs. Ravens
        "winning_outcome_index": 0,  # Patriots won 28-24
        "note": "Patriots won 28-24"
    },
    # Steelers vs Lions - Dec 22, 2025 (verified)
    "0x913b67f7c8b370247f": {  # Steelers vs. Lions
        "winning_outcome_index": 0,  # Steelers won 29-24
        "note": "Steelers won 29-24"
    },
    # Rockets vs Kings - Dec 22, 2025 (verified)
    "0x350af0373772d85da1": {  # Rockets vs. Kings
        "winning_outcome_index": 1,  # Kings won 125-124
        "note": "Kings won 125-124"
    },
    # Vikings vs Giants - Dec 22, 2025
    "0x27541f1ebf40749d3a": {  # Vikings vs. Giants
        "winning_outcome_index": 1,  # Giants won (needs verification)
        "note": "Giants won"
    },
    # Bills vs Browns - Dec 22, 2025
    "0x88a1edad9dc7b77efb8f": {  # Bills vs. Browns
        "winning_outcome_index": 0,  # Bills won (needs verification)
        "note": "Bills won"
    },
    # Raptors vs Nets 1H Moneyline - Dec 22, 2025
    "0x0ffffc18501f37a25f": {  # Raptors vs. Nets: 1H Moneyline
        "winning_outcome_index": 1,  # Nets won 1H (needs verification)
        "note": "Nets won first half"
    },
    # Rockets vs. Kings: O/U 226.5 - Dec 22, 2025 (verified)
    "0xb460a6685f655830ff": {  # Rockets vs. Kings: O/U 226.5
        "winning_outcome_index": 0,  # Over (Kings 125-124 = 249 > 226.5)
        "note": "Rockets vs Kings total 249, Over 226.5"
    },
    # Raptors vs. Nets: O/U 224.5 - Dec 22, 2025 (verified)
    "0xcbf10bc06cbcb828f4": {  # Raptors vs. Nets: O/U 224.5
        "winning_outcome_index": 1,  # Under (Nets 96-81 = 177 < 224.5)
        "note": "Raptors vs Nets total 177, Under 224.5"
    },
    # Steelers vs. Lions: O/U 50.5 - Dec 22, 2025 (verified)
    "0x81191be936bcbcb6d1": {  # Steelers vs. Lions: O/U 50.5
        "winning_outcome_index": 0,  # Over (Steelers 29-24 = 53 > 50.5)
        "note": "Steelers vs Lions total 53, Over 50.5"
    },
    # Steelers vs. Lions: O/U 51.5 - Dec 22, 2025 (verified)
    "0xd2d8bfbe29e13b13c9": {  # Steelers vs. Lions: O/U 51.5
        "winning_outcome_index": 0,  # Over (Steelers 29-24 = 53 > 51.5)
        "note": "Steelers vs Lions total 53, Over 51.5"
    },
    # Raptors vs. Nets: 1H Moneyline - Dec 22, 2025 (already added above)
    # Spread: Broncos (-3.5) - Dec 22, 2025 (verified - corrected)
    "0xe58ab3588dc5bd9176": {  # Spread: Broncos (-3.5)
        "winning_outcome_index": 1,  # Broncos won by 1 < 3.5, didn't cover
        "note": "Broncos won by 1 point, didn't cover -3.5 spread"
    },
    # 1H Spread: Spurs (-9.5) - Dec 22, 2025 (verified - corrected)
    "0x8183b9c32986f6a726": {  # 1H Spread: Spurs (-9.5)
        "winning_outcome_index": 1,  # Spurs 1H won by 7 < 9.5, didn't cover
        "note": "Spurs 1H won by 7 points, didn't cover -9.5 spread"
    },
    
    # Removed false-positive "1920" total entries - these were parsing errors
    # Removed all false-positive "960-960" entries - these were parsing errors
    # These markets need manual verification or better web search results

    # Remove suspicious "0-0" results - these are likely parsing errors
    # "0x6015ddbfd675efa3a2": {  # LoL: Bilibili Gaming vs LNG Esports - Game 2 Winner
    #     "winning_outcome_index": 1,
    #     "note": "LNG Esports - Game 2 Winner won 0-0"  # Suspicious - removed
    # },
    # "0xa14f019006a8aa63ec": {  # LoL: LGD Gaming vs Invictus Gaming (BO3)
    #     "winning_outcome_index": 1,
    #     "note": "Invictus Gaming (BO3) won 0-0"  # Suspicious - removed
    # },
# Add more condition_ids here as outcomes become known
    # Example format:
    # "0x1234567890abcdef12": {
    #     "winning_outcome_index": 0,  # or 1
    #     "note": "Description of outcome"
    # },
}

# Legacy trade_id-based outcomes (for backward compatibility)
KNOWN_OUTCOMES = {
    241: {
        "resolved": True,
        "winning_outcome_index": 1,
        "won": False,
        "resolved_price": 1.0,
        "note": "Texans won by 2 points, didn't cover -14.5 spread"
    },
    243: {
        "resolved": True,
        "winning_outcome_index": 0,
        "won": None,
        "resolved_price": 1.0,
        "note": "Raiders won 24-19"
    },
}

def calculate_pnl(stake_usd: float, entry_price: float, won: bool, resolved_price: float = 1.0) -> float:
    """Calculate PnL for a resolved trade."""
    if won:
        # Won: profit = stake * (resolved_price - entry_price) / entry_price
        if entry_price > 0:
            return stake_usd * (resolved_price - entry_price) / entry_price
        return stake_usd
    else:
        # Lost: lose the stake
        return -stake_usd

def find_outcome_for_trade(trade: Dict) -> Optional[Dict]:
    """Find known outcome for a trade by condition_id or trade_id."""
    event_id = trade.get("event_id") or trade.get("condition_id", "")
    
    # Try condition_id match first (more reliable)
    if event_id:
        for cond_prefix, outcome in KNOWN_OUTCOMES_BY_CONDITION.items():
            if event_id.startswith(cond_prefix):
                return {
                    "resolved": True,
                    "winning_outcome_index": outcome["winning_outcome_index"],
                    "won": None,  # Will be determined by position
                    "resolved_price": 1.0,
                    "note": outcome.get("note", "")
                }
    
    # Fall back to trade_id match
    trade_id = trade.get("id")
    if trade_id and trade_id in KNOWN_OUTCOMES:
        return KNOWN_OUTCOMES[trade_id]
    
    return None

def resolve_trade_manual(signal_store: SignalStore, trade_id: int, outcome: Dict, dry_run: bool = False) -> bool:
    """Manually resolve a trade with known outcome."""
    # Get trade details
    conn = signal_store._get_connection()
    conn.row_factory = lambda cursor, row: {
        col[0]: row[idx] for idx, col in enumerate(cursor.description)
    }
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pt.*, s.market
        FROM paper_trades pt
        LEFT JOIN signals s ON pt.signal_id = s.id
        WHERE pt.id = ?
    """, (trade_id,))
    trade = cursor.fetchone()
    conn.close()
    
    if not trade:
        print(f"❌ Trade ID {trade_id} not found")
        return False
    
    if trade["status"] != "OPEN":
        print(f"⚠️  Trade ID {trade_id} is already {trade['status']}")
        return False
    
    # Determine win/loss based on outcome_index
    trade_outcome_index = trade.get("outcome_index")
    winning_outcome_index = outcome["winning_outcome_index"]
    outcome_name = (trade.get("outcome_name") or "").lower()
    side = (trade.get("side") or "").upper()
    market_name = (trade.get("market") or "").lower()
    
    # Determine position from outcome_name or market name
    # Trade 241: "Spread: Texans (-14.5)" - outcome_name likely "Texans" or "YES"
    # Trade 243: "Raiders vs. Texans" - outcome_name likely "Raiders" or "Texans"
    
    if trade_outcome_index is not None:
        # Has explicit outcome_index
        won = (trade_outcome_index == winning_outcome_index)
    else:
        # Infer from outcome_name
        if "spread" in market_name:
            # Spread market: YES = index 0 (cover), NO = index 1 (don't cover)
            # Trade 241: Texans didn't cover (-14.5), so winning_outcome_index = 1 (NO)
            # If outcome_name contains "texans" or "yes", position is YES (index 0)
            if "texans" in outcome_name or "yes" in outcome_name or side == "BUY":
                won = (winning_outcome_index == 0)  # YES position wins if index 0
            else:
                won = (winning_outcome_index == 1)  # NO position wins if index 1
        else:
            # Moneyline market: YES = index 0 (team wins), NO = index 1 (team loses)
            # Handle SELL vs BUY positions
            # SELL means betting AGAINST the outcome_name team (so FOR the other team)
            # BUY means betting FOR the outcome_name team
            
            # Determine which team is in outcome_name
            market_lower = market_name.lower()
            if "bulls" in outcome_name.lower():
                # Position is on Bulls (if BUY) or against Bulls (if SELL)
                if side == "SELL":
                    # Betting AGAINST Bulls = FOR Hawks
                    # Bulls won (index 0), so Hawks lost (index 1)
                    won = (winning_outcome_index == 1)  # Hawks losing = SELL Bulls wins
                else:
                    # Betting FOR Bulls
                    won = (winning_outcome_index == 0)  # Bulls winning = BUY Bulls wins
            elif "hawks" in outcome_name.lower():
                # Position is on Hawks (if BUY) or against Hawks (if SELL)
                if side == "SELL":
                    # Betting AGAINST Hawks = FOR Bulls
                    # Bulls won (index 0), so Hawks lost (index 1)
                    won = (winning_outcome_index == 0)  # Bulls winning = SELL Hawks wins
                else:
                    # Betting FOR Hawks
                    won = (winning_outcome_index == 1)  # Hawks winning = BUY Hawks wins
            elif "bucks" in outcome_name.lower():
                # Position is on Bucks
                if side == "SELL":
                    # Betting AGAINST Bucks = FOR Timberwolves
                    won = (winning_outcome_index == 1)  # Timberwolves winning = SELL Bucks wins
                else:
                    # Betting FOR Bucks
                    won = (winning_outcome_index == 0)  # Bucks winning = BUY Bucks wins
            elif "timberwolves" in outcome_name.lower() or "wolves" in outcome_name.lower():
                # Position is on Timberwolves
                if side == "SELL":
                    # Betting AGAINST Timberwolves = FOR Bucks
                    won = (winning_outcome_index == 0)  # Bucks winning = SELL Timberwolves wins
                else:
                    # Betting FOR Timberwolves
                    won = (winning_outcome_index == 1)  # Timberwolves winning = BUY Timberwolves wins
            elif "raiders" in outcome_name.lower():
                # Position is on Raiders
                if side == "SELL":
                    won = (winning_outcome_index == 1)  # Betting AGAINST Raiders
                else:
                    won = (winning_outcome_index == 0)  # Betting FOR Raiders
            elif "texans" in outcome_name.lower():
                # Position is on Texans
                if side == "SELL":
                    won = (winning_outcome_index == 0)  # Betting AGAINST Texans
                else:
                    won = (winning_outcome_index == 1)  # Betting FOR Texans
            else:
                # Default: assume BUY position, outcome_name is the winning team
                # If outcome_name matches first team in market, index 0; else index 1
                teams = [t.strip() for t in market_lower.split(" vs ")]
                if teams and outcome_name.lower() in teams[0]:
                    won = (winning_outcome_index == 0)
                elif len(teams) > 1 and outcome_name.lower() in teams[1]:
                    won = (winning_outcome_index == 1)
                else:
                    # Fallback: assume YES position
                    won = (winning_outcome_index == 0)
    
    # Override if explicitly set in outcome dict
    if outcome.get("won") is not None:
        won = outcome["won"]
    
    # Calculate PnL
    stake_usd = trade.get("stake_usd", 0.0)
    entry_price = trade.get("entry_price", 0.0)
    resolved_price = outcome.get("resolved_price", 1.0)
    pnl = calculate_pnl(stake_usd, entry_price, won, resolved_price)
    
    # Display info
    print(f"\n{'='*80}")
    print(f"Trade ID: {trade_id}")
    print(f"Market: {trade.get('market', 'Unknown')}")
    print(f"Outcome Index: {trade_outcome_index}")
    print(f"Winning Outcome Index: {winning_outcome_index}")
    win_loss = "WIN" if won else "LOSS"
    print(f"Result: {win_loss}")
    print(f"PnL: ${pnl:.2f} USD")
    print(f"Note: {outcome.get('note', '')}")
    
    if dry_run:
        print(f"\n[DRY RUN] Would update trade {trade_id}")
        return True
    
    # Update database
    try:
        conn = signal_store._get_connection()
        cursor = conn.cursor()
        resolved_at = datetime.utcnow().isoformat()
        
        cursor.execute("""
            UPDATE paper_trades
            SET status = 'RESOLVED',
                resolved_at = ?,
                won = ?,
                pnl_usd = ?,
                resolved_outcome_index = ?
            WHERE id = ?
        """, (resolved_at, won, pnl, winning_outcome_index, trade_id))
        
        conn.commit()
        conn.close()
        
        print(f"[OK] Successfully resolved trade {trade_id}")
        return True
    except Exception as e:
        print(f"❌ Failed to update database: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Manually resolve trades with known outcomes"
    )
    parser.add_argument("--trade-id", type=int, help="Specific trade ID to resolve")
    parser.add_argument("--all-known", action="store_true", help="Resolve all trades with known outcomes")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without updating")
    parser.add_argument("--list-known", action="store_true", help="List all known outcomes")
    
    args = parser.parse_args()
    
    if args.list_known:
        print("Known Outcomes by Condition ID:")
        print("=" * 80)
        for cond_id, outcome in KNOWN_OUTCOMES_BY_CONDITION.items():
            print(f"\nCondition ID: {cond_id}...")
            print(f"  Winning Outcome Index: {outcome['winning_outcome_index']}")
            print(f"  Note: {outcome.get('note', '')}")
        
        print("\n\nKnown Outcomes by Trade ID (Legacy):")
        print("=" * 80)
        for tid, outcome in KNOWN_OUTCOMES.items():
            print(f"\nTrade ID {tid}:")
            print(f"  Resolved: {outcome['resolved']}")
            print(f"  Winning Outcome Index: {outcome['winning_outcome_index']}")
            print(f"  Won: {outcome.get('won', 'Auto-determined')}")
            print(f"  Note: {outcome.get('note', '')}")
        return
    
    signal_store = SignalStore()
    
    if args.trade_id:
        # Get trade to find outcome
        conn = signal_store._get_connection()
        conn.row_factory = lambda cursor, row: {
            col[0]: row[idx] for idx, col in enumerate(cursor.description)
        }
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM paper_trades WHERE id = ?", (args.trade_id,))
        trade = cursor.fetchone()
        conn.close()
        
        if not trade:
            print(f"❌ Trade ID {args.trade_id} not found")
            return
        
        outcome = find_outcome_for_trade(trade)
        if not outcome:
            print(f"❌ No known outcome for trade ID {args.trade_id}")
            print(f"Available condition_id prefixes: {list(KNOWN_OUTCOMES_BY_CONDITION.keys())}")
            print(f"Available trade IDs: {list(KNOWN_OUTCOMES.keys())}")
            return
        
        resolve_trade_manual(signal_store, args.trade_id, outcome, dry_run=args.dry_run)
    elif args.all_known:
        # Find all open trades and check for known outcomes
        conn = signal_store._get_connection()
        conn.row_factory = lambda cursor, row: {
            col[0]: row[idx] for idx, col in enumerate(cursor.description)
        }
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM paper_trades WHERE status = 'OPEN'")
        open_trades = cursor.fetchall()
        conn.close()
        
        print(f"Checking {len(open_trades)} open trades for known outcomes...")
        resolved_count = 0
        matched_trades = []
        
        for trade in open_trades:
            outcome = find_outcome_for_trade(trade)
            if outcome:
                matched_trades.append((trade["id"], outcome))
        
        print(f"Found {len(matched_trades)} trades with known outcomes")
        
        for tid, outcome in matched_trades:
            if resolve_trade_manual(signal_store, tid, outcome, dry_run=args.dry_run):
                resolved_count += 1
        
        print(f"\n{'='*80}")
        print(f"Summary: {resolved_count}/{len(matched_trades)} trades resolved")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

