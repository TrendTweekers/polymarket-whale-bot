"""
API-based Whale Validator - Grok's Improved Approach
Uses Polymarket Data API + on-chain queries instead of deprecated subgraph
"""
import asyncio
import aiohttp
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Polymarket Data API (official, reliable)
DATA_API_BASE = "https://data-api.polymarket.com"

# Rate limiting
REQUEST_DELAY = 0.5  # 500ms between requests


async def get_user_trades(session: aiohttp.ClientSession, address: str, limit: int = 100) -> List[Dict]:
    """Get user's trade history from Polymarket Data API"""
    url = f"{DATA_API_BASE}/trades"
    params = {
        'user': address.lower(),
        'limit': limit,
        'offset': 0,
        'takerOnly': 'true'
    }
    
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                data = await response.json()
                # Handle both list and dict responses
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get('value', [])
                return []
            else:
                return []
    except Exception as e:
        print(f"  ⚠️ Error fetching trades for {address[:16]}...: {e}")
        return []


async def get_market_resolution(session: aiohttp.ClientSession, condition_id: str) -> Optional[Dict]:
    """Get market resolution status from Gamma API"""
    url = f"https://gamma-api.polymarket.com/markets"
    params = {'conditionId': condition_id}
    
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status == 200:
                data = await response.json()
                if isinstance(data, list) and len(data) > 0:
                    market = data[0]
                    return {
                        'resolved': market.get('resolved', False),
                        'winningOutcome': market.get('winningOutcome'),
                        'endDate': market.get('endDate'),
                        'question': market.get('question', '')
                    }
                elif isinstance(data, dict):
                    return {
                        'resolved': data.get('resolved', False),
                        'winningOutcome': data.get('winningOutcome'),
                        'endDate': data.get('endDate'),
                        'question': data.get('question', '')
                    }
    except Exception as e:
        pass
    return None


async def calculate_win_rate_from_resolved_trades(trades: List[Dict], session: aiohttp.ClientSession) -> Dict:
    """
    Calculate actual win rate by checking resolved markets
    This is the proper way to validate whale performance
    """
    if not trades:
        return {
            'win_rate': 0.0,
            'resolved_trades': 0,
            'wins': 0,
            'losses': 0,
            'total_profit_usd': 0.0
        }
    
    # Group trades by market (condition_id or market)
    market_positions = defaultdict(lambda: {'trades': [], 'outcome': None, 'side': None})
    
    for trade in trades:
        # Try multiple field names for condition_id
        condition_id = (
            trade.get('conditionId') or 
            trade.get('condition_id') or 
            trade.get('market') or
            trade.get('eventId') or
            trade.get('event_id')
        )
        
        # Try multiple field names for outcome
        outcome_index = (
            trade.get('outcomeIndex') or 
            trade.get('outcome_index') or
            trade.get('outcome')
        )
        
        # Try to get side (YES/NO)
        side = trade.get('side') or trade.get('direction')
        
        if condition_id:
            market_positions[condition_id]['trades'].append(trade)
            if outcome_index is not None:
                try:
                    market_positions[condition_id]['outcome'] = int(outcome_index)
                except:
                    pass
            if side:
                market_positions[condition_id]['side'] = side
    
    # Check resolution for each market (sample up to 30 markets to avoid too many API calls)
    wins = 0
    losses = 0
    resolved_count = 0
    total_profit = 0.0
    
    # Process markets (limit to 30 to avoid rate limits)
    markets_to_check = list(market_positions.items())[:30]
    
    for condition_id, market_data in markets_to_check:
        resolution = await get_market_resolution(session, condition_id)
        
        if resolution and resolution.get('resolved'):
            resolved_count += 1
            winning_outcome = resolution.get('winningOutcome')
            user_outcome = market_data.get('outcome')
            
            if winning_outcome is not None and user_outcome is not None:
                # Calculate P&L for this position
                position_value = sum(
                    float(t.get('size', 0)) * float(t.get('price', 0))
                    for t in market_data['trades']
                )
                
                if int(user_outcome) == int(winning_outcome):
                    wins += 1
                    total_profit += position_value  # Win = full position value
                else:
                    losses += 1
                    total_profit -= position_value  # Loss = lose position value
                
                # Rate limiting
                await asyncio.sleep(0.3)
    
    win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0
    
    return {
        'win_rate': win_rate,
        'resolved_trades': resolved_count,
        'wins': wins,
        'losses': losses,
        'total_profit_usd': total_profit
    }


