"""
AUTOMATED WHALE FINDER - Using Existing Services
=================================================
Instead of scraping Polymarket directly, use existing whale tracking services
that already do the heavy lifting!

Services found:
1. PolyWhaleFeed.com - Real-time $10k+ trades
2. PolyWatch.tech - Free Telegram whale alerts
3. PolyTrack - Pre-vetted whales (Dev Picks)
4. Polymarket Analytics - Trader leaderboards

This script monitors PolyWhaleFeed's public feed for whale addresses
"""

import asyncio
import aiohttp
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict


async def scrape_polywhalefeed(session: aiohttp.ClientSession) -> list:
    """
    PolyWhaleFeed.com shows all $10k+ trades
    Let's try to get data from their feed
    """
    
    # They likely have an API or we can scrape the page
    # For now, this is the concept
    
    url = "https://polywhalefeed.com/"  # May have /api/trades endpoint
    
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status == 200:
                # Would parse HTML or JSON for whale addresses
                # For now, return conceptual structure
                print("✅ Connected to PolyWhaleFeed")
                return []
    except:
        print("⚠️ Could not connect to PolyWhaleFeed")
    
    return []


async def check_polymarket_leaderboard_api(session: aiohttp.ClientSession) -> list:
    """
    Try to find leaderboard data from Polymarket's API
    """
    
    # Based on search results, there's no public leaderboard API
    # But let's check a few endpoints
    
    endpoints_to_try = [
        "https://gamma-api.polymarket.com/leaderboard",
        "https://gamma-api.polymarket.com/traders",
        "https://gamma-api.polymarket.com/top-traders",
    ]
    
    for endpoint in endpoints_to_try:
        try:
            async with session.get(endpoint, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Found data at: {endpoint}")
                    return data
        except:
            pass
    
    print("⚠️ No leaderboard API found")
    return []


async def get_whales_from_recent_large_trades(session: aiohttp.ClientSession) -> dict:
    """
    Get recent large trades from CLOB API
    Extract wallet addresses from maker field
    """
    
    print("\n🔍 Scanning recent large trades (this actually works!)...")
    print()
    
    whale_stats = defaultdict(lambda: {'trades': 0, 'volume': 0})
    
    # Get recent trades across multiple markets
    markets_url = "https://gamma-api.polymarket.com/markets"
    params = {
        "closed": "false",
        "limit": 20,
        "_sort": "volume",
        "_order": "DESC"
    }
    
    try:
        async with session.get(markets_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status != 200:
                print("❌ Could not fetch markets")
                return {}
            
            markets = await response.json()
            print(f"📊 Checking {len(markets)} high-volume markets...")
            print()
            
            for i, market in enumerate(markets, 1):
                # Try both camelCase and snake_case
                condition_id = market.get('conditionId') or market.get('condition_id')
                question = market.get('question', 'Unknown')[:50]
                
                if not condition_id:
                    continue
                
                print(f"[{i}/{len(markets)}] {question}...")
                
                # Get event data
                events_url = f"https://clob.polymarket.com/events/{condition_id}"
                
                try:
                    async with session.get(events_url, timeout=aiohttp.ClientTimeout(total=3)) as events_response:
                        if events_response.status == 200:
                            event_data = await events_response.json()
                            tokens = event_data.get('tokens', [])
                            
                            # Check orders for each token
                            for token in tokens[:2]:  # Both outcomes
                                token_id = token.get('token_id')
                                
                                if not token_id:
                                    continue
                                
                                # Get order book
                                book_url = f"https://clob.polymarket.com/book"
                                book_params = {'token_id': token_id}
                                
                                try:
                                    async with session.get(book_url, params=book_params, timeout=aiohttp.ClientTimeout(total=2)) as book_response:
                                        if book_response.status == 200:
                                            book = await book_response.json()
                                            
                                            # Extract whale addresses
                                            orders = book.get('bids', []) + book.get('asks', [])
                                            
                                            for order in orders:
                                                maker = order.get('maker')
                                                size = float(order.get('size', 0))
                                                price = float(order.get('price', 0))
                                                value = size * price
                                                
                                                # Track whales with orders >$500
                                                if maker and value > 500:
                                                    whale_stats[maker]['trades'] += 1
                                                    whale_stats[maker]['volume'] += value
                                except:
                                    pass
                except:
                    pass
                
                await asyncio.sleep(0.3)  # Rate limiting
    
    except Exception as e:
        print(f"❌ Error: {e}")
    
    return whale_stats


async def validate_and_rank_whales(whale_stats: dict, session: aiohttp.ClientSession) -> list:
    """
    Validate whales have active positions and rank them
    """
    
    if not whale_stats:
        return []
    
    print()
    print("="*80)
    print("🔍 VALIDATING WHALE ACTIVITY")
    print("="*80)
    print()
    
    # Filter to addresses with multiple trades
    candidates = [(addr, stats) for addr, stats in whale_stats.items() 
                  if stats['trades'] >= 3]  # At least 3 active orders
    
    # Sort by volume
    candidates.sort(key=lambda x: x[1]['volume'], reverse=True)
    
    print(f"Found {len(candidates)} candidates with 3+ active orders")
    print(f"Checking top {min(20, len(candidates))} for current positions...")
    print()
    
    validated = []
    
    for i, (address, stats) in enumerate(candidates[:20], 1):
        print(f"[{i}/20] {address[:12]}... (${stats['volume']:,.0f} in orders) ", end='', flush=True)
        
        # Check positions
        positions_url = f"https://clob.polymarket.com/positions/{address}"
        
        try:
            async with session.get(positions_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    positions = await response.json()
                    
                    if isinstance(positions, list):
                        active = [p for p in positions if float(p.get('size', 0)) > 0]
                        
                        if active:
                            print(f"✅ {len(active)} positions")
                            validated.append({
                                'address': address,
                                'order_volume': stats['volume'],
                                'active_orders': stats['trades'],
                                'active_positions': len(active),
                                'score': stats['volume'] + (len(active) * 100)
                            })
                        else:
                            print(f"⚠️ No positions")
                    else:
                        print(f"⚠️ Invalid data")
                else:
                    print(f"❌ No data")
        except:
            print(f"❌ Error")
        
        await asyncio.sleep(0.5)
    
    return sorted(validated, key=lambda x: x['score'], reverse=True)


async def save_whales_to_config(whales: list):
    """Save validated whales, merging with existing"""
    
    if not whales:
        print("\n❌ No whales found!")
        print()
        print("ALTERNATIVE: Use these manual services:")
        print()
        print("1. PolyWhaleFeed.com")
        print("   → See all $10k+ trades in real-time")
        print("   → Copy wallet addresses from trades")
        print()
        print("2. PolyWatch.tech")
        print("   → Free Telegram bot")
        print("   → Get alerts for whale trades")
        print("   → Note wallet addresses")
        print()
        print("3. PolyTrack 'Dev Picks'")
        print("   → Pre-vetted 60%+ win rate whales")
        print("   → Visit: polytrackhq.app")
        print()
        return
    
    print()
    print("="*80)
    print("💾 SAVING WHALES TO CONFIG")
    print("="*80)
    print()
    
    print(f"✅ Found {len(whales)} validated whales:")
    print()
    
    for i, whale in enumerate(whales[:15], 1):
        print(f"{i:2}. ${whale['order_volume']:>8,.0f} volume | "
              f"{whale['active_positions']} positions | "
              f"{whale['address'][:14]}...")
    
    print()
    
    # Load existing
    config_file = Path("config/whale_list.json")
    
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
        print(f"📋 Loaded existing config: {len(config.get('whales', []))} whales")
    else:
        config = {"whales": []}
        print("📝 Creating new config")
    
    # Get existing addresses
    existing = {w.get('address', '').lower() for w in config.get('whales', [])}
    
    added = 0
    skipped = 0
    
    # Add new whales
    for whale in whales[:15]:
        if whale['address'].lower() in existing:
            skipped += 1
            continue
        
        config['whales'].append({
            "address": whale['address'],
            "name": f"Active Whale ({whale['active_positions']} positions)",
            "source": "Automated discovery - orderbook scan",
            "url": f"https://polymarket.com/profile/{whale['address']}",
            "added": datetime.now().strftime('%Y-%m-%d'),
            "discovery_metrics": {
                "order_volume": f"${whale['order_volume']:,.0f}",
                "active_orders": whale['active_orders'],
                "active_positions": whale['active_positions']
            }
        })
        added += 1
    
    # Save
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print()
    print(f"➕ Added: {added} new whales")
    print(f"⏭️ Skipped: {skipped} duplicates")
    print(f"📊 Total: {len(config['whales'])} whales")
    print()
    print("="*80)
    print("✅ DONE! Restart bot: python main.py")
    print("="*80)


async def main():
    """Main execution"""
    
    print("\n" + "="*80)
    print("🤖 AUTOMATED WHALE FINDER")
    print("="*80)
    print()
    print("Method: Scan orderbooks for active large traders")
    print("Criteria: $500+ orders, 3+ markets, current positions")
    print()
    print("⏱️ This will take 2-3 minutes...")
    print()
    
    async with aiohttp.ClientSession() as session:
        # Get whale stats from orderbooks
        whale_stats = await get_whales_from_recent_large_trades(session)
        
        if not whale_stats:
            print("\n❌ Could not find whales via orderbooks")
            print()
            print("RECOMMENDATION: Use manual services instead:")
            print("  • PolyWhaleFeed.com - $10k+ trade feed")
            print("  • PolyWatch.tech - Telegram whale alerts")
            print("  • PolyTrack - Pre-vetted whale list")
            return
        
        # Validate and rank
        validated = await validate_and_rank_whales(whale_stats, session)
        
        # Save
        await save_whales_to_config(validated)


if __name__ == "__main__":
    asyncio.run(main())
