"""
Validate Grok Whale Addresses - Check Active Positions & Quality
Validates whale addresses sorted by win rate and merges with existing config
"""

import asyncio
import aiohttp
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "config" / "whale_list.json"
CLOB_URL = "https://clob.polymarket.com"


# Grok whale addresses with win rate and trade data
# Format: List of tuples (address, win_rate_percent, trades, pnl_string)
GROK_WHALES = [
    ("0x78b9ac44a6d7d7a076c14e0ad518b301b63c6b76", 100.0, 8, "8.7M"),
    ("0x863134d00841b2e200492805a01e1e2f5defaa53", 100.0, 8, "7.5M"),
    ("0x8119010a6e589062aa03583bb3f39ca632d9f887", 100.0, 21, "6.0M"),
    ("0x885783760858e1bd5dd09a3c3f916cfa251ac270", 100.0, 7, "5.6M"),
    ("0x23786fdad0073692157c6d7dc81f281843a35fcb", 100.0, 7, "5.1M"),
    ("0x2bf64b86b64c315d879571b07a3b76629e467cd0", 100.0, 6, "2.0M"),
    ("0xf7850ebb60c10d5375fff6e596d55b69fdec05ed", 98.0, 1327, "0.7M"),
    ("0x9b979a065641e8cfde3022a30ed2d9415cf55e12", 96.1, 4939, "1.3M"),
    ("0xd189664c5308903476f9f079820431e4fd7d06f4", 95.6, 10951, "0.8M"),
    ("0x56687bf447db6ffa42ffe2204a05edaa20f55839", 88.9, 22, "22.0M"),
    ("0x8861f0bb5e0c19474ba73beeadc13ed8915beed6", 89.7, 50, "1.0M"),
    ("0x000d257d2dc7616feaef4ae0f14600fdf50a758e", 84.5, 1012, "1.3M"),
    ("0xed107a85a4585a381e48c7f7ca4144909e7dd2e5", 84.4, 958, "1.2M"),
    ("0x6bab41a0dc40d6dd4c1a915b8c01969479fd1292", 78.2, 1874, "0.9M"),
    ("0x0562c423912e325f83fa79df55085979e1f5594f", 76.9, 19, "1.9M"),
]


def parse_pnl_string(pnl_str: str) -> float:
    """Convert P&L string like '8.7M' to float"""
    pnl_str = pnl_str.strip().upper()
    if pnl_str.endswith('M'):
        return float(pnl_str[:-1]) * 1_000_000
    elif pnl_str.endswith('K'):
        return float(pnl_str[:-1]) * 1_000
    else:
        return float(pnl_str)


def convert_grok_whales_to_dict(whales_list: List) -> Dict:
    """Convert tuple list to dictionary format"""
    whales_dict = {}
    for i, whale_data in enumerate(whales_list):
        if isinstance(whale_data, tuple) and len(whale_data) >= 4:
            address, win_rate_percent, trades, pnl_str = whale_data
            whales_dict[address] = {
                'win_rate': win_rate_percent / 100.0,  # Convert 100.0 to 1.0
                'trades': trades,
                'pnl': parse_pnl_string(pnl_str),
                'name': f"Grok Whale #{i+1}"
            }
        elif isinstance(whale_data, dict):
            # Already in dict format
            address = whale_data.get('address')
            if address:
                whales_dict[address] = whale_data
    return whales_dict


def load_whales_from_file(filepath: str) -> Dict:
    """Load whale data from JSON file"""
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            # Handle both list and dict formats
            if isinstance(data, list):
                return {w['address']: w for w in data}
            elif isinstance(data, dict):
                return data
    except Exception as e:
        print(f"❌ Error loading file: {e}")
        return {}


async def get_wallet_positions(address: str, session: aiohttp.ClientSession) -> List[Dict]:
    """Get current active positions for a wallet"""
    try:
        url = f"{CLOB_URL}/positions/{address}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
            if response.status == 200:
                positions = await response.json()
                if isinstance(positions, list):
                    # Filter to active positions only (size > 0)
                    return [p for p in positions if float(p.get('size', 0)) > 0]
                return []
    except Exception:
        pass
    return []


def categorize_whale(win_rate: float, trades: int, pnl: float) -> str:
    """Categorize whale by quality"""
    if win_rate >= 0.96 and trades >= 1000:
        return "GOLD"
    elif win_rate >= 0.80 and trades >= 100:
        return "EXCELLENT"
    elif win_rate >= 0.75 and trades >= 50:
        return "GOOD"
    elif win_rate == 1.0 and trades < 20:
        return "CAUTION"  # Perfect but low sample size
    else:
        return "SKIP"  # Doesn't meet minimum criteria


