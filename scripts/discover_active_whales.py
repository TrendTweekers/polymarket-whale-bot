"""
Discover ACTIVE Polymarket whales from leaderboard
"""

import asyncio
import aiohttp
import json
import sys
from datetime import datetime

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

async def get_polymarket_leaderboard():
    """
    Fetch top traders from Polymarket's public leaderboard
    """
    
    # Try multiple possible leaderboard endpoints
    urls_to_try = [
        "https://api.polymarket.com/leaderboard",
        "https://gamma-api.polymarket.com/leaderboard",
        "https://clob.polymarket.com/leaderboard",
    ]
    
    params = {
        'period': '7d',  # Last 7 days
        'limit': 50
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
    }
    
    url = urls_to_try[0]
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    print("\n🐋 ACTIVE POLYMARKET WHALES (Last 7 Days)\n")
                    print("=" * 100)
                    
                    traders = data.get('leaderboard', [])
                    
                    if not traders:
                        print("No leaderboard data. Trying alternative method...")
                        return await get_whales_from_markets()
                    
                    for i, trader in enumerate(traders[:20], 1):
                        address = trader.get('wallet_address', trader.get('address', 'Unknown'))
                        volume = trader.get('volume', trader.get('total_volume', 0))
                        pnl = trader.get('pnl', trader.get('profit', 0))
                        trades = trader.get('trades', trader.get('num_trades', 0))
                        
                        print(f"\n{i}. Whale: {address}")
                        print(f"   7-Day Volume: ${float(volume):,.2f}")
                        print(f"   7-Day P&L: ${float(pnl):+,.2f}")
                        print(f"   Number of Trades: {trades}")
                    
                    # Generate whale_list.json
                    print("\n\n📝 COPY THIS TO config/whale_list.json:")
                    print("=" * 100)
                    print('{\n  "whales": [')
                    
                    for i, trader in enumerate(traders[:10], 1):
                        address = trader.get('wallet_address', trader.get('address', 'Unknown'))
                        volume = float(trader.get('volume', trader.get('total_volume', 0)))
                        pnl = float(trader.get('pnl', trader.get('profit', 0)))
                        trades = trader.get('trades', trader.get('num_trades', 0))
                        
                        print(f'    {{')
                        print(f'      "address": "{address}",')
                        print(f'      "name": "Top Trader #{i}",')
                        print(f'      "volume_7d": {volume:.2f},')
                        print(f'      "pnl_7d": {pnl:.2f},')
                        print(f'      "num_trades": {trades},')
                        print(f'      "discovered": "{datetime.now().isoformat()}"')
                        print(f'    }}{"," if i < 10 else ""}')
                    
                    print('  ]\n}')
                
                else:
                    print(f"Leaderboard API returned {response.status}")
                    print("Trying alternative method...")
                    return await get_whales_from_markets()
        
        except Exception as e:
            print(f"Error fetching leaderboard: {e}")
            print("Trying alternative method...")
            return await get_whales_from_markets()


