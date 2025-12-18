"""
Get Wallet Address from Polymarket Username
============================================
Converts @username to 0x... wallet address

Usage:
  python scripts/get_whale_address.py gabagool22
  python scripts/get_whale_address.py ExpressoMartini
"""

import sys
import asyncio
import aiohttp
import re
from pathlib import Path


async def get_wallet_from_username(username: str) -> dict:
    """
    Fetch wallet address from Polymarket profile page
    """
    
    # Clean username
    username = username.replace('@', '').strip()
    
    print(f"\n🔍 Looking up: @{username}")
    print(f"📄 URL: https://polymarket.com/@{username}")
    print()
    
    url = f"https://polymarket.com/@{username}"
    
    async with aiohttp.ClientSession() as session:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 404:
                    return {
                        "success": False,
                        "error": "Profile not found - check username spelling",
                        "username": username
                    }
                
                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}",
                        "username": username
                    }
                
                html = await response.text()
                
                # Method 1: Find wallet address in HTML
                # Ethereum addresses are 42 characters starting with 0x
                addresses = re.findall(r'0x[a-fA-F0-9]{40}', html)
                
                if addresses:
                    # Return first address found (usually the profile wallet)
                    address = addresses[0]
                    
                    print(f"✅ Found wallet address!")
                    print(f"   Username: @{username}")
                    print(f"   Address:  {address}")
                    print(f"   Short:    {address[:6]}...{address[-4:]}")
                    print()
                    
                    # Try to get positions count
                    positions_url = f"https://clob.polymarket.com/positions/{address}"
                    async with session.get(positions_url, timeout=aiohttp.ClientTimeout(total=10)) as pos_response:
                        if pos_response.status == 200:
                            positions = await pos_response.json()
                            if isinstance(positions, list):
                                active = sum(1 for p in positions if float(p.get('size', 0)) > 0)
                                print(f"📊 Activity Check:")
                                print(f"   Total Positions: {len(positions)}")
                                print(f"   Active Now: {active}")
                                print()
                    
                    return {
                        "success": True,
                        "username": username,
                        "address": address,
                        "profile_url": f"https://polymarket.com/@{username}"
                    }
                else:
                    print("⚠️ No wallet address found in profile HTML")
                    print("   This might mean:")
                    print("   • Username is correct but page structure changed")
                    print("   • Profile is private or restricted")
                    print("   • Need to use different method")
                    print()
                    
                    return {
                        "success": False,
                        "error": "No wallet address found in profile",
                        "username": username
                    }
                
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Request timeout - try again",
                "username": username
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "username": username
            }


async def main():
    """Main entry point"""
    
    print("\n" + "="*80)
    print("🔎 POLYMARKET USERNAME → WALLET ADDRESS LOOKUP")
    print("="*80)
    
    if len(sys.argv) < 2:
        print("\n❌ ERROR: No username provided!")
        print()
        print("Usage:")
        print("  python scripts/get_whale_address.py gabagool22")
        print("  python scripts/get_whale_address.py ExpressoMartini")
        print()
        print("Or lookup multiple:")
        print("  python scripts/get_whale_address.py gabagool22 ExpressoMartini")
        print()
        return
    
    usernames = sys.argv[1:]
    
    results = []
    for username in usernames:
        result = await get_wallet_from_username(username)
        results.append(result)
        
        if len(usernames) > 1:
            await asyncio.sleep(1)  # Delay between requests
    
    # Summary
    if len(results) > 1:
        print("="*80)
        print("📋 SUMMARY")
        print("="*80)
        print()
        
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        
        if successful:
            print(f"✅ Found {len(successful)} address(es):")
            for r in successful:
                print(f"   @{r['username']:<20} → {r['address']}")
            print()
        
        if failed:
            print(f"❌ Failed {len(failed)} lookup(s):")
            for r in failed:
                print(f"   @{r['username']:<20} → {r['error']}")
            print()
    
    # Offer to add to whale list
    successful = [r for r in results if r['success']]
    if successful:
        print("="*80)
        print("💡 NEXT STEPS")
        print("="*80)
        print()
        print("To add these whales to your bot:")
        print()
        print("1. Manual method:")
        print("   • Open config/whale_list.json")
        print("   • Add these addresses to the 'whales' array")
        print("   • Restart your bot")
        print()
        print("2. Or use the add script:")
        print("   • python scripts/add_active_whales.py")
        print()
        
        # Generate JSON snippet
        print("📄 JSON to add:")
        print()
        for r in successful:
            print(f'''{{
  "address": "{r['address']}",
  "name": "{r['username']}",
  "source": "Manual lookup",
  "url": "{r['profile_url']}",
  "added": "2025-12-18"
}},''')
        print()


if __name__ == "__main__":
    asyncio.run(main())
