#!/usr/bin/env python3
"""Quick check of latest simulation"""
import json
from pathlib import Path

# Get latest simulation
sim_dir = Path("data/simulations")
latest = sorted(sim_dir.glob("sim_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[0]
sim = json.loads(latest.read_text())

print(f"Latest Simulation: {latest.name}")
print(f"Whale Address: {sim.get('whale_address', 'N/A')}")
print(f"Is Elite: {sim.get('is_elite', False)}")
print(f"Confidence: {sim.get('confidence', 0)}")

# Check if whale is in elite list
whale_addr = sim.get('whale_address', '').lower()
with open('data/api_validation_results.json', 'r') as f:
    data = json.load(f)
results = data if isinstance(data, list) else data.get('results', [])
elite_addrs = {w['address'].lower() for w in results if w.get('passes', False)}

print(f"\nElite Check:")
print(f"  Whale in elite list: {whale_addr in elite_addrs}")
print(f"  Total elite whales: {len(elite_addrs)}")