async def get_whales_from_markets():
    """
    Alternative: Find whales by checking recent large trades on markets
    """
    
    print("\n🔍 Finding whales from recent market activity...\n")
    
    gamma_url = "https://gamma-api.polymarket.com"
    
    async with aiohttp.ClientSession() as session:
        # Get popular markets
        async with session.get(f"{gamma_url}/markets?limit=20&active=true") as response:
            if response.status != 200:
                print(f"Error: {response.status}")
                return
            
            markets_data = await response.json()
            markets = markets_data if isinstance(markets_data, list) else markets_data.get('data', markets_data.get('markets', []))
            
            if not markets:
                print("No markets found. API structure may have changed.")
                print("\nManual method: Visit https://polymarket.com and check:")
                print("  - Leaderboards page")
                print("  - Large market positions")
                print("  - Recent large trades")
                return
            
            print(f"Found {len(markets)} markets. Checking recent trades...\n")
            
            if not markets:
                print("No markets returned. API may require authentication.")
                print_manual_instructions()
                return
            
            whale_volumes = {}  # Track total volume per address
            markets_checked = 0
            
            # Check recent trades on each market
            for market in markets[:10]:
                market_id = market.get('id', market.get('condition_id'))
                
                if not market_id:
                    continue
                
                try:
                    # Try multiple trade endpoint formats
                    trade_endpoints = [
                        f"{gamma_url}/markets/{market_id}/trades?limit=100",
                        f"{gamma_url}/trades?market={market_id}&limit=100",
                        f"https://clob.polymarket.com/trades?market={market_id}&limit=100",
                    ]
                    
                    trades_found = False
                    for trade_url in trade_endpoints:
                        async with session.get(trade_url) as trade_response:
                            if trade_response.status == 200:
                                trades_data = await trade_response.json()
                                trades = trades_data if isinstance(trades_data, list) else trades_data.get('data', trades_data.get('trades', []))
                                
                                if trades:
                                    trades_found = True
                                    for trade in trades:
                                        # Try multiple possible address fields
                                        address = (
                                            trade.get('user') or 
                                            trade.get('address') or 
                                            trade.get('maker') or 
                                            trade.get('taker') or
                                            trade.get('trader')
                                        )
                                        
                                        # Try multiple possible size fields
                                        size = float(
                                            trade.get('size') or 
                                            trade.get('amount') or 
                                            trade.get('quantity') or 
                                            trade.get('value') or
                                            0
                                        )
                                        
                                        if address and size > 1000:  # Trades over $1k
                                            if address not in whale_volumes:
                                                whale_volumes[address] = {'volume': 0, 'trades': 0}
                                            whale_volumes[address]['volume'] += size
                                            whale_volumes[address]['trades'] += 1
                                    break  # Found trades, no need to try other endpoints
                    
                    if trades_found:
                        markets_checked += 1
                    else:
                        print(f"  No trades found for market {market_id[:10]}...")
                
                except Exception as e:
                    print(f"  Error checking market {market_id[:10]}: {str(e)[:50]}")
                    continue
            
            print(f"\nChecked {markets_checked} markets with trades.")
            
            # Sort by volume
            sorted_whales = sorted(
                whale_volumes.items(),
                key=lambda x: x[1]['volume'],
                reverse=True
            )
            
            print("=" * 100)
            print("Top traders by recent market activity:\n")
            
            for i, (address, data) in enumerate(sorted_whales[:20], 1):
                print(f"{i}. {address}")
                print(f"   Volume: ${data['volume']:,.2f}")
                print(f"   Trades: {data['trades']}")
                print()
            
            # Generate JSON
            print("\n📝 COPY THIS TO config/whale_list.json:")
            print("=" * 100)
            print('{\n  "whales": [')
            
            for i, (address, data) in enumerate(sorted_whales[:10], 1):
                print(f'    {{')
                print(f'      "address": "{address}",')
                print(f'      "name": "Active Trader #{i}",')
                print(f'      "recent_volume": {data["volume"]:.2f},')
                print(f'      "recent_trades": {data["trades"]},')
                print(f'      "discovered": "{datetime.now().isoformat()}"')
                print(f'    }}{"," if i < 10 else ""}')
            
            print('  ]\n}')
            
            if not sorted_whales:
                print("\n⚠️  No whales found via API.")
                print_manual_instructions()


def print_manual_instructions():
    """
    Print instructions for manually finding whales
    """
    print("\n" + "=" * 100)
    print("📋 MANUAL WHALE DISCOVERY INSTRUCTIONS")
    print("=" * 100)
    print("\nSince the API endpoints require authentication or have changed,")
    print("here are ways to find real Polymarket whales manually:\n")
    print("1. Visit Polymarket.com:")
    print("   - Go to any large market")
    print("   - Click on large positions")
    print("   - Copy wallet addresses from top traders\n")
    print("2. Check Polymarket Discord/Twitter:")
    print("   - Look for announcements about top traders")
    print("   - Check leaderboard discussions\n")
    print("3. Use the subgraph script:")
    print("   - Run: python scripts/discover_whales.py")
    print("   - This uses the Positions Subgraph (may have limited data)\n")
    print("4. Monitor markets directly:")
    print("   - Watch markets with high volume")
    print("   - Note addresses making large trades\n")
    print("Example whale_list.json format:")
    print('{\n  "whales": [')
    print('    {')
    print('      "address": "0x...",')
    print('      "name": "Known Whale",')
    print('      "known_win_rate": 0.65,')
    print('      "specialty": ["politics"],')
    print('      "avg_bet_size": 20000')
    print('    }')
    print('  ]\n}')


if __name__ == "__main__":
    asyncio.run(get_polymarket_leaderboard())
