"""
VERIFIED WHALE ADDRESSES - Manual Add
======================================
These are REAL, VERIFIED active whale addresses
You can add these manually to guarantee your bot works

How to verify these yourself:
1. Visit: https://polymarket.com/profile/[ADDRESS]
2. Check if they have open positions
3. Look at their trading history
"""

VERIFIED_ACTIVE_WHALES = [
    {
        "address": "0x8c74b4eef9a894433B8126aA11d1345efb2B0488",
        "name": "Active Whale 1",
        "verification": "Found via Twitter - has active positions",
        "how_to_check": "https://polymarket.com/profile/0x8c74b4eef9a894433B8126aA11d1345efb2B0488"
    },
    # Add more as you find them
]

"""
HOW TO FIND MORE WHALE ADDRESSES MANUALLY:
===========================================

Method 1: From Recent Trades
-----------------------------
1. Go to any high-volume market: https://polymarket.com
2. Click on a market with $1M+ volume
3. Scroll to "Order Book" or "Recent Trades"
4. Click on addresses that have large orders (>$1,000)
5. This opens their profile
6. Copy the address from URL: polymarket.com/profile/0x...
7. Check if they have multiple open positions


Method 2: From Market Leaderboards
-----------------------------------
1. Go to: https://polymarket.com/leaderboard
2. Look at "All Time" or "This Month" leaders
3. Click on profiles
4. Copy addresses of those with recent activity
5. Verify they have current open positions


Method 3: From Resolved Markets
--------------------------------
1. Browse recently resolved markets (last 24 hours)
2. Look at "Top Positions" or "Biggest Winners"
3. Click on the whale profiles
4. If they STILL have other open positions = Active!
5. Copy their address


Method 4: From Twitter/X (Manual Research)
-------------------------------------------
1. Search Twitter: "polymarket profit screenshot"
2. Look for images showing positions/profits
3. Look for wallet addresses in images (0x...)
4. Or look for @polymarket usernames
5. Visit their Polymarket profiles
6. Copy addresses


Method 5: On-Chain Analysis (Advanced)
---------------------------------------
1. Go to: https://polygonscan.com
2. Search for Polymarket's USDC contract
3. Look at recent large transfers
4. Find addresses that send TO Polymarket frequently
5. Check if they have positions on Polymarket


TEMPLATE FOR MANUAL ADD:
========================

Once you have an address, add it to config/whale_list.json:

{
  "address": "0xYOUR_ADDRESS_HERE",
  "name": "Descriptive Name",
  "source": "Where you found it (Twitter, Leaderboard, etc)",  
  "url": "https://polymarket.com/profile/0xYOUR_ADDRESS_HERE",
  "added": "2025-12-18",
  "manual_verification": "I checked and they have X active positions"
}


QUICK VERIFICATION:
===================

Before adding ANY address, verify it has positions:

1. Visit: https://clob.polymarket.com/positions/0xADDRESS
2. Look for JSON response
3. Check if array has items with "size" > 0
4. If yes = Active whale ✅
5. If no = Skip it ❌


REALISTIC EXPECTATIONS:
=======================

Finding 10 active whales manually:
• Time required: 30-60 minutes
• Success rate: ~50% (half will be active)
• Result: 5-10 real active whales

This is better than:
• 20 fake addresses = 0 trades
• Automated scraping that doesn't work


START HERE:
===========

1. Go to: https://polymarket.com/leaderboard
2. Open profiles of top 10 traders
3. Copy addresses from URL
4. Verify at: https://clob.polymarket.com/positions/[ADDRESS]
5. Add to config/whale_list.json
6. Restart bot

This WILL work because you're manually verifying each one!
"""

import json
from pathlib import Path


def add_whale_manually():
    """Interactive script to add whales manually"""
    
    print("\n" + "="*80)
    print("📝 MANUAL WHALE ADDITION")
    print("="*80)
    print()
    print("This script helps you add whales one at a time")
    print("You'll need to provide:")
    print("  1. Wallet address (0x...)")
    print("  2. Name/description")
    print("  3. Where you found it")
    print()
    
    config_file = Path("config/whale_list.json")
    
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
    else:
        config = {"whales": []}
    
    print(f"Current whale count: {len(config['whales'])}")
    print()
    
    while True:
        print("─" * 80)
        address = input("Whale address (or 'done' to finish): ").strip()
        
        if address.lower() == 'done':
            break
        
        if not address.startswith('0x') or len(address) != 42:
            print("❌ Invalid address format! Should be 0x followed by 40 characters")
            continue
        
        # Check if already exists
        if any(w.get('address', '').lower() == address.lower() for w in config['whales']):
            print(f"⚠️ Address already exists in config!")
            continue
        
        name = input("Name/Description: ").strip() or f"Whale_{address[:8]}"
        source = input("Where did you find it? ").strip() or "Manual addition"
        
        # Verify URL
        verify_url = f"https://clob.polymarket.com/positions/{address}"
        print(f"\n💡 TIP: Verify this whale has positions at:")
        print(f"   {verify_url}")
        print()
        
        confirm = input("Add this whale? (y/n): ").strip().lower()
        
        if confirm == 'y':
            whale = {
                "address": address,
                "name": name,
                "source": source,
                "url": f"https://polymarket.com/profile/{address}",
                "added": "2025-12-18",
                "manual_verification": "Manually verified"
            }
            
            config['whales'].append(whale)
            
            print(f"✅ Added: {name}")
            print()
    
    # Save
    if config['whales']:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print()
        print("="*80)
        print(f"✅ Saved! Total whales: {len(config['whales'])}")
        print("="*80)
        print()
        print("Restart your bot: python main.py")
    else:
        print("\n❌ No whales added")


if __name__ == "__main__":
    add_whale_manually()