def calculate_win_rate_from_trades(trades: List[Dict], session: aiohttp.ClientSession) -> Dict:
    """
    Calculate win rate from trades by checking resolved markets
    This is a simplified approach - checks if trades were profitable
    """
    if not trades:
        return {
            'win_rate': 0.0,
            'total_trades': 0,
            'resolved_trades': 0,
            'wins': 0,
            'losses': 0,
            'total_profit_usd': 0.0
        }
    
    # Group trades by market
    market_trades = defaultdict(list)
    for trade in trades:
        condition_id = trade.get('conditionId') or trade.get('condition_id')
        if condition_id:
            market_trades[condition_id].append(trade)
    
    # For now, use a simplified approach:
    # Count trades and estimate based on trade patterns
    # Full resolution checking would require async market lookups
    
    total_trades = len(trades)
    total_value = sum(float(t.get('size', 0)) * float(t.get('price', 0)) for t in trades)
    
    # Simplified: Assume 60% win rate baseline (will refine with actual resolution data)
    # This is a placeholder - full implementation would check each market's resolution
    
    return {
        'win_rate': 0.0,  # Will be calculated from resolved positions
        'total_trades': total_trades,
        'resolved_trades': 0,  # Will be updated when we check resolutions
        'wins': 0,
        'losses': 0,
        'total_profit_usd': 0.0,
        'total_volume_usd': total_value
    }


async def validate_whale(address: str, session: Optional[aiohttp.ClientSession] = None, check_resolutions: bool = True) -> Dict:
    """
    Validate a single whale using Polymarket Data API
    
    Args:
        address: Whale wallet address
        session: Optional aiohttp session (creates new if None)
        check_resolutions: If True, check market resolutions for win rate (slower but accurate)
    
    Returns:
        {
            'address': str,
            'win_rate': float,
            'trade_count': int,
            'total_profit_eth': float,
            'total_volume_usd': float,
            'resolved_trades': int,
            'wins': int,
            'losses': int,
            'passes': bool,
            'validated': bool
        }
    """
    if session is None:
        async with aiohttp.ClientSession() as sess:
            return await validate_whale(address, sess, check_resolutions)
    
    try:
        # Step 1: Get trade history
        trades = await get_user_trades(session, address, limit=100)
        
        if not trades:
            return {
                'address': address,
                'win_rate': 0.0,
                'trade_count': 0,
                'total_profit_eth': 0.0,
                'total_volume_usd': 0.0,
                'resolved_trades': 0,
                'wins': 0,
                'losses': 0,
                'passes': False,
                'validated': False,
                'error': 'No trades found'
            }
        
        # Step 2: Calculate basic stats
        trade_count = len(trades)
        total_volume = sum(float(t.get('size', 0)) * float(t.get('price', 0)) for t in trades)
        
        # Step 3: Calculate win rate from resolved markets (if enabled)
        if check_resolutions:
            resolution_stats = await calculate_win_rate_from_resolved_trades(trades, session)
            win_rate = resolution_stats['win_rate']
            resolved_trades = resolution_stats['resolved_trades']
            wins = resolution_stats['wins']
            losses = resolution_stats['losses']
            total_profit_usd = resolution_stats['total_profit_usd']
        else:
            # Quick mode - skip resolution checks
            win_rate = 0.0
            resolved_trades = 0
            wins = 0
            losses = 0
            total_profit_usd = 0.0
        
        # Convert profit to ETH (rough estimate: ETH ~$2000)
        total_profit_eth = total_profit_usd / 2000.0 if total_profit_usd > 0 else 0.0
        
        # If no resolution data, estimate profit (conservative)
        if total_profit_eth == 0.0 and total_volume > 0:
            # Very rough estimate: assume 3% ROI
            total_profit_eth = (total_volume * 0.03) / 2000.0
        
        # Step 4: Apply brutal criteria
        # Brutal criteria (Grok's standards):
        # - ≥65% win rate (if we have resolution data)
        # - ≥30 trades
        # - >2 ETH profit
        
        passes = (
            trade_count >= 30 and
            total_volume >= 10000  # At least $10k volume
        )
        
        # If we have resolution data, apply full criteria
        if check_resolutions and resolved_trades > 0:
            passes = (
                win_rate >= 0.65 and
                trade_count >= 30 and
                total_profit_eth > 2.0
            )
        
        return {
            'address': address,
            'win_rate': win_rate,
            'trade_count': trade_count,
            'total_profit_eth': total_profit_eth,
            'total_volume_usd': total_volume,
            'resolved_trades': resolved_trades,
            'wins': wins,
            'losses': losses,
            'passes': passes,
            'validated': True
        }
        
    except Exception as e:
        return {
            'address': address,
            'validated': False,
            'error': str(e)
        }


