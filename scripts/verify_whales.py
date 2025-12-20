#!/usr/bin/env python3
"""Verify which whales will be monitored"""
import json

with open('data/phase2_analysis_results.json', 'r') as f:
    results = json.load(f)

print("=" * 60)
print("WHALE SELECTION VERIFICATION")
print("=" * 60)
print()

# Show all top 5 whales
print("Top 5 whales from Phase 2 analysis:")
for i, whale in enumerate(results['top_5_whales'], 1):
    win_rate = whale.get('win_rate_1min', 0)
    print(f"  {i}. {whale['address'][:16]}... - Win Rate: {win_rate:.1f}%")

print()

# Filter to >50% win rate
profitable_whales = [
    w for w in results['top_5_whales']
    if w.get('win_rate_1min', 0) > 50
]

print(f"Whales with >50% win rate: {len(profitable_whales)}")
print()

if profitable_whales:
    print("✅ Will monitor these whales:")
    for i, whale in enumerate(profitable_whales[:3], 1):
        win_rate = whale.get('win_rate_1min', 0)
        delay_cost = whale.get('avg_delay_cost_1min', 0)
        print(f"  {i}. {whale['address'][:16]}...")
        print(f"     Win Rate: {win_rate:.1f}%")
        print(f"     Delay Cost: {delay_cost:+.2%}")
        print()
else:
    print("❌ No whales with >50% win rate found!")

print("=" * 60)
