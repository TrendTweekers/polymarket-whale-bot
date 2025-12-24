#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manual resolution script for all open paper trades.

This script:
1. Fetches all open paper trades from database
2. Checks each trade's condition_id against Polymarket API
3. Detects resolved markets using multiple methods
4. Updates database with resolution status, PnL, win/loss
5. Provides detailed logging and statistics

Usage:
    python scripts/resolve_paper_trades.py [--dry-run] [--limit N] [--verbose]
"""

import sys
import os
import asyncio
import aiohttp
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env", override=True)
except Exception:
    pass

from src.polymarket.storage import SignalStore
from src.polymarket.scraper import HEADERS

# Try to import UMA resolver
try:
    from src.polymarket.uma_resolver import check_uma_resolution
    UMA_AVAILABLE = True
except ImportError:
    UMA_AVAILABLE = False
    check_uma_resolution = None

GAMMA_BASE = "https://gamma-api.polymarket.com"
logger = None  # Will be set up if needed


async def fetch_market_data(session: aiohttp.ClientSession, condition_id: str) -> Optional[Dict]:
    """Fetch market data from Polymarket API with detailed error handling."""
    url = f"{GAMMA_BASE}/markets?conditionId={condition_id}"
    
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return {"error": f"HTTP {resp.status}", "status": resp.status}
            
            data = await resp.json()
            
            # Handle different response formats
            markets = []
            if isinstance(data, list):
                markets = data
            elif isinstance(data, dict):
                if "markets" in data and isinstance(data["markets"], list):
                    markets = data["markets"]
                elif "value" in data and isinstance(data["value"], list):
                    markets = data["value"]
                elif "id" in data:
                    markets = [data]
                else:
                    # Try to find market data in nested structures
                    for key in ["data", "result", "items"]:
                        if key in data and isinstance(data[key], list):
                            markets = data[key]
                            break
            
            if not markets:
                return {"error": "No market data in response", "raw_data": str(data)[:200]}
            
            market = markets[0]
            return {"market": market, "status": "success"}
            
    except asyncio.TimeoutError:
        return {"error": "Timeout", "status": "timeout"}
    except Exception as e:
        return {"error": str(e), "status": "exception"}


def check_resolution_status(market_data: Dict) -> Tuple[bool, Optional[int], Optional[float], str]:
    """
    Check if market is resolved and return details.
    
    Returns:
        (is_resolved, winning_outcome_index, resolved_price, reason)
    """
    if "error" in market_data:
        return False, None, None, f"API error: {market_data['error']}"
    
    market = market_data.get("market", {})
    
    # Method 1: Check active flag
    active = market.get("active")
    if active is False:
        # Market is closed - check for resolution
        resolved_flag = market.get("resolved", False)
        resolution = market.get("resolution")
        resolved_outcome_index = market.get("resolvedOutcomeIndex")
        
        if resolved_flag or resolution or resolved_outcome_index is not None:
            # Try to get winning outcome
            winning_idx = None
            if resolution and isinstance(resolution, dict):
                winning_idx = resolution.get("outcome") or resolution.get("outcomeIndex")
            elif resolved_outcome_index is not None:
                winning_idx = resolved_outcome_index
            elif "outcomes" in market:
                outcomes = market.get("outcomes", [])
                for idx, outcome in enumerate(outcomes):
                    if isinstance(outcome, dict):
                        if outcome.get("resolved") or outcome.get("winning"):
                            winning_idx = idx
                            break
                    elif isinstance(outcome, str):
                        # Sometimes outcomes are just strings
                        continue
            
            if winning_idx is not None:
                return True, int(winning_idx), 1.0, "resolved_via_active_flag"
    
    # Method 2: Check resolved flag directly
    resolved_flag = market.get("resolved", False)
    if resolved_flag:
        resolved_outcome_index = market.get("resolvedOutcomeIndex")
        resolution = market.get("resolution")
        
        winning_idx = None
        if resolved_outcome_index is not None:
            winning_idx = resolved_outcome_index
        elif resolution and isinstance(resolution, dict):
            winning_idx = resolution.get("outcome") or resolution.get("outcomeIndex")
        
        if winning_idx is not None:
            return True, int(winning_idx), 1.0, "resolved_via_flag"
    
    # Method 3: Check resolution object
    resolution = market.get("resolution")
    if resolution and isinstance(resolution, dict):
        winning_idx = resolution.get("outcome") or resolution.get("outcomeIndex")
        if winning_idx is not None:
            return True, int(winning_idx), 1.0, "resolved_via_resolution_object"
    
    # Method 4: Check outcomes array for resolved/winning flags
    if "outcomes" in market:
        outcomes = market.get("outcomes", [])
        for idx, outcome in enumerate(outcomes):
            if isinstance(outcome, dict):
                if outcome.get("resolved") or outcome.get("winning"):
                    return True, idx, 1.0, "resolved_via_outcomes_array"
    
    # Market is still active
    active_str = "active" if active else "inactive"
    return False, None, None, f"market_still_{active_str}"


def calculate_pnl(stake_usd: float, entry_price: float, won: bool, resolved_price: float = None) -> float:
    """Calculate PnL for a resolved trade."""
    if won and entry_price and entry_price > 0:
        if resolved_price is not None:
            # Use resolved price if provided
            return stake_usd * (resolved_price - entry_price) / entry_price
        else:
            # Binary payout: +stake_usd * ((1/entry_price) - 1)
            return stake_usd * ((1.0 / entry_price) - 1.0)
    else:
        # Lost - lose the stake
        return -stake_usd


async def resolve_trade(session: aiohttp.ClientSession, signal_store: SignalStore, 
                       trade: Dict, dry_run: bool = False, verbose: bool = False) -> Tuple[bool, str]:
    """
    Resolve a single trade.
    
    Returns:
        (success, message)
    """
    trade_id = trade.get("id")
    event_id = trade.get("event_id") or trade.get("condition_id")
    market_name = trade.get("market", "Unknown")
    outcome_index = trade.get("outcome_index")
    stake_usd = trade.get("stake_usd", 0.0)
    entry_price = trade.get("entry_price", 0.0)
    
    if not event_id:
        return False, "Missing event_id/condition_id"
    
    if verbose:
        print(f"\n{'='*80}")
        print(f"Trade ID {trade_id}: {market_name[:70]}")
        print(f"  Condition ID: {event_id[:66]}...")
        print(f"  Outcome Index: {outcome_index}")
        print(f"  Entry Price: {entry_price:.4f}")
        print(f"  Stake: ${stake_usd:.2f} USD")
    
    # Fetch market data first (needed for both UMA and API methods)
    market_data = await fetch_market_data(session, event_id)
    
    # Extract market metadata for UMA
    # Strategy: Prefer stored market_question from database, then API, then database name
    market_title = trade.get("market_question") or market_name  # Prefer stored question
    question_id = None
    end_date_iso = None
    
    if "market" in market_data:
        market = market_data["market"]
        api_title = market.get("title") or market.get("question")
        api_description = market.get("description", "")
        
        # Check if API returned wrong market (common issue - API returns old Biden market)
        # If API title contains "Biden" or "Coronavirus" or "2020", it's likely wrong
        api_looks_wrong = (
            api_title and (
                "biden" in api_title.lower() or 
                "coronavirus" in api_title.lower() or 
                "2020" in str(market.get("endDate", ""))
            )
        )
        
        # If API looks wrong, reject it completely and use stored question or database name
        if api_looks_wrong:
            if verbose:
                print(f"  ⚠️  Warning: API returned wrong market (Biden/2020), using stored question/database name instead")
            # Don't use API data at all - stick with stored question or database name
        elif api_title and not api_looks_wrong:
            # API title looks valid - use it (usually more complete)
            market_title = api_title
            # Also try description if available and longer
            if api_description and len(api_description) > len(api_title):
                # Description often has full question text - use first sentence
                desc_first_sentence = api_description.split('.')[0]
                if len(desc_first_sentence) > len(api_title):
                    market_title = desc_first_sentence
        
        question_id = market.get("questionId") or market.get("question_id")
        end_date_iso = market.get("endDateIso") or market.get("endDate") or market.get("end_date")
    
    # Try UMA on-chain resolution first
    uma_resolved = False
    if UMA_AVAILABLE and check_uma_resolution:
        try:
            if verbose:
                print(f"  🔗 Checking UMA on-chain resolution...")
                if market_title:
                    print(f"     Market Title: {market_title[:60]}...")
                if end_date_iso:
                    print(f"     End Date: {end_date_iso}")
            uma_result = check_uma_resolution(
                event_id,
                market_title=market_title,
                question_id_address=question_id,
                end_date_iso=end_date_iso
            )
            if uma_result and uma_result.get("resolved"):
                uma_resolved = True
                winning_outcome_index = uma_result.get("winning_outcome_index")
                resolved_price = uma_result.get("resolved_price", 1.0)
                if verbose:
                    print(f"  ✅ UMA RESOLUTION FOUND!")
                    print(f"  Winning Outcome Index: {winning_outcome_index}")
                    print(f"  Resolved Price: {resolved_price}")
        except Exception as e:
            if verbose:
                print(f"  ⚠️  UMA check failed: {e}")
                import traceback
                print(f"  Traceback: {traceback.format_exc()}")
    
    # If UMA didn't resolve, try API method
    if not uma_resolved:
        if "error" in market_data:
            if verbose:
                print(f"  ❌ API Error: {market_data['error']}")
            return False, f"API error: {market_data['error']}"
        
        # Check resolution status
        is_resolved, winning_outcome_index, resolved_price, reason = check_resolution_status(market_data)
    else:
        # UMA resolved it - use UMA results
        is_resolved = True
        reason = "resolved_via_uma_onchain"
    
    if verbose:
        market = market_data.get("market", {})
        print(f"  API Status: {market.get('active', 'N/A')}")
        print(f"  Resolved Flag: {market.get('resolved', 'N/A')}")
        print(f"  Resolution Check: {reason}")
    
    if not is_resolved:
        if verbose:
            print(f"  ⏳ Market not resolved yet ({reason})")
        return False, reason
    
    # Market is resolved!
    if verbose:
        print(f"  ✅ RESOLVED!")
        print(f"  Winning Outcome Index: {winning_outcome_index}")
        print(f"  Resolved Price: {resolved_price}")
    
    # Determine if we won
    won = False
    if winning_outcome_index is not None and outcome_index is not None:
        won = (int(winning_outcome_index) == int(outcome_index))
    elif outcome_index is None:
        # Can't determine win/loss without outcome_index
        if verbose:
            print(f"  ⚠️  Cannot determine win/loss: trade has no outcome_index")
        won = False  # Default to loss if we can't determine
    
    pnl_usd = calculate_pnl(stake_usd, entry_price, won, resolved_price)
    
    if verbose:
        print(f"  Result: {'🏆 WON' if won else '❌ LOST'}")
        print(f"  PnL: ${pnl_usd:+.2f} USD")
    
    if dry_run:
        if verbose:
            print(f"  [DRY RUN] Would update trade in database")
        return True, f"DRY_RUN: Would resolve as {'WON' if won else 'LOST'}"
    
    # Update database
    try:
        success = signal_store.mark_trade_resolved(
            trade_id,
            winning_outcome_index or -1,
            won,
            resolved_price or (1.0 if won else 0.0)
        )
        
        if success:
            if verbose:
                print(f"  ✅ Trade updated in database")
            return True, f"Resolved as {'WON' if won else 'LOST'}, PnL: ${pnl_usd:+.2f}"
        else:
            if verbose:
                print(f"  ❌ Failed to update database")
            return False, "Database update failed"
            
    except Exception as e:
        if verbose:
            print(f"  ❌ Exception updating database: {e}")
        return False, f"Exception: {str(e)}"


async def main():
    parser = argparse.ArgumentParser(description="Manually resolve all open paper trades")
    parser.add_argument("--dry-run", action="store_true", help="Don't update database, just check")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum number of trades to check")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output for each trade")
    parser.add_argument("--condition-id", type=str, help="Check specific condition_id only")
    args = parser.parse_args()
    
    # Initialize storage
    signal_store = SignalStore()
    
    # Get open trades
    if args.condition_id:
        all_trades = signal_store.get_open_paper_trades(limit=10000)
        open_trades = [t for t in all_trades 
                      if (t.get("event_id") == args.condition_id or 
                          t.get("condition_id") == args.condition_id)]
        if not open_trades:
            print(f"❌ No open trades found for condition_id: {args.condition_id}")
            return
    else:
        open_trades = signal_store.get_open_paper_trades(limit=args.limit)
    
    if not open_trades:
        print("✅ No open paper trades found")
        return
    
    print(f"\n🔍 Found {len(open_trades)} open paper trade(s)")
    if args.dry_run:
        print("⚠️  DRY RUN MODE - No database updates will be made")
    print("=" * 80)
    
    # Resolve trades
    async with aiohttp.ClientSession() as session:
        resolved_count = 0
        error_count = 0
        not_resolved_count = 0
        total_pnl = 0.0
        
        for i, trade in enumerate(open_trades, 1):
            if not args.verbose and i % 10 == 0:
                print(f"Checking trade {i}/{len(open_trades)}...", end='\r')
            
            success, message = await resolve_trade(session, signal_store, trade, 
                                                   args.dry_run, args.verbose)
            
            if success and "DRY_RUN" not in message and "Resolved" in message:
                resolved_count += 1
                # Extract PnL from message
                if "$" in message:
                    try:
                        pnl_str = message.split("$")[1].split()[0]
                        total_pnl += float(pnl_str)
                    except:
                        pass
            elif "error" in message.lower() or "failed" in message.lower():
                error_count += 1
            else:
                not_resolved_count += 1
            
            # Rate limiting
            await asyncio.sleep(0.1)
        
        print("\n" + "=" * 80)
        print(f"\n📊 Summary:")
        print(f"   ✅ Resolved: {resolved_count}")
        print(f"   ⏳ Not Resolved: {not_resolved_count}")
        print(f"   ❌ Errors: {error_count}")
        if resolved_count > 0:
            print(f"   💰 Total PnL: ${total_pnl:+.2f} USD")
            print(f"   📈 Average PnL: ${total_pnl/resolved_count:+.2f} USD")


if __name__ == "__main__":
    asyncio.run(main())

