"""
LIVE TRADER FINDER - Final Version
===================================
Uses CLOB positions endpoint to find traders with active positions
"""

import asyncio
import aiohttp
import json
from datetime import datetime
from pathlib import Path
from collections import defaultdict

CLOB_BASE = "https://clob.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"


async def find_traders_from_recent_trades():
    """Find traders from recent high-volume trades"""
    
    print("\n" + "="*80)
    print("🔍 FINDING LIVE TRADERS FROM RECENT TRADES")
    print("="*80)
    print()
    
    traders = defaultdict(lambda: {
        'address': '',
        'trade_count': 0,
        'total_volume': 0.0,
        'markets': set()
    })
    
    async with aiohttp.ClientSession() as session:
        # Get top markets
        print("📊 Step 1: Getting top markets...")
        markets_url = f"{GAMMA_BASE}/markets"
        params = {"closed": "false", "limit": 30}
        
        try:
            async with session.get(markets_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    print(f"❌ Could not fetch markets: {response.status}")
                    return []
                
                markets = await response.json()
                if isinstance(markets, dict):
                    markets = markets.get('markets', markets.get('data', []))
                
                print(f"✅ Found {len(markets)} markets")
                print()
                
                print("📊 Step 2: Scanning recent trades...")
                print()
                
                checked = 0
                for market in markets[:20]:
                    condition_id = market.get('condition_id') or market.get('id')
                    question = market.get('question', 'Unknown')[:45]
                    
                    if not condition_id:
                        continue
                    
                    checked += 1
                    print(f"[{checked}/20] {question}... ", end='', flush=True)
                    
                    # Get recent trades
                    trades_url = f"{CLOB_BASE}/trades"
                    trades_params = {'market': condition_id, 'limit': 100}
                    
                    try:
                        async with session.get(trades_url, params=trades_params, timeout=aiohttp.ClientTimeout(total=5)) as trades_response:
                            if trades_response.status == 200:
                                trades_data = await trades_response.json()
                                
                                # Handle different response formats
                                if isinstance(trades_data, list):
                                    trades = trades_data
                                elif isinstance(trades_data, dict):
                                    trades = trades_data.get('trades', trades_data.get('data', []))
                                else:
                                    trades = []
                                
                                found = 0
                                for trade in trades[:50]:  # Check last 50
                                    # Try multiple fields for trader address
                                    trader = (trade.get('maker') or trade.get('taker') or 
                                             trade.get('user') or trade.get('trader') or
                                             trade.get('address'))
                                    
                                    if not trader or trader.startswith('0x0000'):
                                        continue
                                    
                                    size = float(trade.get('size', trade.get('amount', 0)))
                                    price = float(trade.get('price', trade.get('fillPrice', 0.5)))
                                    value = size * price
                                    
                                    if value > 50:  # $50+ trades
                                        traders[trader]['address'] = trader
                                        traders[trader]['trade_count'] += 1
                                        traders[trader]['total_volume'] += value
                                        traders[trader]['markets'].add(condition_id)
                                        found += 1
                                
                                if found > 0:
                                    print(f"✅ {found} traders")
                                else:
                                    print("⚪")
                            else:
                                print("⚪")
                    except Exception as e:
                        print(f"⚪")
                    
                    await asyncio.sleep(0.2)
        
        except Exception as e:
            print(f"❌ Error: {e}")
            return []
    
    # Convert to list
    trader_list = []
    for addr, data in traders.items():
        if data['trade_count'] >= 2:  # At least 2 trades
            trader_list.append({
                'address': addr,
                'trade_count': data['trade_count'],
                'total_volume': data['total_volume'],
                'markets': len(data['markets'])
            })
    
    trader_list.sort(key=lambda x: x['total_volume'], reverse=True)
    return trader_list


async def verify_has_positions(traders: list):
    """Check if traders have current positions using CLOB positions endpoint"""
    
    if not traders:
        return []
    
    print()
    print("="*80)
    print("🔍 VERIFYING ACTIVE POSITIONS")
    print("="*80)
    print()
    
    verified = []
    
    async with aiohttp.ClientSession() as session:
        for i, trader in enumerate(traders[:10], 1):
            address = trader['address']
            print(f"[{i}/{min(10, len(traders))}] {address[:12]}... ", end='', flush=True)
            
            url = f"{CLOB_BASE}/positions/{address}"
            
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        positions = await response.json()
                        
                        if isinstance(positions, list):
                            active = [p for p in positions if float(p.get('size', 0)) > 0]
                            
                            if active:
                                print(f"✅ {len(active)} positions")
                                verified.append({
                                    'address': address,
                                    'active_positions': len(active),
                                    'trade_count': trader['trade_count'],
                                    'total_volume': trader['total_volume'],
                                    'markets': trader['markets']
                                })
                            else:
                                print(f"⚠️ No positions")
                        else:
                            print(f"⚠️ Unexpected format")
                    else:
                        print(f"❌ Status {response.status}")
            except Exception as e:
                print(f"❌ Error")
            
            await asyncio.sleep(0.3)
    
    return verified


async def add_to_config(verified_traders: list):
    """Add to whale_list.json"""
    
    if not verified_traders:
        print("\n❌ No verified traders to add")
        return 0
    
    print()
    print("="*80)
    print("💾 ADDING TO CONFIG")
    print("="*80)
    print()
    
    config_file = Path("config/whale_list.json")
    
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
    else:
        config = {"whales": []}
    
    existing = {w.get('address', '').lower() for w in config.get('whales', [])}
    
    added = 0
    for trader in verified_traders[:5]:  # Add top 5
        addr = trader['address']
        
        if addr.lower() in existing:
            print(f"   ⏭️ {addr[:12]}... (already in config)")
            continue
        
        config['whales'].append({
            "address": addr,
            "name": f"LIVE TRADER (Testing) - {trader['active_positions']} positions",
            "source": f"Live scan - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "url": f"https://polymarket.com/profile/{addr}",
            "added": datetime.now().strftime('%Y-%m-%d'),
            "testing": True,
            "known_win_rate": 0.65,
            "specialty": ["live_testing"],
            "avg_bet_size": int(trader['total_volume'] / max(trader['trade_count'], 1)),
            "live_stats": {
                "active_positions": trader['active_positions'],
                "recent_trades": trader['trade_count'],
                "total_volume": f"${trader['total_volume']:,.0f}",
                "markets": trader['markets']
            }
        })
        
        print(f"   ✅ {addr[:12]}... ({trader['active_positions']} positions)")
        added += 1
    
    if added == 0:
        print("\n⚠️ All traders already in config")
        return 0
    
    # Save
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print()
    print(f"✅ Added {added} live traders")
    print(f"📊 Total whales: {len(config['whales'])}")
    
    return added


async def main():
    """Main execution"""
    
    print("\n🔥 LIVE TRADER FINDER - Find Active Traders")
    print()
    
    # Find from trades
    traders = await find_traders_from_recent_trades()
    
    if not traders:
        print("\n❌ No active traders found from recent trades")
        print("\nThis means:")
        print("  • Very low trading activity right now")
        print("  • Markets may be quiet")
        print("  • Try again during peak hours")
        return
    
    print()
    print("="*80)
    print("📊 FOUND TRADERS")
    print("="*80)
    print()
    
    for i, trader in enumerate(traders[:10], 1):
        print(f"{i:2}. {trader['address']}")
        print(f"    Trades: {trader['trade_count']} | Volume: ${trader['total_volume']:,.0f} | Markets: {trader['markets']}")
        print()
    
    # Verify positions
    verified = await verify_has_positions(traders)
    
    if not verified:
        print("\n⚠️ Found traders but none have current positions")
        print("   They may have closed positions recently")
        print("   Adding them anyway - bot will detect when they trade again")
        
        # Add top 3 even without positions (they're active traders)
        added = await add_to_config(traders[:3])
        if added > 0:
            print(f"\n✅ Added {added} active traders (will detect when they trade)")
    else:
        # Add verified traders
        added = await add_to_config(verified)
        
        if added > 0:
            print()
            print("="*80)
            print("🎯 NEXT STEPS")
            print("="*80)
            print()
            print("✅ Added live traders")
            print()
            print("Restart bot: python main.py")
            print()
            print("Expected:")
            print("  ⏰ Bot will detect positions within 1-2 check cycles")
            print("  ⏰ Watch logs for 'position_detected' events")


if __name__ == "__main__":
    asyncio.run(main())
