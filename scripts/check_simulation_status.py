"""Check simulation status and verify if simulations are running"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

print("="*80)
print("SIMULATION STATUS CHECK")
print("="*80)
print()

# Check 1: TradeSimulator structure
print("1. TradeSimulator Structure")
print("-"*80)
try:
    from src.simulation.trade_simulator import TradeSimulator
    sim = TradeSimulator()
    print("✅ TradeSimulator loaded successfully")
    print(f"   Attributes: {[x for x in dir(sim) if not x.startswith('_')]}")
    print(f"   Has 'simulations' attr: {hasattr(sim, 'simulations')}")
    print(f"   Has 'storage_path' attr: {hasattr(sim, 'storage_path')}")
    print(f"   Elite whales: {len(sim.elite_whales)}")
except Exception as e:
    print(f"❌ Error loading TradeSimulator: {e}")
    import traceback
    traceback.print_exc()

print()

# Check 2: Watcher integration
print("2. Watcher Integration")
print("-"*80)
try:
    with open('scripts/realtime_whale_watcher.py', 'r') as f:
        content = f.read()
    
    if 'simulate_trade' in content:
        print("✅ simulate_trade() is called in watcher")
        # Count occurrences
        count = content.count('simulate_trade')
        print(f"   Found {count} references to simulate_trade")
    else:
        print("❌ simulate_trade() NOT found in watcher")
    
    if 'asyncio.create_task' in content and 'simulate_trade' in content:
        print("✅ Simulations are started as async tasks")
    else:
        print("⚠️ Simulation task creation unclear")
        
except Exception as e:
    print(f"❌ Error checking watcher: {e}")

print()

# Check 3: Simulation files
print("3. Simulation Files")
print("-"*80)
data_dir = Path('data')
sim_dir = data_dir / 'simulations'

if sim_dir.exists():
    sim_files = list(sim_dir.glob('*.json'))
    print(f"✅ Simulation directory exists: {sim_dir}")
    print(f"   Files found: {len(sim_files)}")
    if sim_files:
        latest = max(sim_files, key=lambda p: p.stat().st_mtime)
        print(f"   Latest file: {latest.name}")
        print(f"   Modified: {latest.stat().st_mtime}")
else:
    print(f"❌ Simulation directory NOT found: {sim_dir}")
    print("   This means simulations are NOT being saved to disk")

print()

# Check 4: In-memory simulations
print("4. Simulation Persistence")
print("-"*80)
print("⚠️ CRITICAL FINDING:")
print("   TradeSimulator does NOT have persistence built-in")
print("   Simulations are created but NOT saved to disk")
print("   This means:")
print("   • Simulations run in memory only")
print("   • Lost on watcher restart")
print("   • No data for Phase 2 analysis")
print()
print("✅ SOLUTION NEEDED:")
print("   Add save_to_disk() method to TradeSimulator")
print("   Call it after each simulation completes")
print("   Store in data/simulations/ directory")

print()
print("="*80)
print("END OF CHECK")
print("="*80)
