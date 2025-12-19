"""Check confidence of monitored whales"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dynamic_whale_manager import DynamicWhaleManager

# Monitored whales that have been trading
monitored_wallets = [
    '0x6bab41a0dc40d6dd4c1a915b8c01969479fd1292',
    '0xed107a85a4585a381e48c7f7ca4144909e7dd2e5'
]

m = DynamicWhaleManager()

print("="*80)
print("🐋 MONITORED WHALE CONFIDENCE CHECK")
print("="*80)
print()

for wallet in monitored_wallets:
    whale_data = m.whales.get(wallet)
    if whale_data:
        confidence = whale_data.get('confidence', 0)
        trade_count = whale_data.get('trade_count', 0)
        total_value = whale_data.get('total_value', 0)
        
        print(f"{wallet[:16]}...")
        print(f"  Confidence: {confidence:.0%}")
        print(f"  Trade count: {trade_count}")
        print(f"  Total value: ${total_value:,.0f}")
        print(f"  Status: {'✅ HIGH-CONFIDENCE (≥70%)' if confidence >= 0.70 else '❌ BELOW THRESHOLD (<70%)'}")
        print()
    else:
        print(f"{wallet[:16]}...")
        print(f"  Status: ⚠️ NOT IN DYNAMIC MANAGER")
        print(f"  Default confidence: 50% (static list whale)")
        print(f"  Result: ❌ BELOW THRESHOLD (needs ≥70%)")
        print()

print("="*80)
print("💡 EXPLANATION:")
print("="*80)
print()
print("These whales are from your static whale list (config/whale_list.json).")
print("They get a default confidence of 50% until they accumulate enough")
print("trades in the dynamic manager to build a real confidence score.")
print()
print("To get notifications for these whales:")
print("  1. Wait for them to accumulate more trades (builds confidence)")
print("  2. OR lower the notification threshold from 70% to 50%")
print("  3. OR manually set their confidence in dynamic_whale_manager.py")
print()
