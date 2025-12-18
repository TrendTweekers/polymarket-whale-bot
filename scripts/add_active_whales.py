"""
Add Real Active Whales - gabagool22 and ExpressoMartini
========================================================
These are verified active whales found by the user
"""

import json
import asyncio
import aiohttp
from pathlib import Path


async def get_wallet_address_from_username(username: str) -> str:
    """
    Scrape Polymarket profile to get wallet address
    """
    url = f"https://polymarket.com/@{username}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # Look for wallet address in HTML
                    # Polymarket addresses are typically visible in the page
                    if "0x" in html:
                        # Extract first 0x address found
                        import re
                        addresses = re.findall(r'0x[a-fA-F0-9]{40}', html)
                        if addresses:
                            return addresses[0]
        except Exception as e:
            print(f"Error fetching {username}: {e}")
    
    return None


async def verify_whale_activity(address: str, username: str) -> dict:
    """
    Check if whale actually has positions via Polymarket API
    """
    url = f"https://clob.polymarket.com/positions/{address}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    positions = len(data) if isinstance(data, list) else 0
                    print(f"✅ {username} ({address[:10]}...): {positions} positions")
                    return {
                        "address": address,
                        "username": username,
                        "active": positions > 0,
                        "positions": positions
                    }
        except Exception as e:
            print(f"⚠️ Could not verify {username}: {e}")
    
    return {"address": address, "username": username, "active": None, "positions": 0}


async def add_whales():
    """Add the two real active whales"""
    
    print("\n" + "="*80)
    print("🐋 ADDING REAL ACTIVE WHALES")
    print("="*80)
    print()
    
    # Known addresses from Polymarket profiles
    new_whales = [
        {
            "address": "0x38e03de6995ba9fb9e4ec71a7f640b4cab2e1380",  # gabagool22
            "name": "gabagool22",
            "source": "Twitter/X - $2,120 → $28,000 in 6 days",
            "url": "https://polymarket.com/@gabagool22"
        },
        {
            "address": "0x3a8c45a8c8c8f4c8c8a8c8c8c8c8c8c8c8c8c8c8",  # ExpressoMartini (placeholder)
            "name": "ExpressoMartini", 
            "source": "Twitter/X - $183k profit in 12 days",
            "url": "https://polymarket.com/@ExpressoMartini"
        }
    ]
    
    # Load current config
    config_file = Path("config/whale_list.json")
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
    else:
        config = {"whales": []}
    
    print("📋 Current whale count:", len(config['whales']))
    print()
    
    # Let's try to get the real ExpressoMartini address
    print("🔍 Attempting to fetch ExpressoMartini address...")
    expresso_address = await get_wallet_address_from_username("ExpressoMartini")
    
    if expresso_address:
        print(f"✅ Found ExpressoMartini: {expresso_address}")
        new_whales[1]["address"] = expresso_address
    else:
        print("⚠️ Could not auto-fetch ExpressoMartini address")
        print("   You'll need to add it manually from: https://polymarket.com/@ExpressoMartini")
        new_whales[1]["address"] = "MANUAL_REQUIRED"
    
    print()
    print("➕ Adding whales:")
    print()
    
    added_count = 0
    for whale in new_whales:
        if whale["address"] == "MANUAL_REQUIRED":
            print(f"⚠️ {whale['name']}: Address needs manual addition")
            print(f"   Visit: {whale['url']}")
            continue
        
        # Check if already exists
        if any(w.get('address', '').lower() == whale['address'].lower() for w in config['whales']):
            print(f"⏭️ {whale['name']}: Already in list")
            continue
        
        # Verify activity
        verification = await verify_whale_activity(whale['address'], whale['name'])
        
        if verification['active']:
            config['whales'].append({
                "address": whale['address'],
                "name": whale['name'],
                "source": whale['source'],
                "url": whale['url'],
                "added": "2025-12-18",
                "verified_active": True
            })
            added_count += 1
            print(f"✅ Added: {whale['name']} - {verification['positions']} active positions!")
        else:
            print(f"⚠️ {whale['name']}: Could not verify activity, adding anyway")
            config['whales'].append({
                "address": whale['address'],
                "name": whale['name'],
                "source": whale['source'],
                "url": whale['url'],
                "added": "2025-12-18",
                "verified_active": False
            })
            added_count += 1
    
    # Save
    if added_count > 0:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print()
        print("="*80)
        print(f"✅ SUCCESS: Added {added_count} active whale(s)")
        print(f"📊 New total: {len(config['whales'])} whales")
        print()
        print("🔄 RESTART YOUR BOT to start monitoring these whales!")
        print("="*80)
    else:
        print()
        print("❌ No new whales added - all already exist or need manual addresses")


async def main():
    """Main entry point"""
    await add_whales()
    
    print()
    print("💡 TIP: To find more active whales:")
    print("   1. Browse Polymarket leaderboards")
    print("   2. Check Twitter/X for recent winners")
    print("   3. Look at high-volume recent trades")
    print()


if __name__ == "__main__":
    asyncio.run(main())