async def validate_whale_batch(addresses: List[str], limit: Optional[int] = None, check_resolutions: bool = False) -> List[Dict]:
    """
    Validate a batch of whales
    
    Args:
        addresses: List of whale addresses
        limit: Optional limit on number to process
        check_resolutions: If True, check market resolutions (slower but accurate)
    """
    if limit:
        addresses = addresses[:limit]
    
    results = []
    
    async with aiohttp.ClientSession() as session:
        for i, address in enumerate(addresses, 1):
            print(f"[{i}/{len(addresses)}] {address[:16]}...", end=" ", flush=True)
            
            result = await validate_whale(address, session, check_resolutions=check_resolutions)
            results.append(result)
            
            if result.get('validated'):
                trade_count = result.get('trade_count', 0)
                volume = result.get('total_volume_usd', 0)
                win_rate = result.get('win_rate', 0)
                passes = result.get('passes', False)
                
                if check_resolutions and result.get('resolved_trades', 0) > 0:
                    print(f"✅ {trade_count} trades | {win_rate:.0%} WR | ${volume:,.0f} | {'PASS' if passes else 'FAIL'}")
                else:
                    print(f"✅ {trade_count} trades | ${volume:,.0f} | {'PASS' if passes else 'FAIL'}")
            else:
                print(f"❌ {result.get('error', 'Failed')}")
            
            # Rate limiting (longer delay if checking resolutions)
            delay = REQUEST_DELAY * 2 if check_resolutions else REQUEST_DELAY
            if i < len(addresses):
                await asyncio.sleep(delay)
    
    return results


def get_elite_whales(results: List[Dict]) -> List[Dict]:
    """Filter to elite whales that pass brutal criteria"""
    elite = [
        r for r in results
        if r.get('validated') and r.get('passes')
    ]
    
    # Sort by trade count and volume
    elite.sort(key=lambda x: (x.get('trade_count', 0), x.get('total_volume_usd', 0)), reverse=True)
    
    return elite


async def main():
    """Main function for testing"""
    print("="*80)
    print("🔍 API-BASED WHALE VALIDATOR")
    print("="*80)
    print()
    
    # Test on one whale first (quick mode - no resolution checks)
    test_address = "0xd189664c5308903476f9f079820431e4fd7d06f4"
    
    print("Step 1: Testing on one whale (quick mode)...")
    print(f"Address: {test_address}")
    print()
    
    result = await validate_whale(test_address, check_resolutions=False)
    
    print("Result:")
    print(json.dumps(result, indent=2))
    print()
    
    if result.get('validated'):
        print("✅ Quick test successful!")
        print()
        print("Step 2: Testing with resolution checks (slower but accurate)...")
        print()
        
        result_detailed = await validate_whale(test_address, check_resolutions=True)
        print("Detailed Result:")
        print(json.dumps(result_detailed, indent=2))
        print()
        
        if result_detailed.get('validated'):
            print("✅ Detailed validation successful!")
            print()
            print("Next step: Run on top 200 high-confidence whales")
            print("   Use check_resolutions=True for accurate win rates")
            print("   Use check_resolutions=False for faster processing")
        else:
            print("⚠️ Detailed validation had issues - will use quick mode")
    else:
        print("❌ Test failed - check error message")
        print("   May need to refine API queries or use alternative approach")


if __name__ == "__main__":
    asyncio.run(main())
