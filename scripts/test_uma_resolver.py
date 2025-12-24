#!/usr/bin/env python3
"""Test UMA on-chain resolver."""
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.polymarket.uma_resolver import check_uma_resolution, get_ancillary_data_from_condition

# Test NFL trade condition_id
condition_id = "0x0e4ccd69c581deb1aad6f587083a4800d458d6a12f3d202418a53e0c40b18c5a"

print(f"Testing UMA resolver for condition_id: {condition_id}")
print("=" * 80)

# Test ancillaryData extraction
print("\n1. Getting ancillaryData from condition_id...")
# Test with market title (preferred method)
market_title = "Raiders vs. Texans"
result = get_ancillary_data_from_condition(condition_id, market_title=market_title)
if result[0]:
    ancillary_data, timestamp, chain_id = result
    print(f"   [OK] AncillaryData: {ancillary_data.hex()[:66]}...")
    print(f"   Timestamp: {timestamp}")
    print(f"   Chain ID: {chain_id}")
else:
    print("   [FAIL] Failed to get ancillaryData")

# Test resolution check
print("\n2. Checking UMA resolution...")
result = check_uma_resolution(condition_id)
if result:
    print(f"   Resolved: {result.get('resolved', False)}")
    if result.get('resolved'):
        print(f"   [RESOLVED] Market is resolved!")
        print(f"   Winning Outcome Index: {result.get('winning_outcome_index')}")
        print(f"   Resolved Price: {result.get('resolved_price')}")
        print(f"   Resolution Time: {result.get('resolution_time')}")
    else:
        print(f"   [PENDING] Not resolved yet")
else:
    print("   [FAIL] Failed to check resolution")

