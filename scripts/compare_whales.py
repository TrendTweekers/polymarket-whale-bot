"""Compare old static whale list vs new dynamic whale list"""
from dynamic_whale_manager import DynamicWhaleManager
import json

# Load old whales
with open('config/whale_list.json', 'r') as f:
    old_config = json.load(f)
old_whales = [w['address'].lower() for w in old_config['whales']]

# Load new whales
manager = DynamicWhaleManager()
new_whales = [w.lower() for w in manager.get_active_whales(min_confidence=0.6)]

print("="*80)
print("🐋 WHALE LIST COMPARISON")
print("="*80)
print()
print(f'Old static list: {len(old_whales)} whales')
print(f'New dynamic list: {len(new_whales)} active whales')
print(f'Overlap: {len(set(old_whales) & set(new_whales))} whales in both lists')
print()

# Show overlap details
overlap = set(old_whales) & set(new_whales)
if overlap:
    print(f"Whales in both lists ({len(overlap)}):")
    for addr in list(overlap)[:10]:
        print(f"  • {addr[:16]}...")
    if len(overlap) > 10:
        print(f"  ... and {len(overlap) - 10} more")
    print()

# Show new whales not in old list
new_only = set(new_whales) - set(old_whales)
if new_only:
    print(f"New whales discovered ({len(new_only)}):")
    for addr in list(new_only)[:10]:
        whale_data = manager.whales.get(addr, {})
        conf = whale_data.get('confidence', 0) * 100
        trades = whale_data.get('trade_count', 0)
        value = whale_data.get('total_value', 0)
        print(f"  • {addr[:16]}... | {conf:.0f}% | ${value:,.0f} | {trades} trades")
    if len(new_only) > 10:
        print(f"  ... and {len(new_only) - 10} more")
    print()

print("Conclusion:")
if len(new_whales) > len(old_whales):
    print(f'✅ Found {len(new_whales) - len(old_whales)} MORE active whales!')
if len(set(old_whales) & set(new_whales)) == 0:
    print('✅ Discovered completely NEW set of active traders!')
else:
    print(f'✅ {len(set(old_whales) & set(new_whales))} whales overlap between old and new lists')
    print(f'✅ {len(new_only)} completely new active whales discovered!')
print("="*80)
