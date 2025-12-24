#!/usr/bin/env python3
"""Check if markets are actually resolved in Polymarket API."""
import asyncio
import aiohttp
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.scraper import HEADERS
from src.polymarket.storage import SignalStore

GAMMA_BASE = "https://gamma-api.polymarket.com"

async def check_market_detailed(condition_id: str):
    """Check market with detailed output."""
    url = f"{GAMMA_BASE}/markets?conditionId={condition_id}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                print(f"\n{'='*80}")
                print(f"Condition ID: {condition_id}")
                print(f"HTTP Status: {resp.status}")
                
                if resp.status != 200:
                    text = await resp.text()
                    print(f"Error Response: {text[:500]}")
                    return None
                
                data = await resp.json()
                
                # Handle different formats
                markets = []
                if isinstance(data, list):
                    markets = data
                elif isinstance(data, dict):
                    if "markets" in data:
                        markets = data["markets"]
                    elif "value" in data:
                        markets = data["value"]
                    elif "id" in data:
                        markets = [data]
                
                if not markets:
                    print("❌ No markets in response")
                    print(f"Response structure: {type(data)}")
                    if isinstance(data, dict):
                        print(f"Keys: {list(data.keys())[:10]}")
                    return None
                
                market = markets[0]
                
                print(f"\nMarket Data:")
                print(f"  Title: {market.get('title', 'N/A')}")
                print(f"  Slug: {market.get('slug', 'N/A')}")
                print(f"  Active: {market.get('active', 'N/A')}")
                print(f"  Resolved: {market.get('resolved', 'N/A')}")
                print(f"  Resolved Outcome Index: {market.get('resolvedOutcomeIndex', 'N/A')}")
                print(f"  Resolution: {market.get('resolution', 'N/A')}")
                
                # Check outcomes
                outcomes = market.get('outcomes', [])
                print(f"\nOutcomes ({len(outcomes)}):")
                for idx, outcome in enumerate(outcomes):
                    if isinstance(outcome, dict):
                        print(f"  [{idx}] {outcome.get('name', 'N/A')}")
                        print(f"      resolved: {outcome.get('resolved', False)}")
                        print(f"      winning: {outcome.get('winning', False)}")
                    else:
                        print(f"  [{idx}] {outcome} (type: {type(outcome).__name__})")
                
                # Check all resolution-related fields
                print(f"\nAll resolution-related fields:")
                for key in market.keys():
                    if any(word in key.lower() for word in ['resolve', 'active', 'close', 'end', 'outcome']):
                        value = market[key]
                        if isinstance(value, (dict, list)):
                            print(f"  {key}: {type(value).__name__} (len={len(value) if hasattr(value, '__len__') else 'N/A'})")
                        else:
                            print(f"  {key}: {value}")
                
                # Determine if resolved
                active = market.get('active')
                resolved_flag = market.get('resolved', False)
                resolution = market.get('resolution')
                resolved_outcome_idx = market.get('resolvedOutcomeIndex')
                
                is_resolved = False
                reason = ""
                
                if active is False:
                    is_resolved = True
                    reason = "active=False"
                elif resolved_flag:
                    is_resolved = True
                    reason = "resolved=True"
                elif resolution:
                    is_resolved = True
                    reason = "resolution object exists"
                elif resolved_outcome_idx is not None:
                    is_resolved = True
                    reason = "resolvedOutcomeIndex set"
                else:
                    reason = "still active"
                
                print(f"\n{'='*80}")
                print(f"RESOLUTION STATUS: {'✅ RESOLVED' if is_resolved else '⏳ NOT RESOLVED'}")
                print(f"Reason: {reason}")
                if is_resolved:
                    print(f"Winning Outcome Index: {resolved_outcome_idx}")
                
                return market
                
        except Exception as e:
            print(f"❌ Exception: {e}")
            import traceback
            traceback.print_exc()
            return None

async def main():
    # Get NFL/sports trades
    store = SignalStore()
    all_trades = store.get_open_paper_trades(limit=1000)
    
    # Find sports/NFL trades
    sports_keywords = ['nfl', 'raiders', 'texans', 'basketball', 'nba', 'bulls', 'hawks']
    sports_trades = []
    for t in all_trades:
        market = t.get('market', '').lower()
        if any(kw in market for kw in sports_keywords):
            sports_trades.append(t)
    
    print(f"Found {len(sports_trades)} sports/NFL trades")
    
    # Check first 5 sports trades
    for trade in sports_trades[:5]:
        cid = trade.get('event_id') or trade.get('condition_id')
        if cid:
            await check_market_detailed(cid)
            await asyncio.sleep(1)  # Rate limit
    
    # Also check a few recent trades
    print(f"\n\n{'='*80}")
    print("Checking recent trades...")
    print(f"{'='*80}")
    
    for trade in all_trades[-5:]:
        cid = trade.get('event_id') or trade.get('condition_id')
        if cid:
            await check_market_detailed(cid)
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())

