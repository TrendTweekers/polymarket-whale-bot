#!/usr/bin/env python3
"""
Paper Trading with Auto-Restart
Automatically restarts paper trading if it crashes
"""
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

def run_with_auto_restart(max_restarts=100, restart_delay=10):
    """Run paper trading with auto-restart on crash"""
    restart_count = 0
    log_file = Path('logs/paper_trading_restarts.log')
    log_file.parent.mkdir(exist_ok=True)
    
    print("=" * 60)
    print("🚀 PAPER TRADING WITH AUTO-RESTART")
    print("=" * 60)
    print(f"Max restarts: {max_restarts}")
    print(f"Restart delay: {restart_delay}s")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()
    
    while restart_count < max_restarts:
        try:
            if restart_count > 0:
                print(f"🔄 Restart #{restart_count}")
                with open(log_file, 'a') as f:
                    f.write(f"[{datetime.now()}] Restart #{restart_count}\n")
            
            print(f"▶️ Starting paper trading (attempt {restart_count + 1})...")
            print()
            
            result = subprocess.run(
                [sys.executable, "scripts/paper_trading.py"],
                check=False
            )
            
            if result.returncode == 0:
                print("\n✅ Paper trading stopped cleanly")
                break
            
            restart_count += 1
            if restart_count >= max_restarts:
                print(f"\n❌ Maximum restarts ({max_restarts}) reached")
                break
            
            print(f"\n⚠️ Paper trading crashed (exit code: {result.returncode})")
            print(f"   Restarting in {restart_delay} seconds...")
            print()
            time.sleep(restart_delay)
            
        except KeyboardInterrupt:
            print("\n\n⚠️ Stopped by user")
            break
        except Exception as e:
            restart_count += 1
            print(f"\n❌ Error: {e}")
            if restart_count < max_restarts:
                print(f"   Restarting in {restart_delay} seconds...")
                time.sleep(restart_delay)
            else:
                print(f"   Maximum restarts reached")
                break
    
    print(f"\n✅ Wrapper stopped. Total restarts: {restart_count}")
    if restart_count > 0:
        print(f"   Log file: {log_file}")

if __name__ == "__main__":
    run_with_auto_restart(max_restarts=100, restart_delay=10)
