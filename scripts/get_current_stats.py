"""Get current system statistics"""
from dynamic_whale_manager import DynamicWhaleManager

m = DynamicWhaleManager()
stats = m.get_whale_stats()

print('='*80)
print('CURRENT SYSTEM STATUS')
print('='*80)
print(f'Total Whales: {stats["total_whales"]}')
print(f'High-Confidence (≥70%): {stats["high_confidence"]}')
print(f'Active Whales: {stats["active_whales"]}')
print(f'Average Confidence: {stats["avg_confidence"]:.1%}')
print('='*80)
