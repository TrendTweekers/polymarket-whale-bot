# src/polymarket/paper_trading.py
"""
Paper trading module - handles paper trade creation and stake computation.
"""
import os
import structlog
import re
from typing import Dict, Optional
from datetime import datetime

logger = structlog.get_logger()

# Paper trading configuration (loaded from env)
PAPER_MIN_CONFIDENCE = int(os.getenv("PAPER_MIN_CONFIDENCE", "60"))
PAPER_STAKE_EUR = float(os.getenv("PAPER_STAKE_EUR", "2.0"))  # Legacy - kept for backward compatibility
FX_EUR_USD = float(os.getenv("FX_EUR_USD", "1.10"))


def normalize_position(outcome_name: Optional[str], outcome_index: Optional[int]) -> str:
    """
    Normalize position from outcome_name and outcome_index.
    Returns YES, NO, or the outcome name in uppercase.
    """
    if outcome_name and outcome_name.strip():
        o = outcome_name.strip().lower()
        if o in ("yes", "no"):
            return o.upper()
        return outcome_name.strip().upper()
    
    if outcome_index is not None:
        # Polymarket convention: 0=Yes, 1=No (common)
        try:
            oi_int = int(outcome_index)
            return "YES" if oi_int == 0 else "NO"
        except Exception:
            pass
    
    return "UNKNOWN"


def _safe_position_name(trade: Dict) -> str:
    """
    Extract position/outcome name from trade dict with multiple fallbacks.
    Returns a safe string (never blank).
    """
    # First try to normalize from outcome_name/outcome_index (most reliable)
    outcome_name = trade.get("outcome_name") or trade.get("outcome")
    outcome_index = trade.get("outcome_index")
    normalized = normalize_position(outcome_name, outcome_index)
    if normalized != "UNKNOWN":
        return normalized
    
    # Fallback to other keys
    for k in ("position", "selected_outcome", "side_label"):
        v = trade.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    
    return "UNKNOWN"


def _range_hint(market_text: str, position_name: str) -> str:
    """
    Adds range hints for "between X and Y" markets:
      Yes (IN RANGE $LOW–$HIGH)
      No (OUTSIDE RANGE <$LOW OR >$HIGH)
    Only if the question contains "between X and Y".
    """
    if not market_text:
        return position_name
    
    # Match "between $X and $Y" or "between X and Y"
    m = re.search(r"between\s+\$?([\d,.]+)\s+and\s+\$?([\d,.]+)", market_text, re.IGNORECASE)
    if not m:
        return position_name
    
    low = m.group(1)
    high = m.group(2)
    p = (position_name or "").strip().lower()
    
    if p == "yes":
        return f"Yes (IN RANGE ${low}–${high})"
    if p == "no":
        return f"No (OUTSIDE RANGE <${low} OR >${high})"
    
    return position_name


def stake_eur_from_confidence(conf: int) -> float:
    """
    Calculate stake in EUR based on confidence level (max 6 EUR).
    
    Sizing rules:
    - Below 50 confidence → €0 (don't paper trade)
    - 50-70 → scale from €1 → €2
    - 70-90 → scale from €2 → €5
    - 90-100 → scale from €5 → €6 (capped)
    
    Args:
        conf: Confidence score (0-100)
        
    Returns:
        Stake amount in EUR (0.0 if below threshold, max 6.0)
    """
    try:
        c = float(conf)
    except Exception:
        return 0.0
    
    if c < 50:
        return 0.0
    
    if c <= 70:
        # 50->1.0, 70->2.0
        stake = 1.0 + (c - 50.0) * (1.0 / 20.0)
    elif c <= 90:
        # 70->2.0, 90->5.0
        stake = 2.0 + (c - 70.0) * (3.0 / 20.0)
    else:
        # 90->5.0, 100->6.0
        stake = 5.0 + (c - 90.0) * (1.0 / 10.0)
    
    return round(min(stake, 6.0), 2)


def should_paper_trade(confidence: int) -> bool:
    """
    Determine if a signal should create a paper trade based on confidence threshold.
    
    Args:
        confidence: Confidence score (0-100)
        
    Returns:
        True if confidence meets threshold, False otherwise
    """
    return confidence >= PAPER_MIN_CONFIDENCE


def compute_stake_usd(stake_eur: float, fx_eur_usd: float) -> float:
    """
    Convert stake from EUR to USD.
    
    Args:
        stake_eur: Stake amount in EUR
        fx_eur_usd: EUR to USD exchange rate
        
    Returns:
        Stake amount in USD
    """
    return stake_eur * fx_eur_usd


def open_paper_trade(signal_row: Dict, confidence: int = None) -> Dict:
    """
    Create a paper trade dictionary from a signal.
    
    Args:
        signal_row: Signal dictionary with all signal fields
        confidence: Confidence score (0-100). If None, extracted from signal_row.
        
    Returns:
        Paper trade dictionary ready for database insertion
    """
    # Extract confidence
    if confidence is None:
        confidence = signal_row.get("confidence", 0)
    
    # Calculate stake based on confidence
    stake_eur = round(stake_eur_from_confidence(confidence), 2)
    stake_usd = compute_stake_usd(stake_eur, FX_EUR_USD)
    
    entry_price = signal_row.get("whale_entry_price") or signal_row.get("entry_price") or signal_row.get("current_price")
    
    return {
        "signal_id": None,  # Will be set by storage layer
        "opened_at": signal_row.get("timestamp", datetime.utcnow().isoformat()),
        "status": "OPEN",
        "stake_eur": stake_eur,
        "stake_usd": stake_usd,
        "entry_price": entry_price,
        "outcome_index": signal_row.get("outcome_index"),
        "outcome_name": signal_row.get("outcome_name") or signal_row.get("outcome", ""),
        "side": signal_row.get("side", ""),
        "event_id": signal_row.get("event_id") or signal_row.get("condition_id", ""),
        "market_id": signal_row.get("market_id", ""),
        "token_id": signal_row.get("token_id", ""),
        "market": signal_row.get("market", ""),
        "category": signal_row.get("category", ""),
        "confidence": confidence
    }


def format_paper_trade_telegram(trade_dict: Dict) -> str:
    """
    Format Telegram message for paper trade opened.
    
    Args:
        trade_dict: Paper trade dictionary
        
    Returns:
        Formatted Telegram message string
    """
    market = trade_dict.get("market", "Unknown")
    market_short = (market[:50] + "...") if len(market) > 50 else market
    
    confidence = trade_dict.get("confidence", 0)
    confidence_str = f"{confidence}/100"
    
    # Use safe position name helper (never blank)
    position = _safe_position_name(trade_dict)
    
    # Add range hint with actual values
    position = _range_hint(market, position)
    
    stake_eur = trade_dict.get("stake_eur", 0.0)
    stake_usd = trade_dict.get("stake_usd", 0.0)
    entry_price = trade_dict.get("entry_price")
    entry_price_str = f"{entry_price:.4f}" if entry_price else "N/A"
    
    days_to_expiry = trade_dict.get("days_to_expiry")
    expiry_str = f"{days_to_expiry:.1f} days" if days_to_expiry is not None else "Unknown"
    
    status = trade_dict.get("status", "OPEN")
    
    return (
        f"🧾 Paper trade opened\n"
        f"Market: {market_short}\n"
        f"Position: {position}\n"
        f"Status: {status}\n"
        f"Confidence: {confidence_str}\n"
        f"Stake: {stake_eur:.2f} EUR ({stake_usd:.2f} USD)\n"
        f"Entry price: {entry_price_str}\n"
        f"Expiry: {expiry_str}"
    )

