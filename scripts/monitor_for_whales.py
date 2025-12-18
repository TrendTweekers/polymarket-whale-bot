"""
Monitor markets in real-time to discover active traders
Watches for position changes to identify whales
"""

import asyncio
import aiohttp
import json
from datetime import datetime
from collections import defaultdict

async def monitor_markets():
    """
    Monitor markets to see position changes in real-time
    """
    
    print("\n" + "="*100)
    print("🔍 REAL-TIME WHALE DISCOVERY")
    print("="*100)
    print("\nMonitoring top 20 markets for position changes...")
    print("This will run for 5 minutes and discover active traders.")
    print("Press Ctrl+C to stop early.\n")
    
    discovered_whales = defaultdict(lambda: {
        'volume': 0,
        'trades': 0,
        'markets': set(),
        'first_seen': datetime.now()
    })
    
    async with aiohttp.ClientSession() as session:
        
        # Get top markets
        async with session.get("https://gamma-api.polymarket.com/markets?closed=false&limit=20") as response:
            if response.status != 200:
                print("❌ Could not fetch markets")
                return
            
            markets = await response.json()
            print(f"✅ Monitoring {len(markets)} markets\n")
        
        # Monitor for 5 minutes
        start_time = datetime.now()
        check_interval = 10  # Check every 10 seconds
        
        previous_positions = {}
        
        try:
            while (datetime.now() - start_time).seconds < 300:  # 5 minutes
                
                for market in markets:
                    market_id = market.get('conditionId') or market.get('id')
                    
                    try:
                        # Check orderbook to see active positions
                        url = f"https://gamma-api.polymarket.com/markets/{market_id}"
                        
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as detail_response:
                            if detail_response.status == 200:
                                detail = await detail_response.json()
                                
                                # Look for clob_token_ids to check orderbook
                                tokens = detail.get('clobTokenIds', [])
                                
                                for token_id in tokens:
                                    try:
                                        # Get orderbook
                                        orderbook_url = f"https://clob.polymarket.com/book?token_id={token_id}"
                                        
                                        async with session.get(orderbook_url, timeout=aiohttp.ClientTimeout(total=2)) as book_response:
                                            if book_response.status == 200:
                                                book = await book_response.json()
                                                
                                                # Extract makers from bids and asks
                                                bids = book.get('bids', [])
                                                asks = book.get('asks', [])
                                                
                                                for order in bids + asks:
                                                    maker = order.get('maker_address')
                                                    size = float(order.get('size', 0))
                                                    
                                                    if maker and size > 100:
                                                        discovered_whales[maker]['volume'] += size
                                                        discovered_whales[maker]['trades'] += 1
                                                        discovered_whales[maker]['markets'].add(market_id)
                                    except:
                                        continue
                    
                    except:
                        continue
                
                # Status update
                elapsed = (datetime.now() - start_time).seconds
                print(f"⏱️  {elapsed}s elapsed | Found {len(discovered_whales)} active traders", end='\r')
                
                await asyncio.sleep(check_interval)
        
        except KeyboardInterrupt:
            print("\n\n⏸️  Stopped by user")
    
    # Results
    print("\n\n" + "="*100)
    print("🐋 DISCOVERED ACTIVE TRADERS")
    print("="*100)
    print()
    
    if not discovered_whales:
        print("❌ No active traders found in this timeframe.")
        print("   Try running longer or during peak trading hours.")
        return
    
    # Sort by activity
    sorted_whales = sorted(
        discovered_whales.items(),
        key=lambda x: x[1]['volume'],
        reverse=True
    )
    
    for i, (address, data) in enumerate(sorted_whales[:20], 1):
        print(f"{i:2d}. {address}")
        print(f"    Volume: ${data['volume']:,.0f} | Orders: {data['trades']} | Markets: {len(data['markets'])}")
        print()
    
    # Generate config
    print("="*100)
    print("📝 ADD TO config/whale_list.json:")
    print("="*100)
    print()
    
    for i, (address, data) in enumerate(sorted_whales[:20], 1):
        print(f'    {{')
        print(f'      "address": "{address}",')
        print(f'      "name": "Discovered Whale #{i}",')
        print(f'      "specialty": "Active Trader",')
        print(f'      "discovered": "{datetime.now().isoformat()}"')
        print(f'    }}{"," if i < len(sorted_whales[:20]) else ""}')


if __name__ == "__main__":
    asyncio.run(monitor_markets())
