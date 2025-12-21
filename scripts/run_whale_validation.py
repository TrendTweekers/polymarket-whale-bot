"""Run whale validation on top 200 high-confidence whales"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.validation.api_whale_validator import validate_whale_batch, get_elite_whales
from dynamic_whale_manager import DynamicWhaleManager
import json

async def main():
    print("="*80)
    print("🔍 WHALE VALIDATION - Top 200 High-Confidence Whales")
    print("="*80)
    print()
    
    # Get top high-confidence whales
    try:
        manager = DynamicWhaleManager()
        whales = manager.whales
        
        # Filter to high-confidence (≥70%)
        high_conf_whales = [
            (addr, data) for addr, data in whales.items()
            if data.get('confidence', 0) >= 0.70
        ]
        
        # Sort by confidence
        high_conf_whales.sort(key=lambda x: x[1].get('confidence', 0), reverse=True)
        
        # Get top 200
        top_200 = [addr for addr, _ in high_conf_whales[:200]]
        
        print(f"Found {len(high_conf_whales)} high-confidence whales (≥70%)")
        print(f"Processing top {len(top_200)}...")
        print()
        print("Mode: Quick validation (no resolution checks for speed)")
        print("   - Checks trade count and volume")
        print("   - Full resolution checks can be done later if needed")
        print()
        
    except Exception as e:
        print(f"❌ Error loading whale manager: {e}")
        print("   Using test addresses instead...")
        top_200 = [
            "0xd189664c5308903476f9f079820431e4fd7d06f4",
            "0xed107a85a4585a381e48c7f7ca4144909e7dd2e5",
            "0x9b979a065641e8cfde3022a30ed2d9415cf55e12"
        ]
    
    # Validate batch
    print("Starting validation...")
    print("="*80)
    print()
    
    results = await validate_whale_batch(top_200, check_resolutions=False)
    
    # Filter to elite
    elite = get_elite_whales(results)
    
    # Summary
    print()
    print("="*80)
    print("📊 VALIDATION SUMMARY")
    print("="*80)
    print()
    print(f"Total validated: {len(results)}")
    print(f"Elite whales (pass criteria): {len(elite)}")
    print()
    
    if elite:
        print("Top 10 Elite Whales:")
        for i, whale in enumerate(elite[:10], 1):
            addr = whale['address']
            trades = whale['trade_count']
            volume = whale['total_volume_usd']
            profit = whale['total_profit_eth']
            print(f"  {i}. {addr[:16]}... | {trades} trades | ${volume:,.0f} volume | {profit:.2f} ETH profit")
    
    # Save results
    output_file = Path("data/api_validation_results.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'total_validated': len(results),
            'elite_count': len(elite),
            'results': results,
            'elite_whales': elite
        }, f, indent=2)
    
    print()
    print(f"💾 Results saved to: {output_file}")
    print()
    print("="*80)
    print("✅ VALIDATION COMPLETE")
    print("="*80)


if __name__ == "__main__":
    from datetime import datetime
    asyncio.run(main())
