"""Check if recent simulation whales should be elite"""
import json
from pathlib import Path

# Load elite whales
with open('data/api_validation_results.json', 'r') as f:
    data = json.load(f)

elite_addrs = {w['address'].lower() for w in data.get('results', []) if w.get('passes', False)}

print("=" * 70)
print("RECENT WHALE ELITE STATUS CHECK")
print("=" * 70)
print(f"Total elite whales: {len(elite_addrs)}")
print()

# Get recent simulations
sim_dir = Path('data/simulations')
sim_files = sorted(sim_dir.glob('sim_*.json'), key=lambda x: x.stat().st_mtime, reverse=True)[:10]

if not sim_files:
    print("No simulation files found")
    exit()

print(f"Checking last {len(sim_files)} simulations:")
print("-" * 70)

mismatches = []
elite_found = []

for sim_file in sim_files:
    try:
        with open(sim_file, 'r') as f:
            sim = json.load(f)
        
        whale_addr = sim.get('whale_address', '')
        is_elite_in_sim = sim.get('is_elite', False)
        status = sim.get('status', 'unknown')
        
        # Check if whale SHOULD be elite
        whale_lower = whale_addr.lower()
        should_be_elite = whale_lower in elite_addrs
        
        # Get whale short for display
        whale_short = whale_addr[:42] if len(whale_addr) > 42 else whale_addr
        
        # Status indicator
        if should_be_elite and not is_elite_in_sim:
            indicator = "❌ MISMATCH (SHOULD BE ELITE)"
            mismatches.append({
                'whale': whale_addr,
                'file': sim_file.name,
                'should_be': True,
                'is': False
            })
        elif should_be_elite and is_elite_in_sim:
            indicator = "✅ CORRECT (IS ELITE)"
            elite_found.append(whale_addr)
        elif not should_be_elite and not is_elite_in_sim:
            indicator = "✅ CORRECT (NOT ELITE)"
        else:
            indicator = "⚠️  MISMATCH (SHOULD NOT BE ELITE)"
            mismatches.append({
                'whale': whale_addr,
                'file': sim_file.name,
                'should_be': False,
                'is': True
            })
        
        print(f"{whale_short}...")
        print(f"  Status: {status} | Flagged: {is_elite_in_sim} | Should be: {should_be_elite}")
        print(f"  {indicator}")
        print()
        
    except Exception as e:
        print(f"Error reading {sim_file.name}: {e}")
        print()

print("-" * 70)
print("SUMMARY:")
print(f"  Total checked: {len(sim_files)}")
print(f"  Elite whales found: {len(elite_found)}")
print(f"  Mismatches: {len(mismatches)}")

if mismatches:
    print()
    print("⚠️  MISMATCHES FOUND:")
    for m in mismatches:
        print(f"  Whale: {m['whale'][:42]}...")
        print(f"    File: {m['file']}")
        print(f"    Should be elite: {m['should_be']}")
        print(f"    Actually flagged: {m['is']}")
        print()
    
    if any(m['should_be'] for m in mismatches):
        print("❌ FIX NOT WORKING - Elite whales not being flagged!")
    else:
        print("✅ All mismatches are false positives (non-elite flagged as elite)")
else:
    print()
    print("✅ NO MISMATCHES - All flags are correct!")

if elite_found:
    print()
    print("✅ ELITE WHALES FOUND IN RECENT SIMULATIONS:")
    for whale in elite_found:
        print(f"  {whale}")

print("=" * 70)
