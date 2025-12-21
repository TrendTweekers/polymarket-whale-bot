"""Quick system status check"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("="*80)
print("📊 SYSTEM STATUS CHECK")
print("="*80)
print()

# Check watcher process
try:
    import psutil
    watcher_running = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            if proc.info['name'] == 'python.exe':
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'realtime_whale_watcher' in cmdline:
                    watcher_running = True
                    runtime = datetime.now() - datetime.fromtimestamp(proc.info['create_time'])
                    print(f"✅ Watcher running (PID: {proc.info['pid']}, Runtime: {runtime})")
                    break
        except:
            continue
    
    if not watcher_running:
        print("❌ Watcher process not found")
except ImportError:
    print("⚠️ psutil not available - cannot check process")

print()

# Check trade data
trades_file = project_root / "data" / "realtime_whale_trades.json"
if trades_file.exists():
    with open(trades_file, 'r') as f:
        trades = json.load(f)
    
    total_trades = len(trades)
    now = datetime.now()
    hour_ago = now - timedelta(hours=1)
    
    recent_trades = [
        t for t in trades
        if datetime.fromisoformat(t['timestamp'].replace('Z', '+00:00')) > hour_ago
    ]
    
    whale_trades = [t for t in trades if t.get('is_monitored_whale')]
    high_conf_trades = [t for t in trades if t.get('whale_confidence', 0) >= 0.65]
    
    print(f"📈 Trade Statistics:")
    print(f"   Total trades detected: {total_trades}")
    print(f"   Trades in last hour: {len(recent_trades)}")
    print(f"   Monitored whale trades: {len(whale_trades)}")
    print(f"   High-confidence trades (≥65%): {len(high_conf_trades)}")
else:
    print("⚠️ No trade data file found")

print()

# Check dynamic whales
whales_file = project_root / "data" / "dynamic_whale_state.json"
if whales_file.exists():
    with open(whales_file, 'r') as f:
        whale_data = json.load(f)
    
    whales = whale_data.get('whales', {})
    total = len(whales)
    high_conf = sum(1 for w in whales.values() if w.get('confidence', 0) >= 0.70)
    
    print(f"🐋 Dynamic Whale Statistics:")
    print(f"   Total whales discovered: {total}")
    print(f"   High-confidence (≥70%): {high_conf}")
else:
    print("⚠️ No dynamic whale state file found")

print()

# Check elite whales
elite_file = project_root / "data" / "api_validation_results.json"
if elite_file.exists():
    with open(elite_file, 'r') as f:
        elite_data = json.load(f)
    
    elite_count = elite_data.get('elite_count', 0)
    print(f"⭐ Elite Whales:")
    print(f"   API validated elite whales: {elite_count}")
else:
    print("⚠️ No elite whale validation file found")

print()
print("="*80)
print("✅ Status check complete")
print("="*80)
