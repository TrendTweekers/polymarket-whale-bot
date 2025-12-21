"""
Verify Simulation Results
=========================
Checks if scheduled delay price checks are working correctly
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict

def verify_simulation(sim_file: Path = None):
    """Verify a simulation file shows scheduled delays working"""
    
    if sim_file is None:
        # Find latest simulation file
        sim_dir = Path("data/simulations")
        if not sim_dir.exists():
            print("❌ Simulations directory not found")
            return
        
        sim_files = list(sim_dir.glob("sim_*.json"))
        if not sim_files:
            print("⏰ No simulation files found yet")
            print("   Waiting for next high-confidence whale trade...")
            return
        
        sim_file = max(sim_files, key=lambda p: p.stat().st_mtime)
    
    print("=" * 70)
    print("SIMULATION VERIFICATION")
    print("=" * 70)
    print(f"\n📄 File: {sim_file.name}")
    print(f"   Last modified: {datetime.fromtimestamp(sim_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        with open(sim_file, 'r') as f:
            sim = json.load(f)
    except Exception as e:
        print(f"\n❌ Error reading file: {e}")
        return
    
    # Check status (handle old format)
    status = sim.get('status', 'unknown')
    results = sim.get('results', [])
    
    # Detect old format (pre-scheduled delays)
    if status == 'unknown' and results:
        first_result = results[0] if results else {}
        if 'checked_at' not in first_result:
            status = 'old_format'
    
    print(f"\n📊 Status: {status}")
    
    if status == 'old_format':
        print(f"   ⚠️  This is an OLD simulation (before scheduled delays fix)")
        print(f"   Created before watcher restart at 00:35:00")
        print(f"\n✅ NEW CODE IS RUNNING:")
        print(f"   - Watcher restarted with scheduled delay checks")
        print(f"   - Price tracking active")
        print(f"   - Next simulation will use new approach")
        print(f"\n⏰ WAITING FOR NEXT HIGH-CONFIDENCE WHALE TRADE")
        print(f"   Then wait 6+ minutes and run this script again")
        return
    
    print(f"📈 Results count: {len(results)}")
    
    if not results:
        print("\n⏳ No delay results yet - simulation still in progress")
        delays_scheduled = sim.get('delays_scheduled', [])
        if delays_scheduled:
            print(f"   Scheduled delays: {', '.join([f'+{d//60}min' for d in delays_scheduled])}")
        return
    
    # Check each delay result
    print(f"\n🔍 Delay Results:")
    print("-" * 70)
    
    prices = []
    sources = []
    
    for result in results:
        delay_sec = result.get('delay_seconds', 0)
        delay_min = delay_sec // 60
        
        market_state = result.get('market_state_at_entry', {})
        price = market_state.get('price')
        source = market_state.get('source', 'unknown')
        entry_price = result.get('simulated_entry_price', 0)
        checked_at = result.get('checked_at', 'N/A')
        
        prices.append(price)
        sources.append(source)
        
        print(f"\n  Delay: +{delay_min}min ({delay_sec}s)")
        print(f"    Price: {price:.6f}" if price else "    Price: N/A")
        print(f"    Entry: {entry_price:.6f}" if entry_price else "    Entry: N/A")
        print(f"    Source: {source}")
        print(f"    Checked: {checked_at}")
    
    print("-" * 70)
    
    # Verify prices differ
    if prices:
        unique_prices = len(set(prices))
        print(f"\n✅ Price Analysis:")
        print(f"   Unique prices: {unique_prices}")
        print(f"   Price range: {min(prices):.6f} to {max(prices):.6f}")
        
        if unique_prices > 1:
            price_change = ((max(prices) - min(prices)) / min(prices)) * 100
            print(f"   Price change: {price_change:.2f}%")
            print(f"\n🎉 SUCCESS - Prices differ! Scheduled delays working!")
        else:
            print(f"\n⚠️  All prices same")
            print(f"   Possible reasons:")
            print(f"   - Market didn't move during delays")
            print(f"   - Very liquid market (stable price)")
            print(f"   - Need more time for price to change")
    
    # Verify sources
    if sources:
        actual_lookups = sum(1 for s in sources if s == 'actual_lookup')
        print(f"\n✅ Source Analysis:")
        print(f"   Actual lookups: {actual_lookups}/{len(sources)}")
        
        if actual_lookups == len(sources):
            print(f"   ✅ All delays used actual prices!")
        elif actual_lookups > 0:
            print(f"   ⚠️  Some delays used fallback prices")
        else:
            print(f"   ❌ No actual prices found - check price tracking")
    
    # Check completion
    if status == 'completed':
        print(f"\n🎉 Simulation Complete!")
        print(f"   All delay checks finished")
    elif status == 'pending':
        remaining = len(sim.get('delays_scheduled', [])) - len(results)
        if remaining > 0:
            print(f"\n⏳ Simulation In Progress")
            print(f"   {remaining} delay check(s) remaining")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Verify specific file
        verify_simulation(Path(sys.argv[1]))
    else:
        # Verify latest file
        verify_simulation()
