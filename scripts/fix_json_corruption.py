"""Fix JSON corruption in dynamic_whale_state.json"""
import json
from pathlib import Path

file_path = Path("data/dynamic_whale_state.json")
backup_path = Path("data/dynamic_whale_state.json.backup")

print("="*80)
print("🔧 FIXING JSON CORRUPTION")
print("="*80)
print()

# Backup first
if file_path.exists():
    print(f"📦 Creating backup...")
    import shutil
    shutil.copy(file_path, backup_path)
    print(f"✅ Backup created: {backup_path}")
    print()

# Try to load and repair
print("🔍 Attempting to load JSON...")
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print("✅ JSON file is valid! No corruption detected.")
    print(f"   Whales in file: {len(data)}")
except json.JSONDecodeError as e:
    print(f"❌ JSON Error: {e}")
    print(f"   Line: {e.lineno}, Column: {e.colno}")
    print()
    print("🔧 Attempting repair...")
    
    # Try to read line by line and find the issue
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"   Total lines: {len(lines)}")
    print(f"   Error at line: {e.lineno}")
    
    # Show context around error
    start = max(0, e.lineno - 5)
    end = min(len(lines), e.lineno + 5)
    print()
    print("   Context around error:")
    for i in range(start, end):
        marker = ">>> " if i == e.lineno - 1 else "    "
        print(f"{marker}{i+1:6d}: {lines[i].rstrip()[:80]}")
    
    print()
    print("⚠️ Manual repair needed - JSON structure is corrupted")
    print("   Recommendation: Rebuild from trade data or restore from backup")
    
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()

print()
print("="*80)
