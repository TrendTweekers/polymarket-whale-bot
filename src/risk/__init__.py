"""
Risk Management Module
======================
Hard risk limits to prevent catastrophic losses

Implements Kimi's safety requirements:
- Daily loss limit (2% hard stop)
- Position count limit (max 5)
- Position size limit (max 5% per trade)
- Kill switch functionality
"""

from .risk_manager import RiskManager

__all__ = ['RiskManager']
