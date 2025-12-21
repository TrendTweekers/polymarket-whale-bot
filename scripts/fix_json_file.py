"""Fix corrupted JSON file"""
import json
import shutil
from pathlib import Path

state_file = Path("data/dynamic_whale_state.json")
backup_file = Path("data/dynamic_whale_state.json.backup")

if state_file.exists():
    # Backup corrupted file
    try:
        shutil.copy(state_file, backup_file)
        print(f"✅ Backed up corrupted file to {backup_file}")
    except Exception as e:
        print(f"⚠️ Could not backup: {e}")
    
    # Create new empty file
    new_data = {}
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, indent=2)
    print(f"✅ Created new empty whale state file")
    print(f"   Old file backed up - can recover data later if needed")
else:
    print("File doesn't exist - will be created on first run")
