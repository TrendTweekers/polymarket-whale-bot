#!/usr/bin/env python3
"""Investigate whale diversity and elite whale activity"""
import json
from pathlib import Path
from collections import Counter
import sys
sys.path.insert(0, str(Path(__file__).parent))

def investigate_whale_diversity():
    """Investigate which whales are being simulated and why"""
    
    print("=" * 70)
    print("WHALE DIVERSITY INVESTIGATION")
    print("=" * 70)
    print()
    
    # Load elite whales
    with open('data/api_validation_results.json', 'r') as f:
        elite_data = json.load(f)
    
    # Handle both list and dict formats
    if isinstance(elite_data, list):
        results = elite_data
    else:
        results = elite_data.get('results', [])
    
    elite_addresses = {w['address'].lower() for w in results if w.get('passes', False)}
    
    print(f"Elite whales available: {len(elite_addresses)}")
    print()
    
    # Analyze simulations
    sim_dir = Path('data/simulations')
    sim_files = list(sim_dir.glob('sim_*.json'))
    
    whale_sims = Counter()
    whale_details = {}
    
    for sim_file in sim_files:
        try:
            with open(sim_file, 'r') as f:
                sim = json.load(f)
            
            whale = sim.get('whale_address', '').lower()
            if whale:
                whale_sims[whale] += 1
                
                if whale not in whale_details:
                    is_elite = whale in elite_addresses
                    whale_details[whale] = {
                        'simulations': 0,
                        'is_elite': is_elite,
                        'confidence': sim.get('confidence', 0)
                    }
                whale_details[whale]['simulations'] += 1
        except Exception as e:
            print(f"⚠️ Error reading {sim_file.name}: {e}")
    
    # Report
    print("WHALES BEING SIMULATED:")
    print("-" * 70)
    print(f"{'Whale Address':<45} {'Sims':<6} {'Elite':<8} {'Conf'}")
    print("-" * 70)
    
    for whale, count in whale_sims.most_common():
        details = whale_details[whale]
        elite_status = '⭐ YES' if details['is_elite'] else '   NO'
        print(f"{whale[:42]:<45} {count:<6} {elite_status:<8} {details['confidence']}%")
    
    print()
    print(f"Total unique whales: {len(whale_sims)}")
    print(f"Elite whales found: {sum(1 for d in whale_details.values() if d['is_elite'])}")
    print()
    
    # Check if any should be elite
    elite_simulated = [w for w, d in whale_details.items() if d['is_elite']]
    if elite_simulated:
        print("🎉 ELITE WHALES FOUND IN SIMULATIONS:")
        for whale in elite_simulated:
            elite_info = next((w for w in results if w['address'].lower() == whale), None)
            if elite_info:
                print(f"  {whale[:42]}")
                print(f"    Trades: {elite_info.get('trade_count', 0)}")
                print(f"    Volume: ${elite_info.get('volume', 0):,.0f}")
                print(f"    Simulations: {whale_details[whale]['simulations']}")
    else:
        print("❌ NO ELITE WHALES IN SIMULATIONS")
        print()
        print("ANALYSIS:")
        print("All whales being simulated are non-elite.")
        print("This explains 0 elite simulations.")
    
    print()
    print("=" * 70)

