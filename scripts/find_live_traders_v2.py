"""
LIVE TRADER FINDER V2
======================
Finds traders with CURRENT OPEN POSITIONS
Uses Subgraph to find wallets with active positions RIGHT NOW
"""

import asyncio
import aiohttp
import json
from datetime import datetime
from pathlib import Path
from collections import defaultdict

SUBGRAPH_URL = "https://api.thegraph.com/subgraphs/name/polymarket/matic-markets-5"


async def find_traders_with_positions():
    """Find traders who have open positions RIGHT NOW"""
    
    print("\n" + "="*80)
    print("🔍 FINDING TRADERS WITH ACTIVE POSITIONS")
    print("="*80)
    print()
    
    traders = defaultdict(lambda: {
        'address': '',
        'positions': [],
        'total_value': 0.0,
        'markets': set()
    })
    
    async with aiohttp.ClientSession() as session:
        # Query for users with open positions
        query = """
        query ActiveTraders {
            userPositions(
                first: 100,
                where: {
                    netQuantity_gt: "0"
                },
                orderBy: netQuantity,
                orderDirection: desc
            ) {
                user {
                    id
                }
                market {
                    id
                    question
                }
                netQuantity
                avgBuyPrice
            }
        }
        """
        
        print("📊 Querying Subgraph for active positions...")
        
        try:
            async with session.post(
                SUBGRAPH_URL,
                json={'query': query},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status != 200:
                    print(f"❌ Subgraph returned status {response.status}")
                    return []
                
                data = await response.json()
                
                if 'errors' in data:
                    print(f"❌ GraphQL errors: {data['errors']}")
                    return []
                
                positions = data.get('data', {}).get('userPositions', [])
                
                if not positions:
                    print("❌ No active positions found")
                    return []
                
                print(f"✅ Found {len(positions)} active positions")
                print()
                
                # Group by user
                for pos in positions:
                    user_id = pos.get('user', {}).get('id')
                    if not user_id:
                        continue
                    
                    market_id = pos.get('market', {}).get('id', '')
                    market_question = pos.get('market', {}).get('question', 'Unknown')
                    net_qty = float(pos.get('netQuantity', 0))
                    avg_price = float(pos.get('avgBuyPrice', 0.5))
                    position_value = net_qty * avg_price
                    
                    if user_id not in traders:
                        traders[user_id]['address'] = user_id
                    
                    traders[user_id]['positions'].append({
                        'market_id': market_id,
                        'question': market_question,
                        'quantity': net_qty,
                        'value': position_value
                    })
                    traders[user_id]['total_value'] += position_value
                    traders[user_id]['markets'].add(market_id)
        
        except Exception as e:
            print(f"❌ Error querying subgraph: {e}")
            return []
    
    # Convert to list and sort by total value
    trader_list = []
    for addr, data in traders.items():
        trader_list.append({
            'address': addr,
            'active_positions': len(data['positions']),
            'markets_active': len(data['markets']),
            'total_value': data['total_value'],
            'positions': data['positions']
        })
    
    trader_list.sort(key=lambda x: x['total_value'], reverse=True)
    
    return trader_list


async def verify_positions(traders: list):
    """Double-check positions using CLOB API"""
    
    if not traders:
        return []
    
    print("="*80)
    print("🔍 VERIFYING POSITIONS (Double-check)")
    print("="*80)
    print()
    
    verified = []
    
    async with aiohttp.ClientSession() as session:
        for i, trader in enumerate(traders[:10], 1):  # Check top 10
            address = trader['address']
            print(f"[{i}/{min(10, len(traders))}] {address[:12]}... ", end='', flush=True)
            
            url = f"https://clob.polymarket.com/positions/{address}"
            
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        positions = await response.json()
                        
                        if isinstance(positions, list):
                            active = [p for p in positions if float(p.get('size', 0)) > 0]
                            
                            if active:
                                print(f"✅ {len(active)} positions verified")
                                verified.append({
                                    'address': address,
                                    'active_positions': len(active),
                                    'markets_active': trader['markets_active'],
                                    'total_value': trader['total_value'],
                                    'positions': trader['positions']
                                })
                            else:
                                print(f"⚠️ No positions (may have closed)")
                        else:
                            print(f"⚠️ Unexpected format")
                    else:
                        print(f"❌ Status {response.status}")
            except Exception as e:
                print(f"❌ Error: {str(e)[:30]}")
            
            await asyncio.sleep(0.5)
    
    return verified


async def add_to_config(verified_traders: list):
    """Add verified traders to whale_list.json"""
    
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
            "source": f"Live position scan - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "url": f"https://polymarket.com/profile/{addr}",
            "added": datetime.now().strftime('%Y-%m-%d'),
            "testing": True,
            "known_win_rate": 0.65,
            "specialty": ["live_testing"],
            "avg_bet_size": int(trader['total_value'] / max(trader['active_positions'], 1)),
            "live_trader_stats": {
                "active_positions": trader['active_positions'],
                "markets_active": trader['markets_active'],
                "total_value": f"${trader['total_value']:,.0f}"
            }
        })
        
        print(f"   ✅ {addr[:12]}... ({trader['active_positions']} positions, ${trader['total_value']:,.0f})")
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
    
    print("\n🔥 LIVE TRADER FINDER V2 - Find Traders With Active Positions")
    print()
    
    # Find traders with positions
    traders = await find_traders_with_positions()
    
    if not traders:
        print("\n❌ No traders with active positions found")
        print("\nThis could mean:")
        print("  • Very low market activity")
        print("  • All positions recently closed")
        print("  • API/subgraph issues")
        return
    
    print()
    print("="*80)
    print("📊 FOUND TRADERS")
    print("="*80)
    print()
    
    for i, trader in enumerate(traders[:10], 1):
        print(f"{i:2}. {trader['address']}")
        print(f"    Positions: {trader['active_positions']} | Markets: {trader['markets_active']} | Value: ${trader['total_value']:,.0f}")
        print()
    
    # Verify
    verified = await verify_positions(traders)
    
    if not verified:
        print("\n❌ Could not verify any traders have current positions")
        print("   They may have closed positions between queries")
        return
    
    # Add to config
    added = await add_to_config(verified)
    
    if added > 0:
        print()
        print("="*80)
        print("🎯 NEXT STEPS")
        print("="*80)
        print()
        print("✅ Added live traders with ACTIVE POSITIONS")
        print()
        print("Restart bot: python main.py")
        print()
        print("Expected:")
        print("  ⏰ Within 1-2 minutes: position_detected events")
        print("  ⏰ Bot should detect their current positions immediately")
        print()


if __name__ == "__main__":
    asyncio.run(main())
