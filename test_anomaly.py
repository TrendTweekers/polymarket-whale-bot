"""Test anomaly detector"""
import traceback
from market_anomaly_detector import MarketAnomalyDetector

d = MarketAnomalyDetector()
trade = {
    'slug': 'test-market',
    'price': 0.5,
    'size': 100,
    'timestamp': 1766074000,  # Integer timestamp
    'proxyWallet': '0x123'
}

try:
    d.update_market_state(trade)
    print('✅ Success')
except Exception as e:
    print('❌ Error:')
    traceback.print_exc()
