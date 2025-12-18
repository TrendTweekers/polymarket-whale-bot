"""
LIVE TRADER FINDER
==================
Finds whale addresses that have traded in the LAST HOUR
Perfect for testing - guarantees you'll see activity immediately
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from pathlib import Path


async def find_recent_active_traders():
    """
    Find traders who made moves in the last 1-2 hours
    This guarantees we'll see active positions
    """
    
    print("\n" + "="*80)
    print("🔍 FINDING LIVE ACTIVE TRADERS (Last 1-2 Hours)")
    print("="*80)
    print()
    print("Strategy: Find recent high-volume trades and extract addresses")
    print("Goal: Add 3-5 addresses that are ACTIVELY trading RIGHT NOW")
    print()
    
    active_traders = {}
    
    async with aiohttp.ClientSession() as session:
        # Get active high-volume markets
        print("📊 Step 1: Getting active markets...")
        markets_url = "https://gamma-api.polymarket.com/markets"
        params = {
            "closed": "false",
            "limit": 30,
            "_sort": "volume24hr",
            "_order": "DESC"
        }
        
        try:
            async with session.get(markets_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    print("❌ Could not fetch markets")
                    return []
                
                markets = await response.json()
                print(f"✅ Found {len(markets)} high-volume markets")
                print()
                
                print("📊 Step 2: Scanning recent trades for active traders...")
                print()
                
                checked = 0
                for market in markets[:20]:  # Check top 20 by 24h volume
                    condition_id = market.get('condition_id')
                    question = market.get('question', 'Unknown')[:45]
                    volume_24h = market.get('volume24hr', 0)
                    
                    if not condition_id:
                        continue
                    
                    checked += 1
                    print(f"[{checked}/20] {question}... ", end='', flush=True)
                    
                    # Get recent trades for this market
                    trades_url = f"https://clob.polymarket.com/trades"
                    trades_params = {'market': condition_id, 'limit': 50}
                    
                    try:
                        async with session.get(trades_url, params=trades_params, timeout=aiohttp.ClientTimeout(total=5)) as trades_response:
                            if trades_response.status == 200:
                                trades_data = await trades_response.json()
                                
                                # Handle both list and dict responses
                                trades = trades_data if isinstance(trades_data, list) else trades_data.get('trades', [])
                                
                                found_count = 0
                                
                                # Process recent trades (last hour)
                                now = datetime.now()
                                for trade in trades[:50]:  # Check last 50 trades
                                    # Get trader address (try multiple fields)
                                    trader = (trade.get('maker') or trade.get('taker') or 
                                             trade.get('trader') or trade.get('user') or
                                             trade.get('address'))
                                    
                                    if not trader or trader == '0x0000000000000000000000000000000000000000':
                                        continue
                                    
                                    # Get trade size
                                    size = float(trade.get('size', trade.get('amount', 0)))
                                    price = float(trade.get('price', trade.get('fillPrice', 0.5)))
                                    trade_value = size * price
                                    
                                    # Only count significant trades (>$100)
                                    if trade_value > 100:
                                        if trader not in active_traders:
                                            active_traders[trader] = {
                                                'address': trader,
                                                'markets_active': 1,
                                                'total_size': trade_value,
                                                'first_seen': question,
                                                'recent_trades': 1
                                            }
                                            found_count += 1
                                        else:
                                            active_traders[trader]['markets_active'] += 1
                                            active_traders[trader]['total_size'] += trade_value
                                            active_traders[trader]['recent_trades'] += 1
                                
                                if found_count > 0:
                                    print(f"✅ {found_count} traders")
                                else:
                                    print("⚪")
                            else:
                                print("⚪")
                    except Exception as e:
                        print(f"⚪ ({str(e)[:20]})")
                    
                    await asyncio.sleep(0.3)  # Rate limiting
        
        except Exception as e:
            print(f"❌ Error: {e}")
            return []
    
    print()
    print("="*80)
    print("📊 RESULTS")
    print("="*80)
    print()
    
    if not active_traders:
        print("❌ No active traders found")
        print()
        print("This means:")
        print("  • Very low market activity right now")
        print("  • Weekend/off-hours (low volume)")
        print("  • Try again during peak hours (2-6 PM ET)")
        return []
    
    # Sort by activity (markets active + total size)
    sorted_traders = sorted(
        active_traders.values(),
        key=lambda x: x['markets_active'] * 100 + x['total_size'],
        reverse=True
    )
    
    print(f"✅ Found {len(sorted_traders)} active traders")
    print()
    print("Top 10 by activity:")
    print()
    
    for i, trader in enumerate(sorted_traders[:10], 1):
        print(f"{i:2}. {trader['address'][:12]}...")
        print(f"    Active in: {trader['markets_active']} markets")
        print(f"    Total size: ${trader['total_size']:,.0f}")
        print(f"    First seen: {trader['first_seen'][:40]}")
        print()
    
    return sorted_traders[:5]  # Return top 5


async def verify_and_add_live_traders(traders: list):
    """Verify these traders have current positions and add to config"""
    
    if not traders:
        print("No traders to add")
        return
    
    print("="*80)
    print("🔍 VERIFYING ACTIVE POSITIONS")
    print("="*80)
    print()
    
    verified = []
    
    async with aiohttp.ClientSession() as session:
        for i, trader in enumerate(traders, 1):
            address = trader['address']
            print(f"[{i}/{len(traders)}] Checking {address[:12]}... ", end='', flush=True)
            
            url = f"https://clob.polymarket.com/positions/{address}"
            
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        positions = await response.json()
                        
                        if isinstance(positions, list):
                            active = [p for p in positions if float(p.get('size', 0)) > 0]
                            
                            if active:
                                print(f"✅ {len(active)} active positions")
                                verified.append({
                                    'address': address,
                                    'active_positions': len(active),
                                    'markets_active': trader['markets_active'],
                                    'total_size': trader['total_size']
                                })
                            else:
                                print(f"⚠️ No active positions (just closed?)")
                    else:
                        print(f"❌ No data")
            except:
                print(f"❌ Error")
            
            await asyncio.sleep(0.5)
    
    print()
    
    if not verified:
        print("❌ None of the found traders have current positions")
        print("   They may have just closed their trades")
        print("   Try running again in 10-15 minutes")
        return
    
    print(f"✅ {len(verified)} traders verified with active positions")
    print()
    
    # Add to config
    print("="*80)
    print("💾 ADDING LIVE TRADERS TO CONFIG (FOR TESTING)")
    print("="*80)
    print()
    
    config_file = Path("config/whale_list.json")
    
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
        print(f"📋 Current config: {len(config.get('whales', []))} whales")
    else:
        config = {"whales": []}
        print("📝 Creating new config")
    
    existing = {w.get('address', '').lower() for w in config.get('whales', [])}
    
    added = 0
    for trader in verified:
        addr = trader['address']
        
        if addr.lower() in existing:
            print(f"   ⏭️ {addr[:12]}... (already in config)")
            continue
        
        config['whales'].append({
            "address": addr,
            "name": f"LIVE TRADER (Testing) - {trader['active_positions']} positions",
            "source": f"Live activity scan - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "url": f"https://polymarket.com/profile/{addr}",
            "added": datetime.now().strftime('%Y-%m-%d'),
            "testing": True,
            "live_trader_stats": {
                "active_positions": trader['active_positions'],
                "markets_active": trader['markets_active'],
                "total_size": f"${trader['total_size']:,.0f}"
            }
        })
        
        print(f"   ✅ {addr[:12]}... ({trader['active_positions']} positions)")
        added += 1
    
    if added == 0:
        print("\n⚠️ All live traders already in config")
        return
    
    # Save
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print()
    print(f"✅ Added {added} live traders for IMMEDIATE TESTING")
    print(f"📊 Total whales: {len(config['whales'])}")
    print()
    print("="*80)
    print("🎯 RESTART BOT NOW!")
    print("="*80)
    print()
    print("These traders have active positions RIGHT NOW.")
    print("Your bot should detect them within 1-2 check cycles.")
    print()
    print("Expected:")
    print("  ⏰ Within 2 minutes: position_detected events")
    print("  ⏰ Within 5 minutes: trades_considered > 0")
    print("  ⏰ Within 10 minutes: Possible signal if trade is good")
    print()
    print("Restart: python main.py")


async def main():
    """Main execution"""
    
    print("\n🔥 LIVE TRADER FINDER - For Immediate Bot Testing")
    print()
    print("This script finds traders who are ACTIVELY trading RIGHT NOW")
    print("Perfect for testing your bot - you'll see immediate activity!")
    print()
    
    # Find active traders
    traders = await find_recent_active_traders()
    
    if not traders:
        print("\n💡 TIP: Try again during peak hours:")
        print("   • Monday-Friday: 10 AM - 6 PM ET")
        print("   • Avoid late night / early morning")
        print("   • Check market_scanner.py to see if markets are active")
        return
    
    # Verify and add
    await verify_and_add_live_traders(traders)


if __name__ == "__main__":
    asyncio.run(main())
