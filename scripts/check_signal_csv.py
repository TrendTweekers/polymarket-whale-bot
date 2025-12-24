#!/usr/bin/env python3
"""Check signals CSV for condition_ids."""
import csv
from pathlib import Path

csv_file = Path("logs/signals_2025-12-21.csv")
if not csv_file.exists():
    csv_file = Path("logs/signals_2025-12-22.csv")

if csv_file.exists():
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if 'raiders' in r.get('market', '').lower() or 'texans' in r.get('market', '').lower() or 'nfl' in r.get('market', '').lower()]
        
        print(f"Found {len(rows)} NFL/sports signals in {csv_file.name}")
        print("=" * 80)
        
        for r in rows[:5]:
            print(f"\nMarket: {r.get('market', '')[:70]}")
            print(f"Condition ID: {r.get('condition_id', 'N/A')}")
            print(f"Market ID: {r.get('market_id', 'N/A')}")
            print(f"Timestamp: {r.get('timestamp', 'N/A')}")
else:
    print(f"CSV file not found: {csv_file}")

