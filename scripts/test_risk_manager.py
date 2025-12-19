"""Test RiskManager functionality"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from src.risk import RiskManager
except ImportError:
    # Try direct import
    import importlib.util
    spec = importlib.util.spec_from_file_location("risk_manager", project_root / "src" / "risk" / "risk_manager.py")
    risk_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(risk_module)
    RiskManager = risk_module.RiskManager

print("="*80)
print("🧪 TESTING RISK MANAGER")
print("="*80)
print()

# Initialize with $1000 bankroll
rm = RiskManager(bankroll=1000)

# Get initial status
status = rm.get_risk_status()
print("Initial Status:")
print(f"  Bankroll: ${status['bankroll']:.2f}")
print(f"  Daily loss limit: ${status['daily_loss_limit']:.2f}")
print(f"  Max positions: {status['max_positions']}")
print(f"  Max position size: ${status['max_position_size']:.0f}")
print()

# Test 1: Small trade (should pass)
allowed, reason = rm.can_trade(50)
print(f"Test 1: Trade $50")
print(f"  Allowed: {allowed}")
print(f"  Reason: {reason}")
print()

# Test 2: Large trade (should pass if under 5%)
allowed2, reason2 = rm.can_trade(100)
print(f"Test 2: Trade $100")
print(f"  Allowed: {allowed2}")
print(f"  Reason: {reason2}")
print()

# Test 3: Too large trade (should fail)
allowed3, reason3 = rm.can_trade(1000)
print(f"Test 3: Trade $1000")
print(f"  Allowed: {allowed3}")
print(f"  Reason: {reason3}")
print()

# Test 4: Add positions
print("Test 4: Adding positions")
for i in range(6):
    success, msg = rm.add_position(
        market_slug=f"test-market-{i}",
        entry_price=0.65,
        size=50,
        side='YES'
    )
    print(f"  Position {i+1}: {success} - {msg}")
print()

# Final status
final_status = rm.get_risk_status()
print("Final Status:")
print(f"  Active positions: {final_status['active_positions']}")
print(f"  Bankroll remaining: ${final_status['bankroll']:.2f}")
print(f"  Kill switch: {final_status['kill_switch_active']}")
print()

print("="*80)
print("✅ RiskManager tests complete")
print("="*80)