def check_elite_whale_activity():
    """Check if elite whales are trading but not meeting threshold"""
    
    print("=" * 70)
    print("ELITE WHALE ACTIVITY CHECK")
    print("=" * 70)
    print()
    
    # Load elite whales
    with open('data/api_validation_results.json', 'r') as f:
        elite_data = json.load(f)
    
    # Handle both list and dict formats
    if isinstance(elite_data, list):
        results = elite_data
    else:
        results = elite_data.get('results', [])
    
    elite_addresses = {w['address'].lower() for w in results if w.get('passes', False)}
    
    # Load dynamic whale state
    try:
        from dynamic_whale_manager import DynamicWhaleManager
        manager = DynamicWhaleManager()
        
        # Check elite whales in dynamic pool
        elite_in_pool = []
        for address, whale_data in manager.whales.items():
            if address.lower() in elite_addresses:
                elite_in_pool.append({
                    'address': address,
                    'confidence': whale_data['confidence'],
                    'trade_count': whale_data['trade_count'],
                    'total_value': whale_data['total_value']
                })
        
        print(f"Elite whales discovered: {len(elite_in_pool)} / {len(elite_addresses)}")
        print()
        
        if elite_in_pool:
            # Sort by confidence
            elite_in_pool.sort(key=lambda x: x['confidence'], reverse=True)
            
            print("TOP 10 ELITE WHALES IN DYNAMIC POOL:")
            print("-" * 70)
            print(f"{'Address':<45} {'Conf':<6} {'Trades':<8} {'Value'}")
            print("-" * 70)
            
            for whale in elite_in_pool[:10]:
                addr = whale['address'][:42]
                conf = whale['confidence']
                trades = whale['trade_count']
                value = whale['total_value']
                
                meets_threshold = '✅' if conf >= 65 else '❌'
                print(f"{addr:<45} {conf:>5.0f}% {trades:>7} ${value:>10,.0f} {meets_threshold}")
            
            # Count how many meet threshold
            meets_threshold = sum(1 for w in elite_in_pool if w['confidence'] >= 65)
            print()
            print(f"Elite whales meeting ≥65% threshold: {meets_threshold}")
            
            if meets_threshold == 0:
                print()
                print("⚠️ ISSUE FOUND:")
                print("Elite whales are in the pool but NONE meet ≥65% confidence!")
                print()
                print("SOLUTIONS:")
                print("1. Lower confidence threshold (65% → 60% or 55%)")
                print("2. Wait longer for elite whales to build confidence")
                print("3. Add special handling for elite whales (lower threshold)")
        else:
            print("❌ NO ELITE WHALES DISCOVERED YET")
            print()
            print("This means:")
            print("• Elite whales haven't traded recently")
            print("• Or they're trading below $100 threshold")
            print("• Or detection is missing them")
    except Exception as e:
        print(f"⚠️ Error loading dynamic whale manager: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("=" * 70)

def analyze_trade_distribution():
    """See which whales are most active in trades"""
    
    print("=" * 70)
    print("TRADE DISTRIBUTION ANALYSIS")
    print("=" * 70)
    print()
    
    # Load trade history
    try:
        with open('data/realtime_whale_trades.json', 'r') as f:
            trades = json.load(f)
    except Exception as e:
        print(f"⚠️ Error loading trades: {e}")
        return
    
    # Load elite addresses
    with open('data/api_validation_results.json', 'r') as f:
        elite_data = json.load(f)
    
    # Handle both list and dict formats
    if isinstance(elite_data, list):
        results = elite_data
    else:
        results = elite_data.get('results', [])
    
    elite_addresses = {w['address'].lower() for w in results if w.get('passes', False)}
    
    # Count trades per whale
    whale_trades = Counter()
    for trade in trades:
        wallet = trade.get('wallet', '').lower()
        if wallet:
            whale_trades[wallet] += 1
    
    print("TOP 20 MOST ACTIVE WHALES IN TRADES:")
    print("-" * 70)
    print(f"{'Whale':<45} {'Trades':<8} {'Elite'}")
    print("-" * 70)
    
    for whale, count in whale_trades.most_common(20):
        is_elite = '⭐ YES' if whale in elite_addresses else '   NO'
        print(f"{whale[:42]:<45} {count:<8} {is_elite}")
    
    # Statistics
    total_whales = len(whale_trades)
    elite_trading = sum(1 for w in whale_trades if w in elite_addresses)
    
    print()
    print(f"Total whales trading: {total_whales}")
    print(f"Elite whales trading: {elite_trading} / {len(elite_addresses)}")
    if total_whales > 0:
        print(f"Elite percentage: {elite_trading/total_whales*100:.1f}% of active traders")
    print()
    print("=" * 70)

if __name__ == "__main__":
    investigate_whale_diversity()
    print("\n")
    check_elite_whale_activity()
    print("\n")
    analyze_trade_distribution()
