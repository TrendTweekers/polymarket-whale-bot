"""Check watcher logs for errors"""
import subprocess
import re
import os
import glob

print("="*80)
print("🔍 CHECKING WATCHER LOGS FOR ERRORS")
print("="*80)
print()

# Find latest terminal log
log_files = glob.glob("C:/Users/User/.cursor/projects/c-Users-User-Documents-polymarket-whale-engine/terminals/*.txt")
if log_files:
    latest_log = max(log_files, key=lambda x: os.path.getmtime(x))
    print(f"📄 Checking log: {os.path.basename(latest_log)}")
    print()
    
    with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Count errors
    error_patterns = [
        r'Error|Exception|Failed|closed|disconnected|timeout',
        r'⚠️|❌',
        r'Telegram.*failed',
        r'anomaly.*error'
    ]
    
    errors = []
    for pattern in error_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            errors.extend(matches)
    
    if errors:
        print(f"⚠️ Found {len(errors)} potential errors/warnings")
        print()
        print("Recent errors:")
        # Get last 100 lines and find errors
        lines = content.split('\n')
        error_lines = []
        for i, line in enumerate(lines[-500:], len(lines)-500):
            if any(pattern in line.lower() for pattern in ['error', 'exception', 'failed', '⚠️', '❌']):
                error_lines.append((i+1, line.strip()))
        
        for line_num, line in error_lines[-10:]:
            print(f"  Line {line_num}: {line[:100]}")
    else:
        print("✅ No errors found in logs!")
    
    # Check for Telegram notifications
    telegram_mentions = content.lower().count('telegram')
    print()
    print(f"📱 Telegram mentions in log: {telegram_mentions}")
    
    if 'telegram notification' in content.lower() or 'telegram.*sent' in content.lower():
        print("✅ Telegram notifications appear to be working")
    else:
        print("⚠️ No Telegram notification messages found")
        print("   This could mean:")
        print("   • No trades met notification criteria")
        print("   • Notifications are failing silently")
    
    print()
    print("="*80)
else:
    print("❌ No log files found")
