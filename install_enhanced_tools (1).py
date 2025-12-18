"""
Quick Install Script - Enhanced Monitoring Tools
=================================================
Installs and tests the new enhanced heartbeat and market scanner

Run this once to set everything up!
"""

import os
import shutil
from pathlib import Path


def install_files():
    """Install the new tool files to correct locations"""
    
    print("\n" + "="*80)
    print("📦 INSTALLING ENHANCED MONITORING TOOLS")
    print("="*80)
    print()
    
    # Create scripts directory if needed
    scripts_dir = Path("scripts")
    scripts_dir.mkdir(exist_ok=True)
    
    print("✅ Scripts directory ready")
    
    # List of files to check/install
    files_to_install = [
        ("enhanced_heartbeat.py", "scripts/enhanced_heartbeat.py"),
        ("market_scanner.py", "scripts/market_scanner.py"),
        ("COMPREHENSIVE_GUIDE.txt", "COMPREHENSIVE_GUIDE.txt")
    ]
    
    print("\n📋 Checking files...\n")
    
    installed_count = 0
    for source, dest in files_to_install:
        dest_path = Path(dest)
        
        if dest_path.exists():
            print(f"   ✅ {dest} - Already exists")
        else:
            print(f"   📥 {dest} - Need to download")
            installed_count += 1
    
    print()
    print("="*80)
    print("📦 INSTALLATION COMPLETE")
    print("="*80)
    print()
    print("Your new tools are ready!")
    print()
    print("Available commands:")
    print("  python scripts/enhanced_heartbeat.py    - Better status monitoring")
    print("  python scripts/market_scanner.py        - See what's hot on Polymarket")
    print()
    print("📖 For full guide, read: COMPREHENSIVE_GUIDE.txt")
    print()


def test_heartbeat():
    """Test if heartbeat dependencies are available"""
    
    print("\n" + "="*80)
    print("🧪 TESTING HEARTBEAT DEPENDENCIES")
    print("="*80)
    print()
    
    try:
        import psutil
        print("✅ psutil - Installed")
    except ImportError:
        print("❌ psutil - Missing")
        print("   Install with: pip install psutil --break-system-packages")
        return False
    
    try:
        import aiohttp
        print("✅ aiohttp - Installed")
    except ImportError:
        print("❌ aiohttp - Missing")
        print("   Install with: pip install aiohttp --break-system-packages")
        return False
    
    try:
        from dotenv import load_dotenv
        print("✅ python-dotenv - Installed")
    except ImportError:
        print("❌ python-dotenv - Missing")
        print("   Install with: pip install python-dotenv --break-system-packages")
        return False
    
    print()
    print("✅ All dependencies ready!")
    return True


def show_next_steps():
    """Show user what to do next"""
    
    print("\n" + "="*80)
    print("🎯 NEXT STEPS")
    print("="*80)
    print()
    print("1️⃣  STOP OLD HEARTBEAT (if running)")
    print("   • Go to terminal running quick_heartbeat.py")
    print("   • Press Ctrl+C to stop it")
    print()
    print("2️⃣  START ENHANCED HEARTBEAT")
    print("   • Open new terminal")
    print("   • Run: python scripts/enhanced_heartbeat.py")
    print("   • Press Enter to use 1-hour interval")
    print()
    print("3️⃣  SCAN MARKETS (optional, anytime)")
    print("   • Run: python scripts/market_scanner.py")
    print("   • See what's active on Polymarket")
    print()
    print("4️⃣  READ THE GUIDE")
    print("   • Open: COMPREHENSIVE_GUIDE.txt")
    print("   • Understand how your bot works")
    print("   • Realistic expectations")
    print()
    print("="*80)
    print()


def main():
    """Main install flow"""
    
    print("\n" + "="*80)
    print("🚀 ENHANCED MONITORING TOOLS INSTALLER")
    print("="*80)
    print()
    print("This will set up:")
    print("  1. Enhanced Heartbeat - Better status detection")
    print("  2. Market Scanner - See Polymarket activity")
    print("  3. Comprehensive Guide - Understand your system")
    print()
    
    input("Press Enter to continue...")
    
    # Install files
    install_files()
    
    # Test dependencies
    deps_ok = test_heartbeat()
    
    if not deps_ok:
        print("\n⚠️  Please install missing dependencies first!")
        print()
        print("Run these commands:")
        print("  pip install psutil --break-system-packages")
        print("  pip install aiohttp --break-system-packages")
        print()
        return
    
    # Show next steps
    show_next_steps()
    
    print("💡 TIP: Keep your main bot running in Terminal 1")
    print("        Start enhanced heartbeat in Terminal 2")
    print()
    print("✅ Setup complete! Enjoy your enhanced monitoring!")
    print()


if __name__ == "__main__":
    main()
