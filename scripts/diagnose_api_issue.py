#!/usr/bin/env python3
"""Diagnose API issue - test different endpoints and formats."""
import asyncio
import aiohttp
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.scraper import HEADERS
from src.polymarket.storage import SignalStore

GAMMA_BASE = "https://gamma-api.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"

async def test_endpoints(condition_id: str):
    """Test different API endpoints and formats."""
    print(f"\n{'='*80}")
    print(f"Testing Condition ID: {condition_id}")
    print(f"{'='*80}")
    
    async with aiohttp.ClientSession() as session:
        # Test 1: Gamma API with conditionId (current method)
        print("\n1. Gamma API: /markets?conditionId={id}")
        url1 = f"{GAMMA_BASE}/markets?conditionId={condition_id}"
        try:
            async with session.get(url1, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data1 = await resp.json()
                market1 = None
                if isinstance(data1, list) and data1:
                    market1 = data1[0]
                elif isinstance(data1, dict) and "markets" in data1:
                    market1 = data1["markets"][0] if data1["markets"] else None
                elif isinstance(data1, dict) and "id" in data1:
                    market1 = data1
                
                if market1:
                    print(f"   Title: {market1.get('title', 'N/A')[:60]}")
                    print(f"   Slug: {market1.get('slug', 'N/A')[:60]}")
                    print(f"   Active: {market1.get('active', 'N/A')}")
                    print(f"   Closed: {market1.get('closed', 'N/A')}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Test 2: Gamma API with condition_ids (plural)
        print("\n2. Gamma API: /markets?condition_ids={id}")
        url2 = f"{GAMMA_BASE}/markets?condition_ids={condition_id}"
        try:
            async with session.get(url2, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data2 = await resp.json()
                print(f"   Status: {resp.status}")
                print(f"   Response type: {type(data2)}")
                if isinstance(data2, dict):
                    print(f"   Keys: {list(data2.keys())[:10]}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Test 3: Data API
        print("\n3. Data API: /markets?condition_id={id}")
        url3 = f"{DATA_BASE}/markets?condition_id={condition_id}"
        try:
            async with session.get(url3, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"   Status: {resp.status}")
                if resp.status == 200:
                    data3 = await resp.json()
                    print(f"   Response type: {type(data3)}")
                    if isinstance(data3, dict):
                        print(f"   Keys: {list(data3.keys())[:10]}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # Test 4: Try searching by market slug/name instead
        print("\n4. Gamma API: Search by slug")
        # Get market name from database
        store = SignalStore()
        trades = store.get_open_paper_trades(limit=1000)
        nfl_trade = next((t for t in trades if 'raiders' in t.get('market', '').lower() or 'texans' in t.get('market', '').lower()), None)
        if nfl_trade:
            market_name = nfl_trade.get('market', '')
            print(f"   Market name: {market_name[:60]}")
            # Try searching
            url4 = f"{GAMMA_BASE}/markets?search={market_name[:30]}"
            try:
                async with session.get(url4, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    print(f"   Status: {resp.status}")
            except Exception as e:
                print(f"   Error: {e}")

async def main():
    # Test with a known NFL trade condition_id
    store = SignalStore()
    trades = store.get_open_paper_trades(limit=1000)
    nfl_trade = next((t for t in trades if 'raiders' in t.get('market', '').lower() or 'texans' in t.get('market', '').lower()), None)
    
    if nfl_trade:
        cid = nfl_trade.get('event_id') or nfl_trade.get('condition_id')
        print(f"Testing NFL trade: {nfl_trade.get('market', '')[:60]}")
        await test_endpoints(cid)
    else:
        print("No NFL trades found")

if __name__ == "__main__":
    asyncio.run(main())

