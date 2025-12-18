"""
Discover top Polymarket whales by querying the subgraph
"""

import asyncio
import aiohttp
import sys
from datetime import datetime

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

async def discover_top_whales():
    """
    Query Polymarket subgraph for top traders by volume
    Uses the official Polymarket Positions Subgraph on Goldsky
    """
    
    # Use Polymarket's official Positions Subgraph
    subgraph_url = "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/positions-subgraph/0.0.7/gn"
    
    # First, try introspection to see available fields
    introspection_query = """
    query IntrospectionQuery {
        __schema {
            queryType {
                fields {
                    name
                    type {
                        name
                        kind
                    }
                }
            }
        }
    }
    """
    
    print("Discovering Polymarket whales...")
    print("Note: Subgraph schemas may have changed. Trying introspection first...\n")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(subgraph_url, json={'query': introspection_query}) as intro_response:
            if intro_response.status == 200:
                intro_data = await intro_response.json()
                if 'data' in intro_data:
                    fields = intro_data['data']['__schema']['queryType']['fields']
                    print("Available query fields:")
                    for field in fields[:10]:
                        print(f"  - {field['name']}")
                    print()
    
    # Try netUserBalances (net positions) instead
    query = """
    query NetUserBalances {
        netUserBalances(
            first: 100,
            orderBy: balance,
            orderDirection: desc
        ) {
            user
            balance
        }
    }
    """
    
    async with aiohttp.ClientSession() as session:
        # Try introspection first
        async with session.post(subgraph_url, json={'query': introspection_query}) as intro_response:
            if intro_response.status == 200:
                intro_data = await intro_response.json()
                if 'data' in intro_data:
                    fields = intro_data['data']['__schema']['queryType']['fields']
                    field_names = [f['name'] for f in fields]
                    print(f"Available fields: {', '.join(field_names[:10])}...\n")
        
        # Try the actual query
        async with session.post(subgraph_url, json={'query': query}) as response:
            if response.status == 200:
                data = await response.json()
                
                # Debug: print response structure
                if 'errors' in data:
                    print("GraphQL Errors:")
                    for error in data['errors']:
                        print(f"  - {error}")
                    return
                
                # Get userBalances or netUserBalances
                user_balances = (
                    data.get('data', {}).get('netUserBalances', []) or
                    data.get('data', {}).get('userBalances', []) or
                    []
                )
                
                if not user_balances:
                    print("No user balances found.")
                    print("You may need to manually add whale addresses to config/whale_list.json")
                    print("\nTo find whales manually:")
                    print("1. Visit Polymarket.com and check leaderboards")
                    print("2. Look at large market positions")
                    print("3. Check Twitter/Discord for known whale addresses")
                    return
                
                # Aggregate balances by user
                whale_data = {}
                for balance_entry in user_balances:
                    user = balance_entry.get('user')
                    if not user:
                        continue
                    
                    # Balance is in wei (18 decimals), convert to USD (assuming 1 token = $1)
                    balance_wei = float(balance_entry.get('balance', 0))
                    balance_usd = balance_wei / 1e18  # Convert from wei
                    
                    if user not in whale_data:
                        whale_data[user] = {
                            'address': user,
                            'total_balance': 0,
                            'num_positions': 0,
                            'positions': []
                        }
                    
                    whale_data[user]['total_balance'] += balance_usd
                    whale_data[user]['num_positions'] += 1
                    whale_data[user]['positions'].append(balance_entry)
                
                # Sort by total balance
                sorted_whales = sorted(
                    whale_data.values(),
                    key=lambda x: x['total_balance'],
                    reverse=True
                )[:20]
                
                print("\n🐋 TOP POLYMARKET WHALES (by position balance)\n")
                print("=" * 80)
                
                for i, whale in enumerate(sorted_whales, 1):
                    address = whale['address']
                    balance = whale['total_balance']
                    positions_count = whale['num_positions']
                    
                    print(f"\n{i}. Whale: {address}")
                    print(f"   Total Balance: ${balance:,.2f}")
                    print(f"   Number of Positions: {positions_count}")
                
                # Generate whale_list.json format
                print("\n\n📝 WHALE LIST JSON FORMAT:")
                print("=" * 80)
                print('{\n  "whales": [')
                
                for i, whale in enumerate(sorted_whales[:10], 1):  # Top 10
                    address = whale['address']
                    balance = whale['total_balance']
                    positions_count = whale['num_positions']
                    
                    print(f'    {{')
                    print(f'      "address": "{address}",')
                    print(f'      "name": "Whale #{i}",')
                    print(f'      "total_balance": {balance:.2f},')
                    print(f'      "num_positions": {positions_count},')
                    print(f'      "discovered": "{datetime.now().isoformat()}"')
                    print(f'    }}{"," if i < 10 else ""}')
                
                print('  ]\n}')
            
            else:
                error_text = await response.text()
                print(f"Error: {response.status}")
                print(f"Response: {error_text[:200]}")
                print("\nNote: You may need to manually add whale addresses to config/whale_list.json")

if __name__ == "__main__":
    asyncio.run(discover_top_whales())
