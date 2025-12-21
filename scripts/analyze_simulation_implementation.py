"""Analyze simulation implementation - check what's actually working"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from src.simulation.trade_simulator import TradeSimulator
from src.simulation.market_state_tracker import MarketStateTracker
from src.simulation.slippage_calculator import SlippageCalculator
import inspect

print("="*80)
print("SIMULATION IMPLEMENTATION ANALYSIS")
print("="*80)
print()

# Check 1: TradeSimulator methods
print("1. TradeSimulator Implementation")
print("-"*80)
sim = TradeSimulator()
methods = [m for m in dir(sim) if not m.startswith('__')]
print(f"Methods: {len(methods)}")
print(f"  ✅ simulate_trade: {hasattr(sim, 'simulate_trade')}")
print(f"  ✅ _simulate_delay: {hasattr(sim, '_simulate_delay')}")
print(f"  ✅ resolve_simulation: {hasattr(sim, 'resolve_simulation')}")
print(f"  ✅ _save_simulation: {hasattr(sim, '_save_simulation')}")
print()

# Check 2: MarketStateTracker
print("2. MarketStateTracker Implementation")
print("-"*80)
tracker = MarketStateTracker()
print(f"  ✅ record_state: {hasattr(tracker, 'record_state')}")
print(f"  ✅ get_state_at_time: {hasattr(tracker, 'get_state_at_time')}")
print(f"  ✅ _fetch_state_from_api: {hasattr(tracker, '_fetch_state_from_api')}")
# Check if API fetch is implemented
import inspect
api_fetch_code = inspect.getsource(tracker._fetch_state_from_api)
if 'TODO' in api_fetch_code or 'return None' in api_fetch_code:
    print(f"  ⚠️ _fetch_state_from_api: NOT IMPLEMENTED (returns None)")
else:
    print(f"  ✅ _fetch_state_from_api: IMPLEMENTED")
print()

# Check 3: SlippageCalculator
print("3. SlippageCalculator Implementation")
print("-"*80)
calc = SlippageCalculator()
print(f"  ✅ calculate_slippage: {hasattr(calc, 'calculate_slippage')}")
slippage_code = inspect.getsource(calc.calculate_slippage)
if 'TODO' in slippage_code:
    print(f"  ⚠️ Has TODOs (orderbook depth not used)")
else:
    print(f"  ✅ Basic implementation")
print()

# Check 4: Analyze existing simulation files
print("4. Existing Simulation Files Analysis")
print("-"*80)
sim_dir = Path('data/simulations')
if sim_dir.exists():
    sim_files = list(sim_dir.glob('*.json'))
    print(f"Found: {len(sim_files)} simulation files")
    
    if sim_files:
        # Load latest simulation
        latest = max(sim_files, key=lambda p: p.stat().st_mtime)
        with open(latest) as f:
            sim_data = json.load(f)
        
        print(f"\nLatest simulation: {latest.name}")
        print(f"  Whale: {sim_data['whale_address'][:16]}...")
        print(f"  Market: {sim_data['market_slug']}")
        print(f"  Detection time: {sim_data['detection_time']}")
        print(f"  Delays tested: {len(sim_data['results'])}")
        
        # Check if prices are different at delays
        prices = [r['market_state_at_entry']['price'] for r in sim_data['results']]
        timestamps = [r['market_state_at_entry']['timestamp'] for r in sim_data['results']]
        
        print(f"\n  Price at detection: {prices[0]}")
        print(f"  Prices at delays: {prices}")
        print(f"  Timestamps: {timestamps}")
        
        # CRITICAL CHECK: Are prices different?
        if len(set(prices)) == 1:
            print(f"\n  ⚠️ CRITICAL: All delays show SAME price!")
            print(f"     This means delay price checking is NOT working")
            print(f"     All delays using detection price (fallback)")
        else:
            print(f"\n  ✅ Prices differ at delays (delay checking working)")
        
        # Check if resolved
        resolved = [r['resolved'] for r in sim_data['results']]
        if any(resolved):
            print(f"\n  ✅ Some results resolved (P&L calculated)")
        else:
            print(f"\n  ⚠️ No results resolved yet (markets not closed)")
else:
    print("No simulation directory found")

print()
print("="*80)
print("CRITICAL FINDINGS")
print("="*80)
print()
print("ISSUE FOUND:")
print("  ⚠️ Delay price checking uses FALLBACK")
print("  ⚠️ _fetch_state_from_api() returns None (not implemented)")
print("  ⚠️ Falls back to detection price for all delays")
print()
print("WHAT THIS MEANS:")
print("  • Simulations ARE being created ✅")
print("  • Delay structure EXISTS ✅")
print("  • BUT: All delays use SAME price (detection price) ❌")
print("  • Need to implement actual price fetching at delays")
print()
print("="*80)