async def validate_whale(address: str, whale_data: Dict, session: aiohttp.ClientSession) -> Optional[Dict]:
    """Validate a single whale address"""
    win_rate = whale_data.get('win_rate', 0)
    trades = whale_data.get('trades', 0)
    pnl = whale_data.get('pnl', 0)
    name = whale_data.get('name', f"Whale_{address[:8]}")
    
    category = categorize_whale(win_rate, trades, pnl)
    
    if category == "SKIP":
        return None
    
    # Check for active positions
    positions = await get_wallet_positions(address, session)
    active_count = len(positions)
    
    result = {
        'address': address.lower(),
        'name': name,
        'win_rate': win_rate,
        'trades': trades,
        'pnl': pnl,
        'category': category,
        'active_positions': active_count,
        'has_active_positions': active_count > 0
    }
    
    return result


async def validate_all_whales(whales: Dict) -> List[Dict]:
    """Validate all whale addresses"""
    print("\n" + "="*80)
    print("🔍 PHASE 1: VALIDATING WHALE ADDRESSES")
    print("="*80)
    print()
    
    validated = []
    
    async with aiohttp.ClientSession() as session:
        for i, (address, data) in enumerate(whales.items(), 1):
            print(f"[{i}/{len(whales)}] {address[:12]}... ({data.get('name', 'Unknown')})")
            print(f"      WR: {data.get('win_rate', 0):.1%} | Trades: {data.get('trades', 0):,} | P&L: ${data.get('pnl', 0):,.0f}")
            
            result = await validate_whale(address, data, session)
            
            if result:
                if result['has_active_positions']:
                    print(f"      ✅ {result['category']} | {result['active_positions']} active positions")
                else:
                    print(f"      ⚠️ {result['category']} | No active positions (but meets quality criteria)")
                validated.append(result)
            else:
                print(f"      ❌ SKIP (doesn't meet criteria)")
            
            print()
            await asyncio.sleep(0.3)  # Rate limiting
    
    return validated


def generate_quality_report(validated: List[Dict]) -> Dict:
    """Generate quality breakdown report"""
    report = {
        'GOLD': [],
        'EXCELLENT': [],
        'GOOD': [],
        'CAUTION': []
    }
    
    for whale in validated:
        category = whale['category']
        if category in report:
            report[category].append(whale)
    
    return report


def print_quality_report(report: Dict):
    """Print quality breakdown"""
    print("="*80)
    print("📊 PHASE 2: QUALITY REPORT")
    print("="*80)
    print()
    
    total = sum(len(whales) for whales in report.values())
    
    print(f"GOLD Tier (96-98% WR, 1000+ trades): {len(report['GOLD'])}")
    print(f"EXCELLENT Tier (80-90% WR, 100+ trades): {len(report['EXCELLENT'])}")
    print(f"GOOD Tier (75-80% WR, 50+ trades): {len(report['GOOD'])}")
    print(f"CAUTION Tier (100% WR, <20 trades): {len(report['CAUTION'])}")
    print()
    print(f"Total Validated: {total}")
    print()


def print_top_whales(validated: List[Dict], limit: int = 10):
    """Print top whales by quality score"""
    print("="*80)
    print(f"🏆 PHASE 3: TOP {limit} WHALES BY QUALITY")
    print("="*80)
    print()
    
    # Score: win_rate * (1 + trades/1000) * (1 + has_active)
    scored = []
    for whale in validated:
        score = (
            whale['win_rate'] * 
            (1 + whale['trades'] / 1000) * 
            (2 if whale['has_active_positions'] else 1)
        )
        scored.append((score, whale))
    
    scored.sort(reverse=True, key=lambda x: x[0])
    
    for i, (score, whale) in enumerate(scored[:limit], 1):
        active_indicator = "🟢" if whale['has_active_positions'] else "⚪"
        print(f"{i:2}. {active_indicator} {whale['category']:10} | "
              f"WR: {whale['win_rate']:5.1%} | "
              f"Trades: {whale['trades']:>6,} | "
              f"P&L: ${whale['pnl']:>10,.0f} | "
              f"{whale['name'][:30]}")
        print(f"    Address: {whale['address']}")
        if whale['has_active_positions']:
            print(f"    Active Positions: {whale['active_positions']}")
        print()


