#!/usr/bin/env python3
"""Test specific condition_ids to see if they're resolved in Polymarket."""
import asyncio
import aiohttp
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.scraper import HEADERS
from src.polymarket.resolver import check_market_resolution

GAMMA_BASE = "https://gamma-api.polymarket.com"

async def test_condition_id(condition_id: str):
    """Test a specific condition_id."""
    print(f"\n{'='*80}")
    print(f"Testing Condition ID: {condition_id}")
    print(f"{'='*80}")
    
    async with aiohttp.ClientSession() as session:
        # First, fetch raw market data
        url = f"{GAMMA_BASE}/markets?conditionId={condition_id}"
        try:
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"API Status: {resp.status}")
                if resp.status != 200:
                    print(f"❌ API Error: {resp.status}")
                    text = await resp.text()
                    print(f"Response: {text[:200]}")
                    return
                
                data = await resp.json()
                
                # Handle different response formats
                market = None
                if isinstance(data, list) and len(data) > 0:
                    market = data[0]
                elif isinstance(data, dict) and "markets" in data and isinstance(data["markets"], list) and data["markets"]:
                    market = data["markets"][0]
                elif isinstance(data, dict) and "id" in data:
                    market = data
                
                if not market:
                    print("❌ No market data returned")
                    return
                
                print(f"\nMarket Title: {market.get('title', 'N/A')}")
                print(f"Market Slug: {market.get('slug', 'N/A')}")
                print(f"Active: {market.get('active', 'N/A')}")
                print(f"Resolved: {market.get('resolved', 'N/A')}")
                print(f"Resolution: {market.get('resolution', 'N/A')}")
                print(f"Resolved Outcome Index: {market.get('resolvedOutcomeIndex', 'N/A')}")
                
                # Check outcomes
                outcomes = market.get('outcomes', [])
                print(f"\nOutcomes ({len(outcomes)}):")
                for idx, outcome in enumerate(outcomes):
                    if isinstance(outcome, dict):
                        print(f"  [{idx}] {outcome.get('name', 'N/A')} - resolved: {outcome.get('resolved', False)}, winning: {outcome.get('winning', False)}")
                    else:
                        print(f"  [{idx}] {outcome} (type: {type(outcome).__name__})")
                
                # Print full market data for debugging
                print(f"\nFull market keys: {list(market.keys())[:20]}")
                if 'resolution' in market:
                    print(f"Resolution object: {market['resolution']}")
                
                # Now test our resolver function
                print(f"\n{'='*80}")
                print("Testing check_market_resolution() function:")
                print(f"{'='*80}")
                resolution = await check_market_resolution(session, condition_id)
                
                if resolution is None:
                    print("❌ check_market_resolution() returned None")
                else:
                    print(f"✅ Resolved: {resolution.get('resolved', False)}")
                    print(f"   Winning Outcome Index: {resolution.get('winning_outcome_index', 'N/A')}")
                    print(f"   Resolved Price: {resolution.get('resolved_price', 'N/A')}")
                    print(f"   Resolution Time: {resolution.get('resolution_time', 'N/A')}")
                
        except Exception as e:
            print(f"❌ Exception: {e}")
            import traceback
            traceback.print_exc()

async def main():
    # Test the specific condition_ids mentioned
    test_ids = [
        "0x986c255d16e062c4c9",  # NBA Bulls vs Hawks (partial)
        "0x0e4ccd69c581deb1aad6f587083a4800d458d6a12f3d202418a53e0c40b18c5a",  # Raiders vs Texans (full)
    ]
    
    # Also test a few from our database
    from src.polymarket.storage import SignalStore
    store = SignalStore()
    nfl_trades = [t for t in store.get_open_paper_trades(limit=300) 
                  if 'raiders' in t.get('market', '').lower() or 'texans' in t.get('market', '').lower()]
    
    for trade in nfl_trades[:3]:
        cid = trade.get('event_id') or trade.get('condition_id')
        if cid:
            test_ids.append(cid)
    
    # Remove duplicates
    test_ids = list(set(test_ids))
    
    for cid in test_ids:
        await test_condition_id(cid)
        await asyncio.sleep(1)  # Rate limit

if __name__ == "__main__":
    asyncio.run(main())

