"""
Market Scanner - Scans Polymarket for active markets
Shows breakdown by category and displays top markets by liquidity
"""

import asyncio
import aiohttp
from datetime import datetime
from collections import defaultdict
from typing import Dict, List

GAMMA_API_BASE = "https://gamma-api.polymarket.com"


async def fetch_markets(session: aiohttp.ClientSession, limit: int = 100) -> List[Dict]:
    """Fetch active markets from Polymarket"""
    try:
        url = f"{GAMMA_API_BASE}/markets?closed=false&limit={limit}"
        
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status == 200:
                data = await response.json()
                # Handle both list and dict responses
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and 'data' in data:
                    return data['data']
                elif isinstance(data, dict) and 'markets' in data:
                    return data['markets']
                else:
                    return []
            else:
                print(f"❌ API returned status {response.status}")
                return []
    except Exception as e:
        print(f"❌ Error fetching markets: {e}")
        return []


def categorize_markets(markets: List[Dict]) -> Dict[str, List[Dict]]:
    """Group markets by category"""
    categories = defaultdict(list)
    
    for market in markets:
        category = market.get('category', 'Unknown')
        if not category or category == '':
            category = 'Unknown'
        
        categories[category].append(market)
    
    return dict(categories)


def calculate_liquidity(market: Dict) -> float:
    """Calculate market liquidity score"""
    try:
        # Try different liquidity fields
        liquidity = market.get('liquidity', 0)
        if liquidity:
            return float(liquidity)
        
        volume = market.get('volume', 0)
        if volume:
            return float(volume)
        
        # Try volume24h
        volume24h = market.get('volume24h', market.get('volume_24h', 0))
        if volume24h:
            return float(volume24h)
        
        return 0.0
    except (ValueError, TypeError):
        return 0.0


def format_market_summary(market: Dict) -> str:
    """Format a single market for display"""
    question = market.get('question', market.get('title', 'Unknown'))[:60]
    liquidity = calculate_liquidity(market)
    liquidity_str = f"${liquidity:,.0f}" if liquidity > 0 else "N/A"
    
    # Get end date
    end_date = market.get('endDate', market.get('end_date', ''))
    if end_date:
        try:
            if isinstance(end_date, str):
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                days_left = (end_dt - datetime.now(end_dt.tzinfo)).days
                time_str = f"{days_left}d left" if days_left > 0 else "Expired"
            else:
                time_str = "Unknown"
        except:
            time_str = "Unknown"
    else:
        time_str = "Unknown"
    
    return f"   • {question} | Liquidity: {liquidity_str} | {time_str}"


def get_activity_level(market_count: int) -> tuple:
    """Determine activity level based on market count"""
    if market_count >= 15:
        return "🟢 HIGH", "Very active"
    elif market_count >= 10:
        return "🟡 MODERATE", "Moderate activity"
    elif market_count >= 5:
        return "🟠 LOW", "Low activity"
    else:
        return "🔴 VERY LOW", "Very low activity"


async def scan_markets():
    """Main scanning function"""
    print("\n" + "="*100)
    print("📊 POLYMARKET MARKET SCANNER")
    print("="*100)
    print("\nScanning active markets...\n")
    
    async with aiohttp.ClientSession() as session:
        # Fetch markets
        markets = await fetch_markets(session, limit=200)
        
        if not markets:
            print("❌ No markets found or API error")
            return
        
        print(f"✅ Found {len(markets)} active markets\n")
        
        # Categorize
        categories = categorize_markets(markets)
        
        # Sort categories by count
        sorted_categories = sorted(
            categories.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        
        # Display by category
        print("="*100)
        print("📈 MARKETS BY CATEGORY")
        print("="*100)
        print()
        
        category_icons = {
            'sports': '🏈',
            'politics': '🗳️',
            'economics': '💰',
            'crypto': '🪙',
            'entertainment': '🎬',
            'technology': '💻',
            'weather': '🌤️',
            'unknown': '❓'
        }
        
        for category, category_markets in sorted_categories:
            icon = category_icons.get(category.lower(), '📊')
            level, desc = get_activity_level(len(category_markets))
            
            print(f"{icon} {category.title()}: {len(category_markets)} markets ({level} {desc})")
            
            # Show top 3 markets by liquidity
            sorted_markets = sorted(
                category_markets,
                key=calculate_liquidity,
                reverse=True
            )
            
            for market in sorted_markets[:3]:
                print(format_market_summary(market))
            
            print()
        
        # Overall summary
        print("="*100)
        print("📊 OVERALL ACTIVITY SUMMARY")
        print("="*100)
        print()
        
        total_markets = len(markets)
        total_categories = len(categories)
        avg_per_category = total_markets / total_categories if total_categories > 0 else 0
        
        level, desc = get_activity_level(total_markets)
        
        print(f"Total Active Markets: <b>{total_markets}</b>")
        print(f"Categories: {total_categories}")
        print(f"Average per Category: {avg_per_category:.1f}")
        print(f"Overall Activity: {level} {desc}")
        print()
        
        # Top markets by liquidity
        print("="*100)
        print("🏆 TOP 10 MARKETS BY LIQUIDITY")
        print("="*100)
        print()
        
        sorted_by_liquidity = sorted(
            markets,
            key=calculate_liquidity,
            reverse=True
        )
        
        for i, market in enumerate(sorted_by_liquidity[:10], 1):
            question = market.get('question', market.get('title', 'Unknown'))[:70]
            liquidity = calculate_liquidity(market)
            category = market.get('category', 'Unknown')
            
            liquidity_str = f"${liquidity:,.0f}" if liquidity > 0 else "N/A"
            
            print(f"{i:2d}. {question}")
            print(f"    Category: {category} | Liquidity: {liquidity_str}")
            print()
        
        # Contextual message
        print("="*100)
        print("💡 CONTEXT")
        print("="*100)
        print()
        
        day_of_week = datetime.now().strftime("%A")
        hour = datetime.now().hour
        
        if day_of_week in ['Saturday', 'Sunday']:
            print("📅 Weekend - Typically higher activity")
        elif day_of_week in ['Monday', 'Friday']:
            print("📅 Weekday - Moderate activity expected")
        else:
            print("📅 Midweek - Lower activity typical")
        
        if hour >= 9 and hour < 17:
            print("⏰ Business hours - Normal activity")
        elif hour >= 17 and hour < 22:
            print("⏰ Evening - Peak trading hours")
        else:
            print("⏰ Off-hours - Lower activity")
        
        print()
        
        if total_markets < 30:
            print("⚠️  Low market count detected.")
            print("   This explains why whales may not be trading actively.")
            print("   Activity typically increases:")
            print("   • Weekends (more sports events)")
            print("   • Major news events")
            print("   • Economic data releases")
            print("   • Crypto volatility periods")
        else:
            print("✅ Good market activity detected!")
            print("   Whales should have trading opportunities.")
        
        print()


if __name__ == "__main__":
    try:
        asyncio.run(scan_markets())
    except KeyboardInterrupt:
        print("\n\n⏸️  Scan stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
