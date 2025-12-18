"""
Find ACTIVE Polymarket whales - traders who are currently making trades
Focuses on recent activity (last 7-30 days) and frequency
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from collections import defaultdict

async def find_active_whales():
    """
    Multi-pronged approach to find the most active whales
    """
    
    print("\n" + "="*100)
    print("🔍 DISCOVERING ACTIVE POLYMARKET WHALES")
    print("="*100)
    print("\nThis may take 2-3 minutes to scan recent market activity...")
    print()
    
    whales = defaultdict(lambda: {
        'volume': 0,
        'trades': 0,
        'markets': set(),
        'last_trade': None,
        'recent_trades': []
    })
    
    async with aiohttp.ClientSession() as session:
        
        # METHOD 1: Scan top markets for recent trades
        print("📊 Method 1: Scanning top 50 active markets...")
        
        gamma_url = "https://gamma-api.polymarket.com"
        
        try:
            # Get most active markets
            async with session.get(f"{gamma_url}/markets?closed=false&limit=50") as response:
                if response.status == 200:
                    markets_data = await response.json()
                    markets = markets_data if isinstance(markets_data, list) else []
                    
                    print(f"   Found {len(markets)} active markets")
                    
                    # Check recent trades on each market
                    for i, market in enumerate(markets, 1):
                        market_id = market.get('condition_id') or market.get('id')
                        
                        if not market_id:
                            continue
                        
                        if i % 10 == 0:
                            print(f"   Processed {i}/{len(markets)} markets...")
                        
                        try:
                            # Get recent trades
                            url = f"https://clob.polymarket.com/trades?market={market_id}&limit=100"
                            
                            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as trade_response:
                                if trade_response.status == 200:
                                    trades = await trade_response.json()
                                    
                                    # Process each trade
                                    for trade in trades:
                                        # Get trader address (try multiple fields)
                                        trader = (trade.get('maker') or 
                                                trade.get('taker') or 
                                                trade.get('trader_address') or
                                                trade.get('address'))
                                        
                                        if not trader or trader == '0x0000000000000000000000000000000000000000':
                                            continue
                                        
                                        # Parse trade details
                                        size = float(trade.get('size', 0))
                                        timestamp = trade.get('timestamp', trade.get('created_at'))
                                        
                                        # Only count trades over $100 (filter out dust)
                                        if size >= 100:
                                            whales[trader]['volume'] += size
                                            whales[trader]['trades'] += 1
                                            whales[trader]['markets'].add(market_id)
                                            
                                            if timestamp:
                                                whales[trader]['recent_trades'].append({
                                                    'market': market_id,
                                                    'size': size,
                                                    'time': timestamp
                                                })
                                                
                                                # Track most recent
                                                if not whales[trader]['last_trade'] or timestamp > whales[trader]['last_trade']:
                                                    whales[trader]['last_trade'] = timestamp
                        
                        except Exception as e:
                            # Skip failed markets silently
                            continue
        
        except Exception as e:
            print(f"   Error scanning markets: {e}")
        
        print(f"\n✅ Method 1 complete: Found {len(whales)} active traders")
        
        # METHOD 2: Check for whales with current open positions
        print("\n📈 Method 2: Finding traders with current positions...")
        
        subgraph_url = "https://api.thegraph.com/subgraphs/name/polymarket/matic-markets-5"
        
        query = """
        query ActiveTraders {
            userBalances(
                first: 100,
                orderBy: balance,
                orderDirection: desc,
                where: {
                    balance_gt: "10000000"
                }
            ) {
                user
                balance
            }
        }
        """
        
        try:
            async with session.post(subgraph_url, json={'query': query}) as response:
                if response.status == 200:
                    data = await response.json()
                    users = data.get('data', {}).get('userBalances', [])
                    
                    for user_data in users:
                        address = user_data.get('user')
                        balance = float(user_data.get('balance', 0)) / 1e6  # Convert from micro-dollars
                        
                        if address and address not in whales:
                            # Add them if they have significant positions
                            whales[address]['volume'] = balance
                            whales[address]['trades'] = 1  # Estimate
                    
                    print(f"   Found {len(users)} traders with open positions")
        
        except Exception as e:
            print(f"   Error checking positions: {e}")
        
        print(f"\n✅ Method 2 complete")
    
    # FILTER AND RANK
    print("\n🔍 Filtering and ranking whales...\n")
    
    # Calculate activity scores
    now = datetime.now()
    scored_whales = []
    
    for address, data in whales.items():
        # Skip low-activity traders
        if data['trades'] < 2:  # At least 2 trades
            continue
        
        if data['volume'] < 500:  # At least $500 total volume
            continue
        
        # Calculate recency score (days since last trade)
        recency_score = 10
        if data['last_trade']:
            try:
                # Try parsing different timestamp formats
                if isinstance(data['last_trade'], str):
                    if 'T' in data['last_trade']:
                        last_trade_time = datetime.fromisoformat(data['last_trade'].replace('Z', '+00:00'))
                    else:
                        last_trade_time = datetime.fromtimestamp(int(data['last_trade']))
                else:
                    last_trade_time = datetime.fromtimestamp(int(data['last_trade']))
                
                days_since = (now - last_trade_time).days
                recency_score = max(0, 10 - days_since)  # 10 = today, 0 = 10+ days ago
            except:
                pass
        
        # Calculate diversity score
        diversity_score = min(len(data['markets']), 10)  # Max 10 points for market diversity
        
        # Overall activity score
        activity_score = (
            (data['trades'] * 2) +           # 2 points per trade
            (data['volume'] / 1000) +        # 1 point per $1000 volume
            (recency_score * 3) +            # 3x weight for recency
            diversity_score                  # Market diversity
        )
        
        scored_whales.append({
            'address': address,
            'volume': data['volume'],
            'trades': data['trades'],
            'markets': len(data['markets']),
            'last_trade': data['last_trade'],
            'activity_score': activity_score,
            'recency_score': recency_score
        })
    
    # Sort by activity score
    scored_whales.sort(key=lambda x: x['activity_score'], reverse=True)
    
    # Display results
    print("="*100)
    print("🐋 TOP ACTIVE WHALES (by activity score)")
    print("="*100)
    print()
    
    for i, whale in enumerate(scored_whales[:30], 1):
        recency = "🟢 Today" if whale['recency_score'] >= 9 else "🟡 Recent" if whale['recency_score'] >= 5 else "🟠 This week" if whale['recency_score'] >= 3 else "🔴 Older"
        
        print(f"{i:2d}. {whale['address']}")
        print(f"    Volume: ${whale['volume']:,.0f} | Trades: {whale['trades']} | Markets: {whale['markets']}")
        print(f"    Activity Score: {whale['activity_score']:.1f} | {recency}")
        print()
    
    # Generate JSON for top 20
    print("\n" + "="*100)
    print("📝 READY-TO-USE CONFIG (Copy this to config/whale_list.json)")
    print("="*100)
    print()
    
    print('{')
    print('  "whales": [')
    
    for i, whale in enumerate(scored_whales[:20], 1):
        # Determine specialty based on activity
        if whale['trades'] > 10:
            specialty = "High Frequency Trader"
        elif whale['volume'] > 10000:
            specialty = "High Volume Trader"
        elif whale['markets'] > 5:
            specialty = "Diversified Trader"
        else:
            specialty = "Active Trader"
        
        print(f'    {{')
        print(f'      "address": "{whale["address"]}",')
        print(f'      "name": "Whale #{i}",')
        print(f'      "specialty": "{specialty}",')
        print(f'      "recent_volume": {whale["volume"]:.2f},')
        print(f'      "recent_trades": {whale["trades"]},')
        print(f'      "markets_traded": {whale["markets"]},')
        print(f'      "activity_score": {whale["activity_score"]:.1f},')
        print(f'      "discovered": "{datetime.now().isoformat()}"')
        print(f'    }}{"," if i < 20 else ""}')
    
    print('  ]')
    print('}')
    
    print("\n" + "="*100)
    print(f"✅ Found {len(scored_whales[:20])} highly active whales!")
    print("="*100)
    print()


if __name__ == "__main__":
    asyncio.run(find_active_whales())
