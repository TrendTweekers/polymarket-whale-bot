"""Quality check for discovered whales"""
from dynamic_whale_manager import DynamicWhaleManager

m = DynamicWhaleManager()
stats = m.get_whale_stats()

# Red flags to check
low_trade_count = sum(1 for w in m.whales.values() if w['trade_count'] < 3)
low_value = sum(1 for w in m.whales.values() if w['total_value'] < 100)
single_market = sum(1 for w in m.whales.values() if len(w['markets_traded']) == 1)

print('='*80)
print('QUALITY CHECK')
print('='*80)
print()
print(f'Total whales: {stats["total_whales"]}')
print(f'High confidence (≥70%): {stats["high_confidence"]}')
print(f'Average confidence: {stats["avg_confidence"]:.1%}')
print()

print('Potential Issues:')
print(f'  • Low trade count (<3): {low_trade_count}')
print(f'  • Low value (<$100): {low_value}')
print(f'  • Single market only: {single_market}')
print()

quality_score = (stats['high_confidence'] / stats['total_whales']) * 100 if stats['total_whales'] > 0 else 0
print(f'Quality Score: {quality_score:.1f}% high-confidence')
print()

if quality_score > 8:
    print('✅ QUALITY: EXCELLENT (>8% high-confidence)')
    print('✅ RECOMMENDATION: Ready for Phase 2!')
elif quality_score > 5:
    print('✅ QUALITY: GOOD (>5% high-confidence)')
    print('✅ RECOMMENDATION: Can start Phase 2')
else:
    print('⚠️ QUALITY: Moderate (<5% high-confidence)')
    print('⚠️ RECOMMENDATION: Tune thresholds first')

print()
print('='*80)
