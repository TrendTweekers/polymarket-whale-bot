"""
Debug Polymarket APIs - See what data is actually available
"""

import asyncio
import aiohttp
import json

async def debug_apis():
    """
    Test all Polymarket endpoints and show actual response formats
    """
    
    print("\n" + "="*100)
    print("🔧 DEBUGGING POLYMARKET APIs")
    print("="*100)
    
    async with aiohttp.ClientSession() as session:
        
        # TEST 1: Markets endpoint
        print("\n📊 TEST 1: Gamma Markets API")
        print("-"*100)
        
        try:
            url = "https://gamma-api.polymarket.com/markets?closed=false&limit=5"
            print(f"URL: {url}\n")
            
            async with session.get(url) as response:
                print(f"Status: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    
                    print(f"\nResponse Type: {type(data)}")
                    print(f"Number of markets: {len(data) if isinstance(data, list) else 'N/A'}")
                    
                    # Show first market structure
                    if isinstance(data, list) and len(data) > 0:
                        print("\n📋 First Market Structure:")
                        print(json.dumps(data[0], indent=2)[:1000] + "...")
                        
                        market_id = data[0].get('condition_id') or data[0].get('id')
                        print(f"\n✅ Market ID found: {market_id}")
                        
                        # TEST 2: Try trades endpoint for this market
                        print(f"\n📊 TEST 2: CLOB Trades API for market {market_id[:16]}...")
                        print("-"*100)
                        
                        trade_url = f"https://clob.polymarket.com/trades?market={market_id}&limit=10"
                        print(f"URL: {trade_url}\n")
                        
                        async with session.get(trade_url) as trade_response:
                            print(f"Status: {trade_response.status}")
                            
                            if trade_response.status == 200:
                                trades = await trade_response.json()
                                print(f"\nResponse Type: {type(trades)}")
                                print(f"Number of trades: {len(trades) if isinstance(trades, list) else 'N/A'}")
                                
                                if isinstance(trades, list) and len(trades) > 0:
                                    print("\n📋 First Trade Structure:")
                                    print(json.dumps(trades[0], indent=2))
                                    
                                    # Check for trader address fields
                                    print("\n🔍 Looking for trader address...")
                                    trade = trades[0]
                                    possible_fields = ['maker', 'taker', 'trader', 'trader_address', 'address', 'owner', 'user']
                                    
                                    for field in possible_fields:
                                        if field in trade:
                                            print(f"   ✅ Found '{field}': {trade[field]}")
                                    
                                    print(f"\n   All fields: {list(trade.keys())}")
                                
                                elif isinstance(trades, dict):
                                    print("\n📋 Trades Response:")
                                    print(json.dumps(trades, indent=2)[:1000] + "...")
                                else:
                                    print("\n❌ Unexpected trades format")
                            else:
                                error = await trade_response.text()
                                print(f"Error: {error[:500]}")
                    
                    elif isinstance(data, dict):
                        print("\n📋 Markets Response (dict):")
                        print(json.dumps(data, indent=2)[:1000] + "...")
                    
                else:
                    error = await response.text()
                    print(f"Error: {error[:500]}")
        
        except Exception as e:
            print(f"❌ Error: {e}")
        
        # TEST 3: Alternative trades endpoint
        print("\n\n📊 TEST 3: Alternative Trades Endpoint")
        print("-"*100)
        
        try:
            # Try getting recent trades without market filter
            url = "https://clob.polymarket.com/trades?limit=10"
            print(f"URL: {url}\n")
            
            async with session.get(url) as response:
                print(f"Status: {response.status}")
                
                if response.status == 200:
                    trades = await response.json()
                    print(f"\nResponse Type: {type(trades)}")
                    
                    if isinstance(trades, list) and len(trades) > 0:
                        print(f"Number of trades: {len(trades)}")
                        print("\n📋 First Trade:")
                        print(json.dumps(trades[0], indent=2))
                    else:
                        print(json.dumps(trades, indent=2)[:1000] + "...")
                else:
                    error = await response.text()
                    print(f"Error: {error[:500]}")
        
        except Exception as e:
            print(f"❌ Error: {e}")
        
        # TEST 4: Subgraph
        print("\n\n📊 TEST 4: Subgraph Query")
        print("-"*100)
        
        subgraph_url = "https://api.thegraph.com/subgraphs/name/polymarket/matic-markets-5"
        
        query = """
        query RecentActivity {
            userBalances(
                first: 5,
                orderBy: balance,
                orderDirection: desc
            ) {
                user
                balance
            }
        }
        """
        
        try:
            print(f"URL: {subgraph_url}")
            print(f"Query: {query}\n")
            
            async with session.post(subgraph_url, json={'query': query}) as response:
                print(f"Status: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    print("\n📋 Subgraph Response:")
                    print(json.dumps(data, indent=2))
                else:
                    error = await response.text()
                    print(f"Error: {error[:500]}")
        
        except Exception as e:
            print(f"❌ Error: {e}")
        
        # TEST 5: Try Polymarket's public API
        print("\n\n📊 TEST 5: Polymarket Public API")
        print("-"*100)
        
        try:
            url = "https://polymarket.com/api/markets"
            print(f"URL: {url}\n")
            
            async with session.get(url) as response:
                print(f"Status: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    print(f"\nResponse Type: {type(data)}")
                    
                    if isinstance(data, list) and len(data) > 0:
                        print(f"Number of markets: {len(data)}")
                        print("\n📋 First Market:")
                        print(json.dumps(data[0], indent=2)[:1000] + "...")
                    else:
                        print(json.dumps(data, indent=2)[:1000] + "...")
                else:
                    error = await response.text()
                    print(f"Error: {error[:500]}")
        
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n" + "="*100)
    print("🔧 Debug complete!")
    print("="*100)
    print()


if __name__ == "__main__":
    asyncio.run(debug_apis())
