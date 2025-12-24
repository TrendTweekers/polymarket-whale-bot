#!/usr/bin/env python3
"""Test UMA resolver with a known resolved market."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import aiohttp
from src.polymarket.uma_resolver import check_uma_resolution
from src.polymarket.scraper import HEADERS, GAMMA_BASE

# Known resolved market: 2024 US Presidential Election
# Condition ID example (verify this is correct)
KNOWN_RESOLVED_CONDITION_ID = "0x0f5d2fb29fb7d3cfee444a200298f468908cc942"  # Example - verify
KNOWN_RESOLVED_QUESTION = "Who will win the 2024 U.S. Presidential Election? This market will resolve to the candidate who is formally elected by the Electoral College as the next President of the United States, as certified by Congress on or around January 6, 2025."

async def fetch_market_title(condition_id: str) -> str:
    """Fetch full market title from Polymarket API."""
    async with aiohttp.ClientSession() as session:
        url = f"{GAMMA_BASE}/markets?conditionId={condition_id}"
        try:
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
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
                        # Try multiple fields for full question
                        title = (
                            market.get("title") or 
                            market.get("question") or 
                            market.get("description") or
                            market.get("name") or
                            ""
                        )
                        return title
        except Exception as e:
            print(f"Error fetching market: {e}")
    return ""

async def test_known_resolved():
    """Test with a known resolved market."""
    print("=" * 80)
    print("Testing UMA Resolver with Known Resolved Market")
    print("=" * 80)
    
    # Test 1: Try to fetch full question from API
    print(f"\n1. Fetching market title for condition_id: {KNOWN_RESOLVED_CONDITION_ID[:20]}...")
    full_title = await fetch_market_title(KNOWN_RESOLVED_CONDITION_ID)
    if full_title:
        print(f"   Found title: {full_title[:100]}...")
    else:
        print(f"   Using known question: {KNOWN_RESOLVED_QUESTION[:100]}...")
        full_title = KNOWN_RESOLVED_QUESTION
    
    # Test 2: Try UMA resolution with full question
    print(f"\n2. Testing UMA resolution...")
    print(f"   Question: {full_title[:80]}...")
    
    result = check_uma_resolution(
        KNOWN_RESOLVED_CONDITION_ID,
        market_title=full_title,
        end_date_iso=None  # Use timestamp 0 for latest
    )
    
    if result:
        print(f"\n   Result:")
        print(f"   - Resolved: {result.get('resolved', False)}")
        if result.get('resolved'):
            print(f"   - Winning Outcome Index: {result.get('winning_outcome_index')}")
            print(f"   - Resolved Price: {result.get('resolved_price')}")
            print(f"   - Resolution Time: {result.get('resolution_time')}")
            print(f"\n   ✅ SUCCESS - Market is resolved!")
        else:
            print(f"   ⏳ Market not resolved yet (or wrong question format)")
    else:
        print(f"\n   ❌ Failed to check resolution")

if __name__ == "__main__":
    asyncio.run(test_known_resolved())

