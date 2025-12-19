"""Task 2: Current whale statistics"""
from dynamic_whale_manager import DynamicWhaleManager

m = DynamicWhaleManager()
stats = m.get_whale_stats()
print(f'Total: {stats["total_whales"]} | High-conf (≥70%): {stats["high_confidence"]} | Active: {stats["active_whales"]}')
