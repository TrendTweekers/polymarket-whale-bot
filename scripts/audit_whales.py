"""
Whale Activity Audit
====================
Check which of your current 20 whales are actually trading
Find the dead weight and replace them!
"""

import json
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime


async def check_whale_positions(address: str, name: str) -> dict:
    """
    Check if a whale has ANY positions on Polymarket
    """
    url = f"https://clob.polymarket.com/positions/{address}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    positions = await response.json()
                    
                    if isinstance(positions, list):
                        active_positions = [p for p in positions if float(p.get('size', 0)) > 0]
                        return {
                            "address": address,
                            "name": name,
                            "status": "ACTIVE" if active_positions else "INACTIVE",
                            "total_positions": len(positions),
                            "active_positions": len(active_positions),
                            "error": None
                        }
                    else:
                        return {
                            "address": address,
                            "name": name,
                            "status": "UNKNOWN",
                            "total_positions": 0,
                            "active_positions": 0,
                            "error": "Unexpected response format"
                        }
                elif response.status == 404:
                    return {
                        "address": address,
                        "name": name,
                        "status": "NO_DATA",
                        "total_positions": 0,
                        "active_positions": 0,
                        "error": "No positions found (never traded or wrong address)"
                    }
                else:
                    return {
                        "address": address,
                        "name": name,
                        "status": "ERROR",
                        "total_positions": 0,
                        "active_positions": 0,
                        "error": f"HTTP {response.status}"
                    }
        except asyncio.TimeoutError:
            return {
                "address": address,
                "name": name,
                "status": "TIMEOUT",
                "total_positions": 0,
                "active_positions": 0,
                "error": "Request timeout"
            }
        except Exception as e:
            return {
                "address": address,
                "name": name,
                "status": "ERROR",
                "total_positions": 0,
                "active_positions": 0,
                "error": str(e)
            }


async def audit_whales():
    """Audit all current whales"""
    
    print("\n" + "="*80)
    print("🔍 WHALE ACTIVITY AUDIT")
    print("="*80)
    print()
    print("Checking which of your 20 whales are actually trading...")
    print("This will take about 20-30 seconds...")
    print()
    
    # Load current whales
    config_file = Path("config/whale_list.json")
    if not config_file.exists():
        print("❌ ERROR: config/whale_list.json not found!")
        return
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    whales = config.get('whales', [])
    
    if not whales:
        print("❌ ERROR: No whales in configuration!")
        return
    
    print(f"📋 Auditing {len(whales)} whales...")
    print()
    
    # Check each whale
    results = []
    for i, whale in enumerate(whales, 1):
        address = whale.get('address', '')
        name = whale.get('name', f'Whale #{i}')
        
        print(f"[{i}/{len(whales)}] Checking {name[:30]:<30} ", end='', flush=True)
        
        result = await check_whale_positions(address, name)
        results.append(result)
        
        # Status indicator
        if result['status'] == 'ACTIVE':
            print(f"✅ ACTIVE ({result['active_positions']} positions)")
        elif result['status'] == 'INACTIVE':
            print(f"⚠️ INACTIVE (no positions)")
        elif result['status'] == 'NO_DATA':
            print(f"❌ NO DATA (bad address?)")
        elif result['status'] == 'ERROR':
            print(f"❌ ERROR: {result['error']}")
        else:
            print(f"⚠️ {result['status']}")
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)
    
    # Summary
    print()
    print("="*80)
    print("📊 AUDIT RESULTS")
    print("="*80)
    print()
    
    active = [r for r in results if r['status'] == 'ACTIVE']
    inactive = [r for r in results if r['status'] == 'INACTIVE']
    no_data = [r for r in results if r['status'] == 'NO_DATA']
    errors = [r for r in results if r['status'] in ['ERROR', 'TIMEOUT', 'UNKNOWN']]
    
    print(f"✅ ACTIVE:     {len(active):>2} whales   (Currently have positions)")
    print(f"⚠️ INACTIVE:   {len(inactive):>2} whales   (Valid but no positions)")
    print(f"❌ NO DATA:    {len(no_data):>2} whales   (Never traded / bad address)")
    print(f"❌ ERRORS:     {len(errors):>2} whales   (API errors)")
    print()
    
    # Details
    if active:
        print("🟢 ACTIVE WHALES (Keep these!):")
        for r in active:
            print(f"   • {r['name'][:40]:<40} - {r['active_positions']} positions")
        print()
    
    if inactive:
        print("🟡 INACTIVE WHALES (Temporarily idle):")
        for r in inactive:
            print(f"   • {r['name'][:40]}")
        print()
    
    if no_data:
        print("🔴 DEAD WHALES (Replace these!):")
        for r in no_data:
            print(f"   • {r['name'][:40]:<40} - {r['error']}")
        print()
    
    if errors:
        print("⚠️ ERRORS (Check these):")
        for r in errors:
            print(f"   • {r['name'][:40]:<40} - {r['error']}")
        print()
    
    # Recommendations
    print("="*80)
    print("💡 RECOMMENDATIONS")
    print("="*80)
    print()
    
    if len(active) == 0:
        print("🚨 CRITICAL: You have ZERO active whales!")
        print("   This is why you're seeing 'trades_considered=0'")
        print()
        print("   ACTION REQUIRED:")
        print("   1. Run: python scripts/add_active_whales.py")
        print("   2. Add gabagool22 and ExpressoMartini")
        print("   3. Find more active whales from Polymarket leaderboards")
        print()
    elif len(active) < 5:
        print(f"⚠️ WARNING: Only {len(active)} active whales")
        print("   You need more active whales for better trade signals!")
        print()
        print("   SUGGESTED ACTIONS:")
        print("   1. Add gabagool22 and ExpressoMartini")
        print("   2. Browse Polymarket top traders")
        print("   3. Replace the dead/inactive ones")
        print()
    else:
        print(f"✅ Good: {len(active)} active whales")
        print("   Your bot should be catching trades from these")
        print()
    
    if no_data:
        print(f"🗑️ Remove {len(no_data)} dead whale(s):")
        print("   These addresses are invalid or have never traded")
        print()
    
    if inactive:
        print(f"⏳ Monitor {len(inactive)} inactive whale(s):")
        print("   These are valid but currently have no positions")
        print("   They might become active later")
        print()
    
    # Save detailed report
    report_file = Path("data/whale_audit.json")
    report_file.parent.mkdir(exist_ok=True)
    
    report = {
        "audit_time": datetime.now().isoformat(),
        "total_whales": len(whales),
        "active": len(active),
        "inactive": len(inactive),
        "no_data": len(no_data),
        "errors": len(errors),
        "details": results
    }
    
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"📄 Detailed report saved to: {report_file}")
    print()


async def main():
    """Main entry point"""
    await audit_whales()


if __name__ == "__main__":
    asyncio.run(main())
