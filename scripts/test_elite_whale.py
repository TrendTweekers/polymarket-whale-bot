"""Quick test to check if a whale address is in elite list"""
import json
from pathlib import Path

# Load elite whales
with open('data/api_validation_results.json', 'r') as f:
    data = json.load(f)

elite = [w for w in data.get('results', []) if w.get('passes', False)]
elite_addrs = [w['address'].lower() for w in elite]

print(f"Total elite whales: {len(elite_addrs)}")
print()

# Test the frequently-simulated whale
test = '0xd18966a2fcfc40697600c0d3b5cac3a96cd32316'.lower()

print(f"Testing: {test}")
print()

if test in elite_addrs:
    print('✅ 0xd18966... IS in elite list')
    whale = [w for w in elite if w['address'].lower() == test][0]
    print(f'   Trades: {whale.get("trade_count", 0)}')
    print(f'   Volume: ${whale.get("total_volume_usd", 0):,.0f}')
    print(f'   Profit: {whale.get("total_profit_eth", 0):.2f} ETH')
    print(f'   Win Rate: {whale.get("win_rate", 0)*100:.1f}%')
else:
    print('❌ 0xd18966... NOT in elite list')
    # Check if any elite address starts with 0xd18966
    matches = [a for a in elite_addrs if a.startswith('0xd18966')]
    if matches:
        print(f'   But found similar: {matches[0]}')
    else:
        print('   No similar addresses found')

print()
print("Recent simulation whales:")
sim_dir = Path('data/simulations')
sims = list(sim_dir.glob('sim_*.json'))
recent = sorted(sims, key=lambda x: x.stat().st_mtime, reverse=True)[:5]
for s in recent:
    whale_short = s.stem.split('_')[-1]
    print(f"  {whale_short}")
    
    # Check if this whale is elite
    whale_full = None
    for addr in elite_addrs:
        if addr.startswith(whale_short.lower()):
            whale_full = addr
            break
    
    if whale_full:
        print(f"    → IS ELITE: {whale_full}")
    else:
        print(f"    → NOT in elite list")
