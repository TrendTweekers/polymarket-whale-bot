"""Analyze quality of discovered whales"""
from dynamic_whale_manager import DynamicWhaleManager

m = DynamicWhaleManager()

# Get high-confidence whales
high_conf = [(addr, data) for addr, data in m.whales.items() 
             if data['confidence'] >= 0.7]
high_conf.sort(key=lambda x: x[1]['confidence'], reverse=True)

print('='*80)
print('TOP 20 HIGH-CONFIDENCE WHALES (≥70%)')
print('='*80)
print()

for i, (addr, data) in enumerate(high_conf[:20], 1):
    print(f'{i:2}. {addr[:16]}...')
    print(f'    Confidence: {data["confidence"]:.0%}')
    print(f'    Trades: {data["trade_count"]}')
    print(f'    Value: ${data["total_value"]:,.0f}')
    print(f'    Markets: {len(data["markets_traded"])}')
    print(f'    Last active: {data["last_activity"][:19]}')
    print()

print('='*80)
print(f'Total high-confidence (≥70%): {len(high_conf)}')
print('='*80)