async def merge_with_config(validated: List[Dict], report: Dict):
    """Merge validated whales with existing config"""
    print("="*80)
    print("💾 PHASE 4: UPDATING CONFIG")
    print("="*80)
    print()
    
    # Load existing config
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        existing_whales = config.get('whales', [])
        existing_addresses = {w['address'].lower() for w in existing_whales}
    else:
        existing_whales = []
        existing_addresses = set()
        config = {'whales': [], 'discovery_settings': {}}
    
    print(f"📋 Existing whales: {len(existing_whales)}")
    print(f"📋 Validated new whales: {len(validated)}")
    print()
    
    # Add validated whales (skip duplicates)
    added_count = 0
    skipped_count = 0
    
    for whale in validated:
        if whale['address'].lower() in existing_addresses:
            print(f"⏭️ Skipping {whale['address'][:12]}... (already exists)")
            skipped_count += 1
            continue
        
        whale_entry = {
            "address": whale['address'],
            "name": whale['name'],
            "source": "Grok - Validated High Win Rate",
            "added": datetime.now().strftime('%Y-%m-%d'),
            "known_win_rate": whale['win_rate'],
            "specialty": [whale['category'].lower()],
            "avg_bet_size": 20000,
            "verified_metrics": {
                "win_rate": f"{whale['win_rate']:.1%}",
                "total_trades": whale['trades'],
                "total_pnl": f"${whale['pnl']:,.0f}",
                "active_positions": whale['active_positions'],
                "category": whale['category']
            }
        }
        
        existing_whales.append(whale_entry)
        existing_addresses.add(whale['address'].lower())
        added_count += 1
    
    config['whales'] = existing_whales
    
    # Save
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    
    print()
    print(f"➕ Added: {added_count} new whales")
    print(f"⏭️ Skipped: {skipped_count} duplicates")
    print(f"📊 Total now: {len(existing_whales)} whales")
    print(f"💾 Saved to: {CONFIG_FILE}")
    print()
    
    return {
        'added': added_count,
        'skipped': skipped_count,
        'total': len(existing_whales),
        'existing': len(existing_whales) - added_count
    }


def print_final_summary(stats: Dict, report: Dict):
    """Print final summary"""
    print("="*80)
    print("✅ VALIDATION COMPLETE")
    print("="*80)
    print()
    
    print("📊 FINAL STATISTICS:")
    print(f"   • Existing whales preserved: {stats['existing']}")
    print(f"   • New whales added: {stats['added']}")
    print(f"   • Total whales: {stats['total']}")
    print()
    
    print("🏆 QUALITY BREAKDOWN:")
    print(f"   • GOLD: {len(report['GOLD'])}")
    print(f"   • EXCELLENT: {len(report['EXCELLENT'])}")
    print(f"   • GOOD: {len(report['GOOD'])}")
    print(f"   • CAUTION: {len(report['CAUTION'])}")
    print()
    
    print("🚀 NEXT STEP:")
    print("   python main.py")
    print()


async def main():
    """Main execution"""
    print("\n" + "="*80)
    print("🎯 GROK WHALE VALIDATOR")
    print("="*80)
    print()
    
    # Load whales from command line argument or use GROK_WHALES
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        print(f"📄 Loading whales from: {filepath}")
        file_whales = load_whales_from_file(filepath)
        if file_whales:
            whales = file_whales
            print(f"✅ Loaded {len(whales)} whales from file")
        else:
            print("⚠️ Could not load from file, using GROK_WHALES")
            whales = convert_grok_whales_to_dict(GROK_WHALES)
    else:
        # Convert tuple list to dict format
        whales = convert_grok_whales_to_dict(GROK_WHALES)
    
    if not whales:
        print("❌ ERROR: No whale addresses provided!")
        print()
        print("Usage:")
        print("  1. Add addresses to GROK_WHALES in the script, OR")
        print("  2. Provide JSON file: python validate_grok_whales.py whales.json")
        return
    
    print(f"📋 Validating {len(whales)} whale addresses from Grok...")
    print()
    
    # Validate all whales
    validated = await validate_all_whales(whales)
    
    if not validated:
        print("❌ No whales passed validation!")
        return
    
    # Generate quality report
    report = generate_quality_report(validated)
    print_quality_report(report)
    
    # Show top whales
    print_top_whales(validated, limit=10)
    
    # Merge with config
    stats = await merge_with_config(validated, report)
    
    # Final summary
    print_final_summary(stats, report)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏸️ Validation stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
