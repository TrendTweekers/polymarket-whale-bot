"""Query Polymarket subgraph for historical whale performance
Start with top 100-200 whales to test approach"""
import asyncio
import aiohttp
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from dynamic_whale_manager import DynamicWhaleManager
    whale_manager = DynamicWhaleManager()
except Exception as e:
    print(f"⚠️ Could not load whale manager: {e}")
    whale_manager = None

# Polymarket subgraph endpoint
# Note: Subgraph may be deprecated - using data-api.polymarket.com as alternative
SUBGRAPH_URL = "https://api.thegraph.com/subgraphs/name/polymarket/matic-markets-5"
DATA_API_BASE = "https://data-api.polymarket.com"

# Rate limiting
REQUEST_DELAY = 0.5  # 500ms between requests to avoid rate limits


async def query_user_positions(session: aiohttp.ClientSession, address: str) -> Optional[Dict]:
    """Query subgraph for user's historical positions"""
    
    query = """
    query GetUserPositions($address: String!) {
      user(id: $address) {
        id
        positions(
          first: 1000
          orderBy: timestamp
          orderDirection: desc
          where: { market_: { resolved: true } }
        ) {
          id
          outcomeIndex
          netValue
          timestamp
          market {
            id
            question
            resolved
            winningOutcome
            endDate
          }
        }
      }
    }
    """
    
    try:
        async with session.post(
            SUBGRAPH_URL,
            json={'query': query, 'variables': {'address': address.lower()}},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('data', {}).get('user')
            else:
                print(f"  ⚠️ HTTP {response.status} for {address[:16]}...")
                return None
    except Exception as e:
        print(f"  ❌ Error querying {address[:16]}...: {e}")
        return None


def calculate_performance(positions: List[Dict]) -> Dict:
    """Calculate win rate and total profit from positions"""
    
    if not positions:
        return {
            'win_rate': 0.0,
            'total_trades': 0,
            'total_profit_eth': 0.0,
            'wins': 0,
            'losses': 0
        }
    
    wins = 0
    losses = 0
    total_profit = 0.0
    
    for pos in positions:
        market = pos.get('market', {})
        if not market.get('resolved'):
            continue
        
        winning_outcome = market.get('winningOutcome')
        outcome_index = pos.get('outcomeIndex')
        net_value = float(pos.get('netValue', 0)) / 1e6  # Convert from micro-dollars
        
        if winning_outcome is not None and outcome_index is not None:
            if int(outcome_index) == int(winning_outcome):
                wins += 1
            else:
                losses += 1
        
        total_profit += net_value
    
    total_trades = wins + losses
    win_rate = wins / total_trades if total_trades > 0 else 0.0
    
    return {
        'win_rate': win_rate,
        'total_trades': total_trades,
        'total_profit_eth': total_profit,
        'wins': wins,
        'losses': losses
    }


async def validate_whales_batch(whale_addresses: List[str], limit: int = 200) -> Dict:
    """Validate a batch of whales via subgraph"""
    
    print("="*80)
    print("🔍 SUBGRAPH WHALE VALIDATION")
    print("="*80)
    print()
    print(f"Querying subgraph for top {min(len(whale_addresses), limit)} whales...")
    print(f"Subgraph URL: {SUBGRAPH_URL}")
    print()
    
    results = {}
    
    async with aiohttp.ClientSession() as session:
        # Test connection first
        print("Testing subgraph connection...")
        try:
            test_query = """
            query {
              _meta {
                block {
                  number
                }
              }
            }
            """
            async with session.post(SUBGRAPH_URL, json={'query': test_query}, timeout=aiohttp.ClientTimeout(total=10)) as test_resp:
                if test_resp.status == 200:
                    print("✅ Subgraph connection successful")
                else:
                    print(f"⚠️ Subgraph returned status {test_resp.status}")
        except Exception as e:
            print(f"❌ Subgraph connection failed: {e}")
            return results
        
        print()
        print("Querying whale performance...")
        print()
        
        # Process whales
        for i, address in enumerate(whale_addresses[:limit], 1):
            print(f"[{i}/{min(len(whale_addresses), limit)}] {address[:16]}...", end=" ", flush=True)
            
            user_data = await query_user_positions(session, address)
            
            if user_data:
                positions = user_data.get('positions', [])
                perf = calculate_performance(positions)
                
                results[address] = {
                    'address': address,
                    'positions_count': len(positions),
                    'win_rate': perf['win_rate'],
                    'total_trades': perf['total_trades'],
                    'total_profit_eth': perf['total_profit_eth'],
                    'wins': perf['wins'],
                    'losses': perf['losses'],
                    'validated': True
                }
                
                if perf['total_trades'] > 0:
                    print(f"✅ {perf['total_trades']} trades | {perf['win_rate']:.0%} WR | {perf['total_profit_eth']:+.2f} ETH")
                else:
                    print(f"⚠️ No resolved positions")
            else:
                results[address] = {
                    'address': address,
                    'validated': False,
                    'error': 'No data from subgraph'
                }
                print("❌ No data")
            
            # Rate limiting
            if i < len(whale_addresses[:limit]):
                await asyncio.sleep(REQUEST_DELAY)
    
    return results


async def main():
    """Main function"""
    
    # Get high-confidence whales
    if whale_manager:
        # Get top whales by confidence
        whales = whale_manager.whales
        high_conf_whales = [
            (addr, data) for addr, data in whales.items()
            if data.get('confidence', 0) >= 0.70
        ]
        high_conf_whales.sort(key=lambda x: x[1].get('confidence', 0), reverse=True)
        
        whale_addresses = [addr for addr, _ in high_conf_whales]
        
        print(f"Found {len(whale_addresses)} high-confidence whales (≥70%)")
        print(f"Starting with top 200 to test approach...")
        print()
    else:
        print("⚠️ Could not load whale manager")
        print("Using empty list - will need manual addresses")
        whale_addresses = []
    
    # Validate whales
    results = await validate_whales_batch(whale_addresses, limit=200)
    
    # Summary
    print()
    print("="*80)
    print("📊 VALIDATION SUMMARY")
    print("="*80)
    print()
    
    validated = [r for r in results.values() if r.get('validated')]
    with_trades = [r for r in validated if r.get('total_trades', 0) > 0]
    
    print(f"Total queried: {len(results)}")
    print(f"Successfully validated: {len(validated)}")
    print(f"With resolved trades: {len(with_trades)}")
    print()
    
    if with_trades:
        print("Top performers by historical win rate:")
        sorted_by_wr = sorted(with_trades, key=lambda x: x.get('win_rate', 0), reverse=True)
        for i, whale in enumerate(sorted_by_trades[:10], 1):
            print(f"  {i}. {whale['address'][:16]}... | {whale['win_rate']:.0%} WR | {whale['total_trades']} trades | {whale['total_profit_eth']:+.2f} ETH")
    
    # Save results
    output_file = Path("data/subgraph_validation_results.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_queried': len(results),
            'validated_count': len(validated),
            'with_trades_count': len(with_trades),
            'results': results
        }, f, indent=2)
    
    print()
    print(f"💾 Results saved to: {output_file}")
    print()
    print("="*80)
    print("✅ VALIDATION COMPLETE")
    print("="*80)
    print()
    print("Next steps:")
    print("  1. Review results in data/subgraph_validation_results.json")
    print("  2. If successful, scale to all 840 high-confidence whales")
    print("  3. Integrate with Phase 2 analysis at Hour 48")


if __name__ == "__main__":
    asyncio.run(main())
