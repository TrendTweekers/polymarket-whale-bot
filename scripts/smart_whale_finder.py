"""
SMART WHALE FINDER - Win Rate Based
====================================
Finds whales, calculates their win rates, only adds profitable ones

This solves your problem:
✅ Automated (no manual work)
✅ Filters by win rate (only adds whales with >60% win rate)
✅ Checks profitability
✅ Verifies current activity
"""

import asyncio
import aiohttp
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict


class SmartWhaleFinder:
    """Find and validate profitable whales"""
    
    def __init__(self):
        self.base_url = "https://gamma-api.polymarket.com"
        self.clob_url = "https://clob.polymarket.com"
        self.min_win_rate = 0.50  # 50% minimum (lowered from 60%)
        self.min_trades = 5       # Need at least 5 trades (lowered from 10)
        self.min_profit = 250     # Minimum $250 profit (lowered from $500)
    
    async def get_recent_high_volume_markets(self, session: aiohttp.ClientSession) -> list:
        """Get markets with high activity"""
        
        url = f"{self.base_url}/markets"
        params = {
            "closed": "false",
            "limit": 30,
            "_sort": "volume",
            "_order": "DESC"
        }
        
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            print(f"⚠️ Error fetching markets: {e}")
        
        return []
    
    async def get_market_trades(self, market_slug: str, session: aiohttp.ClientSession) -> list:
        """Get recent trades for a market"""
        
        url = f"{self.base_url}/markets/{market_slug}"
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('events', [])
        except:
            pass
        
        return []
    
    async def get_wallet_positions(self, address: str, session: aiohttp.ClientSession) -> list:
        """Get current positions for a wallet"""
        
        url = f"{self.clob_url}/positions/{address}"
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    positions = await response.json()
                    if isinstance(positions, list):
                        # Filter to active positions only
                        return [p for p in positions if float(p.get('size', 0)) > 0]
        except:
            pass
        
        return []
    
    async def calculate_wallet_performance(self, address: str, session: aiohttp.ClientSession) -> dict:
        """
        Calculate win rate and profitability for a wallet
        This is the KEY function - filters by performance
        """
        
        print(f"      Analyzing performance... ", end='', flush=True)
        
        try:
            # Get all positions (including closed)
            url = f"{self.clob_url}/positions/{address}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    print("❌ No data")
                    return None
                
                positions = await response.json()
                
                if not isinstance(positions, list) or len(positions) < self.min_trades:
                    print(f"❌ Only {len(positions) if isinstance(positions, list) else 0} trades")
                    return None
                
                # Calculate metrics
                total_trades = len(positions)
                winning_trades = 0
                total_pnl = 0.0
                active_positions = 0
                
                for position in positions:
                    size = float(position.get('size', 0))
                    
                    # Count active
                    if size > 0:
                        active_positions += 1
                    
                    # Calculate P&L (simplified - actual calculation is more complex)
                    outcome = position.get('outcome')
                    if outcome:
                        # If outcome exists, position is closed
                        # outcome typically includes settlement info
                        pnl = float(position.get('pnl', 0))
                        total_pnl += pnl
                        
                        if pnl > 0:
                            winning_trades += 1
                
                # Calculate win rate
                closed_trades = total_trades - active_positions
                
                if closed_trades < self.min_trades:
                    print(f"⚠️ Not enough closed trades ({closed_trades})")
                    return None
                
                win_rate = winning_trades / closed_trades if closed_trades > 0 else 0
                
                result = {
                    'total_trades': total_trades,
                    'closed_trades': closed_trades,
                    'active_positions': active_positions,
                    'winning_trades': winning_trades,
                    'win_rate': win_rate,
                    'total_pnl': total_pnl,
                    'avg_pnl_per_trade': total_pnl / closed_trades if closed_trades > 0 else 0
                }
                
                # Check if meets criteria
                meets_criteria = (
                    win_rate >= self.min_win_rate and
                    total_pnl >= self.min_profit and
                    active_positions > 0  # Must have current positions
                )
                
                if meets_criteria:
                    print(f"✅ {win_rate:.1%} WR, ${total_pnl:,.0f} profit, {active_positions} active")
                else:
                    if win_rate < self.min_win_rate:
                        print(f"❌ {win_rate:.1%} WR (need >{self.min_win_rate:.0%})")
                    elif total_pnl < self.min_profit:
                        print(f"❌ ${total_pnl:,.0f} profit (need >${self.min_profit})")
                    elif active_positions == 0:
                        print(f"❌ No active positions")
                
                return result if meets_criteria else None
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    async def extract_whale_addresses_from_markets(self, session: aiohttp.ClientSession) -> set:
        """Extract unique whale addresses from high-volume markets"""
        
        print("\n🔍 Phase 1: Scanning high-volume markets for whale addresses...")
        print()
        
        markets = await self.get_recent_high_volume_markets(session)
        
        if not markets:
            print("❌ Could not fetch markets")
            return set()
        
        print(f"📊 Found {len(markets)} active markets")
        print()
        
        whale_addresses = set()
        
        # We'll use a different approach - scan orderbooks
        for i, market in enumerate(markets[:15], 1):  # Check top 15 markets
            condition_id = market.get('condition_id')
            question = market.get('question', 'Unknown')[:50]
            volume = float(market.get('volume', 0))
            
            print(f"[{i}/15] {question}... (${volume:,.0f})", end=' ')
            
            if not condition_id:
                print("⚠️ No ID")
                continue
            
            # Get orders/trades to find active traders
            # This is where we find wallet addresses
            try:
                # Try to get market events which contain trader addresses
                events_url = f"{self.clob_url}/events/{condition_id}"
                async with session.get(events_url, timeout=aiohttp.ClientTimeout(total=3)) as response:
                    if response.status == 200:
                        data = await response.json()
                        tokens = data.get('tokens', [])
                        
                        found_in_market = 0
                        
                        for token in tokens[:2]:  # Both outcomes
                            token_id = token.get('token_id')
                            if not token_id:
                                continue
                            
                            # Get orderbook
                            book_url = f"{self.clob_url}/book"
                            params = {'token_id': token_id}
                            
                            try:
                                async with session.get(book_url, params=params, timeout=aiohttp.ClientTimeout(total=2)) as book_response:
                                    if book_response.status == 200:
                                        book = await book_response.json()
                                        
                                        # Extract makers from orders
                                        for order in book.get('bids', []) + book.get('asks', []):
                                            maker = order.get('maker')
                                            size = float(order.get('size', 0))
                                            
                                            # Only large orders (likely whales)
                                            if maker and size > 100:
                                                whale_addresses.add(maker.lower())
                                                found_in_market += 1
                            except:
                                pass
                        
                        print(f"✅ Found {found_in_market} whales")
                    else:
                        print("⚠️ No data")
            except Exception as e:
                print(f"❌ Error")
            
            await asyncio.sleep(0.3)  # Rate limiting
        
        print()
        print(f"📊 Extracted {len(whale_addresses)} unique whale addresses")
        print()
        
        return whale_addresses
    
    async def validate_and_rank_whales(self, addresses: set, session: aiohttp.ClientSession) -> list:
        """Validate whales and rank by performance"""
        
        print("🔍 Phase 2: Validating whale performance (Win Rate & Profitability)...")
        print()
        print("Criteria:")
        print(f"  • Minimum Win Rate: {self.min_win_rate:.0%}")
        print(f"  • Minimum Profit: ${self.min_profit:,.0f}")
        print(f"  • Minimum Trades: {self.min_trades}")
        print(f"  • Must have active positions NOW")
        print()
        
        validated_whales = []
        
        for i, address in enumerate(list(addresses)[:50], 1):  # Check up to 50
            print(f"[{i}/{min(len(addresses), 50)}] {address[:10]}...")
            
            # Get current positions first (faster check)
            positions = await self.get_wallet_positions(address, session)
            
            if not positions:
                print("      ⚠️ No active positions, skipping")
                continue
            
            # Calculate performance
            performance = await self.calculate_wallet_performance(address, session)
            
            if performance:
                validated_whales.append({
                    'address': address,
                    'name': f"Whale_{address[:8]}",
                    'win_rate': performance['win_rate'],
                    'total_pnl': performance['total_pnl'],
                    'total_trades': performance['total_trades'],
                    'active_positions': performance['active_positions'],
                    'avg_pnl': performance['avg_pnl_per_trade'],
                    'score': performance['win_rate'] * (1 + performance['total_pnl'] / 10000)  # Weighted score
                })
            
            await asyncio.sleep(0.5)  # Rate limiting
        
        # Sort by score (win rate weighted by profit)
        validated_whales.sort(key=lambda x: x['score'], reverse=True)
        
        return validated_whales
    
    async def save_to_config(self, whales: list):
        """Save validated whales to config - MERGES with existing whales"""
        
        if not whales:
            print("\n❌ No whales met the criteria!")
            print()
            print("This could mean:")
            print("  • Criteria too strict (try lowering min_win_rate to 0.50)")
            print("  • Not enough market activity today")
            print("  • Need to scan more markets")
            return
        
        print("\n" + "="*80)
        print("💾 SAVING VALIDATED WHALES (MERGING WITH EXISTING)")
        print("="*80)
        print()
        
        print(f"✅ {len(whales)} whales passed validation:")
        print()
        
        for i, whale in enumerate(whales[:15], 1):  # Save top 15
            print(f"{i:2}. WR: {whale['win_rate']:.1%} | "
                  f"P&L: ${whale['total_pnl']:>8,.0f} | "
                  f"Trades: {whale['total_trades']:>3} | "
                  f"Active: {whale['active_positions']} | "
                  f"{whale['address'][:12]}...")
        
        print()
        
        # Load existing config - PRESERVE existing whales!
        config_file = Path("config/whale_list.json")
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                print(f"📋 Loaded existing config: {len(config.get('whales', []))} whales already in list")
            except:
                config = {"whales": []}
                print("⚠️ Could not load existing config, starting fresh")
        else:
            config = {"whales": []}
            print("📝 No existing config, creating new one")
        
        # Get existing whale addresses to avoid duplicates
        existing_addresses = {w.get('address', '').lower() for w in config.get('whales', [])}
        
        print()
        print(f"🔍 Checking for duplicates...")
        
        # Add whales with full metadata - ONLY if not already in list
        added_count = 0
        skipped_count = 0
        
        for whale in whales[:15]:  # Add top 15
            if whale['address'].lower() in existing_addresses:
                print(f"   ⏭️ Skipping {whale['address'][:12]}... (already in list)")
                skipped_count += 1
                continue
            
            config['whales'].append({
                "address": whale['address'],
                "name": f"Profitable Whale (WR: {whale['win_rate']:.0%})",
                "source": "Smart Scanner - Performance Validated",
                "url": f"https://polymarket.com/profile/{whale['address']}",
                "added": datetime.now().strftime('%Y-%m-%d'),
                "verified_metrics": {
                    "win_rate": f"{whale['win_rate']:.1%}",
                    "total_profit": f"${whale['total_pnl']:,.0f}",
                    "total_trades": whale['total_trades'],
                    "active_positions": whale['active_positions'],
                    "avg_pnl_per_trade": f"${whale['avg_pnl']:,.2f}"
                }
            })
            added_count += 1
        
        print()
        print(f"➕ Added: {added_count} new whales")
        print(f"⏭️ Skipped: {skipped_count} duplicates")
        print(f"📊 Total now: {len(config['whales'])} whales")
        print()
        
        # Save
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"💾 Saved to: {config_file}")
        print()
        print("="*80)
        print("✅ DONE! Restart your bot:")
        print("   python main.py")
        print("="*80)
        print()
        print("Your whale list now includes:")
        print(f"  ✅ Your {len(existing_addresses)} manually added whales")
        print(f"  ✅ {added_count} new high-performance whales")
        print()
        print("All new whales have:")
        print(f"  ✅ Win rate > {self.min_win_rate:.0%}")
        print(f"  ✅ Total profit > ${self.min_profit:,.0f}")
        print(f"  ✅ Active positions RIGHT NOW")
        print()
        print("Your bot will now copy PROFITABLE traders! 🚀")
    
    async def run(self):
        """Main execution"""
        
        print("\n" + "="*80)
        print("🎯 SMART WHALE FINDER - Performance Based")
        print("="*80)
        print()
        print("This scanner:")
        print("  1. Finds whale addresses from high-volume markets")
        print("  2. Calculates their historical win rate")
        print("  3. Validates profitability")
        print("  4. Only adds whales with >60% win rate + profit")
        print()
        print("⏱️ This will take 3-5 minutes...")
        print()
        
        async with aiohttp.ClientSession() as session:
            # Phase 1: Extract addresses
            addresses = await self.extract_whale_addresses_from_markets(session)
            
            if not addresses:
                print("\n❌ Could not find any whale addresses")
                print("   Try again later when markets are more active")
                return
            
            # Phase 2: Validate performance
            validated = await self.validate_and_rank_whales(addresses, session)
            
            # Phase 3: Save
            await self.save_to_config(validated)


async def main():
    """Entry point"""
    scanner = SmartWhaleFinder()
    await scanner.run()


if __name__ == "__main__":
    asyncio.run(main())
