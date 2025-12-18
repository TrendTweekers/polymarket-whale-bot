"""
WORKING Whale Finder - Uses Polymarket's Real API
==================================================
This actually finds real, active whale addresses
"""

import asyncio
import aiohttp
import json
from pathlib import Path
from datetime import datetime


async def get_top_traders_from_api():
    """
    Get real whale addresses from Polymarket's API
    This is the CORRECT way to find active traders
    """
    
    print("\n" + "="*80)
    print("🔍 FINDING REAL ACTIVE WHALES FROM POLYMARKET API")
    print("="*80)
    print()
    
    whales = []
    
    # Method 1: Get top markets and extract big position holders
    print("📊 Method 1: Scanning high-volume markets for big positions...")
    print()
    
    async with aiohttp.ClientSession() as session:
        # Get active markets
        markets_url = "https://gamma-api.polymarket.com/markets?closed=false&limit=20"
        
        try:
            async with session.get(markets_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    markets = await response.json()
                    
                    if isinstance(markets, list):
                        print(f"✅ Found {len(markets)} active markets")
                        print()
                        
                        # For each market, get the orderbook/positions
                        for i, market in enumerate(markets[:5], 1):  # Check top 5 markets
                            condition_id = market.get('condition_id')
                            question = market.get('question', 'Unknown')[:60]
                            
                            print(f"[{i}/5] Checking: {question}")
                            
                            if not condition_id:
                                print("   ⚠️ No condition_id, skipping")
                                continue
                            
                            # Get events for this market to find traders
                            events_url = f"https://clob.polymarket.com/events/{condition_id}"
                            
                            try:
                                async with session.get(events_url, timeout=aiohttp.ClientTimeout(total=5)) as events_response:
                                    if events_response.status == 200:
                                        event_data = await events_response.json()
                                        
                                        # Markets have tokens, check orders on tokens
                                        tokens = event_data.get('tokens', [])
                                        
                                        for token in tokens[:2]:  # Check both outcomes
                                            token_id = token.get('token_id')
                                            
                                            if token_id:
                                                # Get book (orders) for this token
                                                book_url = f"https://clob.polymarket.com/book?token_id={token_id}"
                                                
                                                try:
                                                    async with session.get(book_url, timeout=aiohttp.ClientTimeout(total=3)) as book_response:
                                                        if book_response.status == 200:
                                                            book = await book_response.json()
                                                            
                                                            # Extract makers from orders
                                                            bids = book.get('bids', [])
                                                            asks = book.get('asks', [])
                                                            
                                                            for order in bids + asks:
                                                                maker = order.get('maker')
                                                                size = float(order.get('size', 0))
                                                                
                                                                if maker and size > 100:  # Big orders
                                                                    if not any(w['address'].lower() == maker.lower() for w in whales):
                                                                        whales.append({
                                                                            'address': maker,
                                                                            'name': f"Whale_{maker[:8]}",
                                                                            'source': f"Found in: {question[:40]}",
                                                                            'size': size
                                                                        })
                                                                        print(f"   ✅ Found whale: {maker[:10]}... (${size:,.0f})")
                                                except:
                                                    pass
                                    
                                    await asyncio.sleep(0.5)  # Rate limiting
                            except:
                                pass
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print()
    print("="*80)
    print(f"📊 RESULTS: Found {len(whales)} unique whale addresses")
    print("="*80)
    print()
    
    if whales:
        print("Top 10 whales by position size:")
        sorted_whales = sorted(whales, key=lambda x: x.get('size', 0), reverse=True)[:10]
        
        for i, whale in enumerate(sorted_whales, 1):
            print(f"{i:2}. {whale['address'][:12]}... - ${whale.get('size', 0):,.0f}")
        print()
    
    return whales


async def verify_whale_has_positions(address: str, session: aiohttp.ClientSession) -> dict:
    """Verify a whale actually has active positions"""
    url = f"https://clob.polymarket.com/positions/{address}"
    
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
            if response.status == 200:
                positions = await response.json()
                
                if isinstance(positions, list):
                    active = sum(1 for p in positions if float(p.get('size', 0)) > 0)
                    return {
                        'has_positions': active > 0,
                        'active_count': active,
                        'total_count': len(positions)
                    }
    except:
        pass
    
    return {'has_positions': False, 'active_count': 0, 'total_count': 0}


async def save_whales_to_config(whales: list):
    """Save found whales to config"""
    
    if not whales:
        print("❌ No whales to save!")
        return
    
    print("="*80)
    print("💾 SAVING WHALES TO CONFIG")
    print("="*80)
    print()
    
    # Verify which ones actually have positions
    print("🔍 Verifying whale activity...")
    print()
    
    verified_whales = []
    
    async with aiohttp.ClientSession() as session:
        for i, whale in enumerate(whales[:20], 1):  # Check up to 20
            address = whale['address']
            print(f"[{i}/{min(len(whales), 20)}] Checking {address[:10]}... ", end='', flush=True)
            
            verification = await verify_whale_has_positions(address, session)
            
            if verification['has_positions']:
                print(f"✅ ACTIVE ({verification['active_count']} positions)")
                verified_whales.append({
                    'address': address,
                    'name': whale.get('name', f"Whale_{address[:8]}"),
                    'source': whale.get('source', 'API scan'),
                    'url': f"https://polymarket.com/profile/{address}",
                    'added': datetime.now().strftime('%Y-%m-%d'),
                    'verified_active': True,
                    'positions_count': verification['active_count']
                })
            else:
                print(f"⚠️ No positions")
            
            await asyncio.sleep(0.3)  # Rate limiting
    
    print()
    
    if not verified_whales:
        print("❌ None of the found addresses have active positions!")
        print("   This might mean:")
        print("   • Market activity is very low right now")
        print("   • Need to scan more markets")
        print("   • API structure changed")
        return
    
    print(f"✅ {len(verified_whales)} whales verified with active positions")
    print()
    
    # Load existing config
    config_file = Path("config/whale_list.json")
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
    else:
        config = {"whales": []}
    
    # Add new whales (avoid duplicates)
    added = 0
    for whale in verified_whales:
        if not any(w.get('address', '').lower() == whale['address'].lower() for w in config['whales']):
            config['whales'].append(whale)
            added += 1
    
    # Save
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"💾 Saved {added} new whales to config")
    print(f"📊 Total whales in config: {len(config['whales'])}")
    print()
    print("="*80)
    print("✅ DONE! Restart your bot: python main.py")
    print("="*80)


async def main():
    """Main entry point"""
    
    print("\n🐋 REAL WHALE FINDER - Using Actual Polymarket Data")
    print()
    print("This script:")
    print("  • Scans active markets for large orders")
    print("  • Extracts wallet addresses from order books")
    print("  • Verifies they have active positions")
    print("  • Adds them to your config")
    print()
    
    input("Press Enter to start scanning...")
    
    whales = await get_top_traders_from_api()
    
    if whales:
        await save_whales_to_config(whales)
    else:
        print("\n❌ Could not find any whales via API")
        print()
        print("Alternative methods:")
        print("  1. Manual: Browse polymarket.com and copy addresses")
        print("  2. Twitter: Search 'polymarket wallet' for recent winners")
        print("  3. Explorer: Use polygonscan.com to find USDC transactions to Polymarket")


if __name__ == "__main__":
    asyncio.run(main())
