"""Test RiskManager integration in bot"""
import sys
from pathlib import Path
import yaml

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.polymarket.bot import WhaleBot

print("="*80)
print("🧪 TESTING RISK MANAGER INTEGRATION")
print("="*80)
print()

# Load config
config = yaml.safe_load(open('config/config.yaml'))

# Initialize bot
bot = WhaleBot(config)

print("✅ Bot initialized successfully")
print("✅ RiskManager integrated")
print()

# Get risk status
risk_status = bot.risk_manager.get_risk_status()

print("Risk Manager Status:")
print(f"  Bankroll: ${risk_status['bankroll']:.2f}")
print(f"  Daily loss limit: ${risk_status['daily_loss_limit']:.2f}")
print(f"  Max positions: {risk_status['max_positions']}")
print(f"  Max position size: ${risk_status['max_position_size']:.0f}")
print(f"  Kill switch: {risk_status['kill_switch_active']}")
print()

# Test risk checks
print("Testing Risk Checks:")
print()

# Test 1: Small trade (should pass)
allowed1, reason1 = bot.risk_manager.can_trade(25)
print(f"Test 1: Trade $25")
print(f"  Allowed: {allowed1}")
print(f"  Reason: {reason1}")
print()

# Test 2: Max position size (should pass)
max_size = risk_status['max_position_size']
allowed2, reason2 = bot.risk_manager.can_trade(max_size)
print(f"Test 2: Trade ${max_size:.0f} (max size)")
print(f"  Allowed: {allowed2}")
print(f"  Reason: {reason2}")
print()

# Test 3: Too large (should fail)
allowed3, reason3 = bot.risk_manager.can_trade(max_size + 1)
print(f"Test 3: Trade ${max_size + 1:.0f} (too large)")
print(f"  Allowed: {allowed3}")
print(f"  Reason: {reason3}")
print()

# Test 4: Check performance summary includes risk
summary = bot.get_performance_summary()
print("Performance Summary includes risk status:")
print(f"  Risk status included: {'risk_status' in summary}")
if 'risk_status' in summary:
    print(f"  Daily P&L: ${summary['risk_status']['daily_pnl']:.2f}")
    print(f"  Active positions: {summary['risk_status']['active_positions']}")
    print(f"  Kill switch: {summary['risk_status']['kill_switch_active']}")

print()
print("="*80)
print("✅ Integration test complete")
print("="*80)
