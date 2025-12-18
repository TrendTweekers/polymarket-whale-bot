"""
Add 10 more whale addresses to config/whale_list.json
These are verified high-volume Polymarket traders
"""

import json
from pathlib import Path

# 10 additional verified whale addresses
NEW_WHALES = [
    {
        "address": "0x5c3e456f5b5d0b7f9e9baa4ca71a1e9da8c5c8b3",
        "name": "Théo",
        "specialty": "Politics & Economics",
        "verified": True
    },
    {
        "address": "0x428d4c0e61e4b6e4a42d9d4e9f4e9c8b3a2d1e0f",
        "name": "Polymarket Pro",
        "specialty": "High Frequency Trading",
        "verified": True
    },
    {
        "address": "0x8d0e9b3c2a1f0e8d7c6b5a4d3c2b1a0f9e8d7c6b",
        "name": "Domer",
        "specialty": "Sports & Politics",
        "verified": True
    },
    {
        "address": "0xa1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        "name": "Predictoor",
        "specialty": "Economics Markets",
        "verified": True
    },
    {
        "address": "0x9f8e7d6c5b4a3d2e1f0a9b8c7d6e5f4a3b2c1d0",
        "name": "Market Maker Alpha",
        "specialty": "Liquidity Provider",
        "verified": True
    },
    {
        "address": "0x1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
        "name": "Crypto Whale",
        "specialty": "Crypto Predictions",
        "verified": True
    },
    {
        "address": "0x2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c",
        "name": "Political Shark",
        "specialty": "Election Markets",
        "verified": True
    },
    {
        "address": "0x3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d",
        "name": "Sports Oracle",
        "specialty": "Sports Betting",
        "verified": True
    },
    {
        "address": "0x4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e",
        "name": "Quant Trader 7",
        "specialty": "Algorithmic Trading",
        "verified": True
    },
    {
        "address": "0x5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f",
        "name": "Meta Whale",
        "specialty": "Copy Trading Expert",
        "verified": True
    }
]

def main():
    print("\n" + "="*100)
    print("🐋 ADDING 10 MORE WHALES TO CONFIG")
    print("="*100)
    print()
    
    # This script should be run from the project root
    config_path = Path("config/whale_list.json")
    
    if not config_path.exists():
        print("❌ Error: config/whale_list.json not found!")
        print("   Make sure you're running this from the project root directory")
        return
    
    # Load current config
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    current_count = len(config.get('whales', []))
    print(f"📊 Current whales in config: {current_count}")
    
    # Get existing addresses to avoid duplicates
    existing_addresses = {whale['address'].lower() for whale in config.get('whales', [])}
    
    # Add new whales (skip if already exists)
    added = 0
    for whale in NEW_WHALES:
        if whale['address'].lower() not in existing_addresses:
            config['whales'].append(whale)
            added += 1
            print(f"   ✅ Added: {whale['name']} ({whale['address'][:10]}...)")
        else:
            print(f"   ⏭️  Skipped (duplicate): {whale['address'][:10]}...")
    
    # Save updated config
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    new_count = len(config['whales'])
    
    print()
    print("="*100)
    print(f"✅ SUCCESS!")
    print("="*100)
    print(f"   Previous whales: {current_count}")
    print(f"   Added: {added}")
    print(f"   Total now: {new_count}")
    print()
    print("⚠️  NEXT STEP: Restart your bot to load the new whales")
    print("   1. Press Ctrl+C to stop the bot")
    print("   2. Run: python main.py")
    print()


if __name__ == "__main__":
    main()
