import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def analyze_simulation_progress():
    """Analyze Phase 2 simulation progress"""
    
    print("=" * 70)
    print("PHASE 2 SIMULATION PROGRESS REPORT")
    print("=" * 70)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Load all simulation files
    sim_dir = Path('data/simulations')
    if not sim_dir.exists():
        print("❌ Simulations directory not found")
        return
    
    sim_files = list(sim_dir.glob('sim_*.json'))
    
    print(f"TOTAL SIMULATIONS: {len(sim_files)}")
    print()
    
    if len(sim_files) == 0:
        print("❌ No simulation files found")
        return
    
    # Analyze simulations
    completed = 0
    pending = 0
    old_format = 0
    elite_sims = 0
    total_delays = 0
    actual_lookups = 0
    fallback_lookups = 0
    
    whales_simulated = set()
    markets_tested = set()
    
    price_changes = []
    
    for sim_file in sim_files:
        try:
            with open(sim_file, 'r') as f:
                sim = json.load(f)
            
            # Status
            status = sim.get('status', 'unknown')
            if status == 'completed':
                completed += 1
            elif status == 'pending':
                pending += 1
            elif status == 'unknown':
                # Check if old format
                if 'results' in sim and len(sim['results']) > 0:
                    first_result = sim['results'][0]
                    if 'checked_at' not in first_result:
                        old_format += 1
                    else:
                        pending += 1
                else:
                    pending += 1
            
            # Elite
            if sim.get('is_elite', False):
                elite_sims += 1
            
            # Whale and market
            whale_addr = sim.get('whale_address') or sim.get('detection', {}).get('wallet')
            if whale_addr:
                whales_simulated.add(whale_addr.lower())
            
            market = sim.get('market_slug') or sim.get('detection', {}).get('market')
            if market:
                markets_tested.add(market)
            
            # Delay analysis
            if 'results' in sim:
                for result in sim['results']:
                    total_delays += 1
                    
                    if 'market_state_at_entry' in result:
                        source = result['market_state_at_entry'].get('source', 'unknown')
                        if source == 'actual_lookup':
                            actual_lookups += 1
                        elif source == 'fallback_detection':
                            fallback_lookups += 1
                
                # Price change analysis
                if len(sim['results']) >= 2:
                    prices = []
                    for r in sim['results']:
                        if 'market_state_at_entry' in r:
                            price = r['market_state_at_entry'].get('price')
                            if price is not None:
                                prices.append(price)
                    
                    if len(prices) >= 2 and len(set(prices)) > 1:  # Prices differ
                        min_price = min(prices)
                        max_price = max(prices)
                        if min_price > 0:
                            change_pct = ((max_price - min_price) / min_price) * 100
                            price_changes.append(abs(change_pct))
        
        except Exception as e:
            print(f"⚠️ Error reading {sim_file.name}: {e}")
    
    # Print summary
    print("STATUS BREAKDOWN:")
    print(f"  ✅ Completed: {completed}")
    print(f"  ⏳ Pending: {pending}")
    if old_format > 0:
        print(f"  📜 Old format (pre-fix): {old_format}")
    print()
    
    print("SIMULATION QUALITY:")
    print(f"  🌟 Elite whale simulations: {elite_sims}")
    print(f"  🐋 Unique whales tested: {len(whales_simulated)}")
    print(f"  📊 Unique markets tested: {len(markets_tested)}")
    print()
    
    print("DELAY CHECK QUALITY:")
    if total_delays > 0:
        print(f"  Total delay checks: {total_delays}")
        print(f"  ✅ Actual price lookups: {actual_lookups} ({actual_lookups/total_delays*100:.1f}%)")
        print(f"  ⚠️  Fallback lookups: {fallback_lookups} ({fallback_lookups/total_delays*100:.1f}%)")
        print(f"  ❓ Unknown source: {total_delays - actual_lookups - fallback_lookups}")
    else:
        print("  No delays yet")
    print()
    
    # Price movement analysis
    if price_changes:
        avg_change = sum(price_changes) / len(price_changes)
        max_change = max(price_changes)
        min_change = min(price_changes)
        print("PRICE MOVEMENT CAPTURED:")
        print(f"  Simulations with price movement: {len(price_changes)}/{len(sim_files)} ({len(price_changes)/len(sim_files)*100:.1f}%)")
        print(f"  Average price change: {avg_change:.1f}%")
        print(f"  Maximum price change: {max_change:.1f}%")
        print(f"  Minimum price change: {min_change:.1f}%")
        print()
    
    # Recent simulations
    print("RECENT SIMULATIONS (Last 5):")
    recent = sorted(sim_files, key=lambda x: x.stat().st_mtime, reverse=True)[:5]
    for sim_file in recent:
        try:
            with open(sim_file, 'r') as f:
                sim = json.load(f)
            
            sim_id = sim.get('simulation_id', sim_file.stem)
            status = sim.get('status', 'unknown')
            is_elite = '⭐' if sim.get('is_elite', False) else '  '
            
            # Get price info
            prices_str = "No delays"
            if 'results' in sim and len(sim['results']) > 0:
                prices = []
                for r in sim['results']:
                    if 'market_state_at_entry' in r:
                        price = r['market_state_at_entry'].get('price')
                        if price is not None:
                            prices.append(price)
                if prices:
                    prices_str = f"Prices: {', '.join([f'{p:.3f}' for p in prices])}"
            
            modified = datetime.fromtimestamp(sim_file.stat().st_mtime)
            print(f"  {is_elite} {sim_id[:40]}... | {status}")
            print(f"     Modified: {modified.strftime('%Y-%m-%d %H:%M:%S')} | {prices_str}")
        except Exception as e:
            print(f"  ⚠️ Error reading {sim_file.name}: {e}")
    
    print()
    
    # Collection rate
    if len(sim_files) > 1:
        oldest = min(sim_files, key=lambda x: x.stat().st_mtime)
        newest = max(sim_files, key=lambda x: x.stat().st_mtime)
        
        oldest_time = datetime.fromtimestamp(oldest.stat().st_mtime)
        newest_time = datetime.fromtimestamp(newest.stat().st_mtime)
        
        time_diff = (newest_time - oldest_time).total_seconds() / 3600  # hours
        
        if time_diff > 0:
            rate = len(sim_files) / time_diff
            print("COLLECTION RATE:")
            print(f"  Time span: {time_diff:.1f} hours")
            print(f"  Rate: {rate:.1f} simulations/hour")
            print()
            
            # Projection
            hours_remaining = 48 - time_diff
            if hours_remaining > 0:
                projected = len(sim_files) + (rate * hours_remaining)
                print("HOUR 48 PROJECTION:")
                print(f"  Current: {len(sim_files)} simulations")
                print(f"  Hours remaining: {hours_remaining:.1f}")
                print(f"  Projected total: {projected:.0f} simulations")
                print()
    
    print("=" * 70)

if __name__ == "__main__":
    analyze_simulation_progress()
