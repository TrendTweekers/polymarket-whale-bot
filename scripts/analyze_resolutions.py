#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone script to analyze and manually resolve paper trades.

This script:
1. Queries the database for open paper trades
2. Checks Polymarket API for market resolutions
3. Auto-updates trades if resolved
4. Calculates PnL and win rate statistics
5. Provides manual resolution capability

Usage:
    python scripts/analyze_resolutions.py [--limit N] [--auto-update] [--condition-id ID]
"""

import sys
import os
import asyncio
import aiohttp
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Fix Windows console encoding for emoji
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
from src.polymarket.resolver import check_market_resolution
from src.polymarket.scraper import HEADERS

GAMMA_BASE = "https://gamma-api.polymarket.com"


async def fetch_market_by_condition(session: aiohttp.ClientSession, condition_id: str) -> Optional[Dict]:
    """Fetch market data from Polymarket API."""
    try:
        url = f"{GAMMA_BASE}/markets?conditionId={condition_id}"
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                print(f"  ❌ API returned status {resp.status}")
                return None
            
            data = await resp.json()
            
            # Handle different response formats
            market = None
            if isinstance(data, list) and len(data) > 0:
                market = data[0]
            elif isinstance(data, dict) and "markets" in data and isinstance(data["markets"], list) and data["markets"]:
                market = data["markets"][0]
            elif isinstance(data, dict) and "id" in data:
                market = data
            
            return market
    except Exception as e:
        print(f"  ❌ Error fetching market: {e}")
        return None


def calculate_pnl(stake_usd: float, entry_price: float, won: bool, resolved_price: float = None) -> float:
    """Calculate PnL for a resolved trade."""
    if won and entry_price and entry_price > 0:
        if resolved_price is not None:
            return stake_usd * (resolved_price - entry_price) / entry_price
        else:
            # Binary payout: +stake_usd * ((1/entry_price) - 1)
            return stake_usd * ((1.0 / entry_price) - 1.0)
    else:
        # Lost - lose the stake
        return -stake_usd


async def analyze_trade(session: aiohttp.ClientSession, signal_store: SignalStore, trade: Dict, auto_update: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Analyze a single trade and optionally update it.
    
    Returns:
        (is_resolved, error_message)
    """
    trade_id = trade.get("id")
    event_id = trade.get("event_id") or trade.get("condition_id")
    market_name = trade.get("market", "Unknown")
    outcome_index = trade.get("outcome_index")
    stake_usd = trade.get("stake_usd", 0.0)
    entry_price = trade.get("entry_price", 0.0)
    
    if not event_id:
        return False, "Missing event_id/condition_id"
    
    print(f"\n📊 Trade ID {trade_id}: {market_name[:60]}")
    print(f"   Condition ID: {event_id[:42]}...")
    print(f"   Outcome Index: {outcome_index}")
    print(f"   Entry Price: {entry_price:.4f}")
    print(f"   Stake: ${stake_usd:.2f} USD")
    
    # Check resolution
    resolution = await check_market_resolution(session, event_id)
    
    if resolution is None:
        return False, "Failed to fetch market data from API"
    
    if not resolution.get("resolved"):
        active = resolution.get("market_data", {}).get("active", True)
        print(f"   Status: ⏳ NOT RESOLVED (active={active})")
        return False, None
    
    # Market is resolved
    winning_outcome_index = resolution.get("winning_outcome_index")
    resolved_price = resolution.get("resolved_price", 0.0)
    won = (winning_outcome_index is not None and 
           outcome_index is not None and
           winning_outcome_index == outcome_index)
    
    pnl_usd = calculate_pnl(stake_usd, entry_price, won, resolved_price)
    
    print(f"   Status: ✅ RESOLVED")
    print(f"   Winning Outcome Index: {winning_outcome_index}")
    print(f"   Resolved Price: {resolved_price:.4f}")
    print(f"   Result: {'🏆 WON' if won else '❌ LOST'}")
    print(f"   PnL: ${pnl_usd:+.2f} USD")
    
    if auto_update:
        try:
            success = signal_store.mark_trade_resolved(
                trade_id,
                winning_outcome_index or -1,
                won,
                resolved_price
            )
            if success:
                print(f"   ✅ Trade updated in database")
                return True, None
            else:
                return False, "Failed to update trade in database"
        except Exception as e:
            return False, f"Exception updating trade: {str(e)}"
    else:
        print(f"   ⚠️  Use --auto-update to update this trade")
        return True, None


async def main():
    parser = argparse.ArgumentParser(description="Analyze and resolve paper trades")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of trades to check")
    parser.add_argument("--auto-update", action="store_true", help="Automatically update resolved trades")
    parser.add_argument("--condition-id", type=str, help="Check specific condition_id only")
    parser.add_argument("--stats-only", action="store_true", help="Show statistics only, don't check individual trades")
    args = parser.parse_args()
    
    # Initialize storage
    signal_store = SignalStore()
    
    # Get open trades
    if args.condition_id:
        # Filter by condition_id if specified
        all_trades = signal_store.get_open_paper_trades(limit=1000)
        open_trades = [t for t in all_trades if (t.get("event_id") == args.condition_id or 
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
    print("=" * 80)
    
    if args.stats_only:
        # Show statistics
        total_stake = sum(t.get("stake_usd", 0.0) for t in open_trades)
        avg_stake = total_stake / len(open_trades) if open_trades else 0.0
        
        print(f"\n📈 Statistics:")
        print(f"   Total Open Trades: {len(open_trades)}")
        print(f"   Total Stake: ${total_stake:.2f} USD")
        print(f"   Average Stake: ${avg_stake:.2f} USD")
        
        # Group by market
        markets = {}
        for trade in open_trades:
            market = trade.get("market", "Unknown")
            if market not in markets:
                markets[market] = []
            markets[market].append(trade)
        
        print(f"\n📊 Trades by Market ({len(markets)} unique markets):")
        for market, trades in sorted(markets.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
            print(f"   {len(trades):3d} trades: {market[:60]}")
        
        return
    
    # Check each trade
    async with aiohttp.ClientSession() as session:
        resolved_count = 0
        error_count = 0
        not_resolved_count = 0
        
        for trade in open_trades:
            is_resolved, error = await analyze_trade(session, signal_store, trade, args.auto_update)
            
            if error:
                error_count += 1
            elif is_resolved:
                resolved_count += 1
            else:
                not_resolved_count += 1
        
        print("\n" + "=" * 80)
        print(f"\n📊 Summary:")
        print(f"   ✅ Resolved: {resolved_count}")
        print(f"   ⏳ Not Resolved: {not_resolved_count}")
        print(f"   ❌ Errors: {error_count}")
        
        if resolved_count > 0 and not args.auto_update:
            print(f"\n💡 Tip: Run with --auto-update to automatically update resolved trades")


if __name__ == "__main__":
    asyncio.run(main())

