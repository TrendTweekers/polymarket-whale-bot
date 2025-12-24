#!/usr/bin/env python3
"""Fetch full market question using Polymarket GraphQL API."""
import sys
import asyncio
import aiohttp
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

GRAPHQL_ENDPOINT = "https://clob-api.polymarket.com/graphql"

# GraphQL query to get market details by condition_id
MARKET_QUERY = """
query GetMarket($conditionId: String!) {
  market(conditionId: $conditionId) {
    id
    question
    description
    title
    slug
    endDate
    endDateIso
    active
    resolved
    resolution
    outcomes {
      name
      price
      resolved
      winning
    }
  }
}
"""

async def fetch_market_via_graphql(condition_id: str):
    """Fetch market details using GraphQL API."""
    async with aiohttp.ClientSession() as session:
        payload = {
            "query": MARKET_QUERY,
            "variables": {
                "conditionId": condition_id
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        try:
            async with session.post(GRAPHQL_ENDPOINT, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"GraphQL Status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    
                    if "errors" in data:
                        print(f"GraphQL Errors: {data['errors']}")
                        return None
                    
                    market = data.get("data", {}).get("market")
                    if market:
                        print("\n" + "=" * 80)
                        print("GraphQL Market Data:")
                        print("=" * 80)
                        print(f"ID: {market.get('id', 'N/A')}")
                        print(f"Title: {market.get('title', 'N/A')}")
                        print(f"Question: {market.get('question', 'N/A')}")
                        print(f"Description: {market.get('description', 'N/A')[:200] if market.get('description') else 'N/A'}...")
                        print(f"Slug: {market.get('slug', 'N/A')}")
                        print(f"Active: {market.get('active', 'N/A')}")
                        print(f"Resolved: {market.get('resolved', 'N/A')}")
                        print(f"End Date: {market.get('endDateIso', 'N/A')}")
                        
                        return {
                            "question": market.get("question") or market.get("title"),
                            "description": market.get("description"),
                            "full_text": market.get("description") or market.get("question") or market.get("title")
                        }
                    else:
                        print("No market data in response")
                        print(f"Response: {json.dumps(data, indent=2)[:500]}")
                else:
                    text = await resp.text()
                    print(f"Error: HTTP {resp.status}")
                    print(f"Response: {text[:200]}")
        except Exception as e:
            print(f"Exception: {e}")
            import traceback
            traceback.print_exc()
    
    return None

async def main():
    # Test with Raiders vs Texans
    condition_id = "0x0e4ccd69c581deb1aad6f587083a4800d458d6a12f3d202418a53e0c40b18c5a"
    print(f"Fetching market via GraphQL for condition_id: {condition_id}")
    result = await fetch_market_via_graphql(condition_id)
    
    if result:
        print(f"\n✅ Full question text: {result.get('full_text', 'N/A')[:150]}...")
    else:
        print("\n❌ Failed to fetch via GraphQL")

if __name__ == "__main__":
    asyncio.run(main())

