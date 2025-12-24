#!/usr/bin/env python3
"""Fetch full market title/question from Polymarket API."""
import sys
import asyncio
import aiohttp
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.scraper import HEADERS, GAMMA_BASE

async def fetch_full_market_info(condition_id: str):
    """Fetch full market information including question."""
    async with aiohttp.ClientSession() as session:
        url = f"{GAMMA_BASE}/markets?conditionId={condition_id}"
        print(f"Fetching: {url}")
        
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            print(f"Status: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                
                market = None
                if isinstance(data, list) and data:
                    market = data[0]
                elif isinstance(data, dict) and "markets" in data and data["markets"]:
                    market = data["markets"][0]
                elif isinstance(data, dict) and "id" in data:
                    market = data
                
                if market:
                    print("\n" + "=" * 80)
                    print("Market Information:")
                    print("=" * 80)
                    print(f"Title: {market.get('title', 'N/A')}")
                    print(f"Question: {market.get('question', 'N/A')}")
                    print(f"Description: {market.get('description', 'N/A')[:200] if market.get('description') else 'N/A'}")
                    print(f"Slug: {market.get('slug', 'N/A')}")
                    print(f"Active: {market.get('active', 'N/A')}")
                    print(f"Resolved: {market.get('resolved', 'N/A')}")
                    print(f"End Date: {market.get('endDate', 'N/A')}")
                    print(f"End Date ISO: {market.get('endDateIso', 'N/A')}")
                    
                    # Show all fields that might contain the question
                    print("\n" + "=" * 80)
                    print("All relevant fields:")
                    for key in ['title', 'question', 'description', 'name', 'text', 'query']:
                        if key in market:
                            value = market[key]
                            if isinstance(value, str) and len(value) > 0:
                                print(f"  {key}: {value[:150]}...")
                    
                    return market.get('title') or market.get('question') or market.get('description', '')
            else:
                print(f"Error: HTTP {resp.status}")
                text = await resp.text()
                print(f"Response: {text[:200]}")
    return None

async def main():
    # Test with Raiders vs Texans
    condition_id = "0x0e4ccd69c581deb1aad6f587083a4800d458d6a12f3d202418a53e0c40b18c5a"
    print(f"Testing condition_id: {condition_id}")
    title = await fetch_full_market_info(condition_id)
    
    if title:
        print(f"\n✅ Full title/question: {title}")

if __name__ == "__main__":
    asyncio.run(main())

