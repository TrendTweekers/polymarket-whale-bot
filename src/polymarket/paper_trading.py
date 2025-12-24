# src/polymarket/paper_trading.py
"""
Paper trading module - handles paper trade creation and stake computation.
"""
import os
import structlog
import re
from typing import Dict, Optional, Tuple
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


def open_paper_trade(signal_row: Dict, confidence: int = None) -> Tuple[Optional[Dict], str]:
    """
    Create a paper trade dictionary from a signal.
    
    Args:
        signal_row: Signal dictionary with all signal fields
        confidence: Confidence score (0-100). If None, extracted from signal_row.
    
    Returns:
        Tuple of (paper_trade_dict, reason_string)
        - If successful: (dict, "success")
        - If failed: (None, "reason_for_failure")
    """
    try:
        # Extract confidence
        if confidence is None:
            confidence = signal_row.get("confidence", 0)
        
        # Validate required fields
        if not signal_row.get("wallet"):
            return None, "missing_wallet"
        if not signal_row.get("condition_id") and not signal_row.get("event_id"):
            return None, "missing_condition_id"
        if not signal_row.get("market"):
            return None, "missing_market"
        
        # Calculate stake based on confidence
        stake_eur = round(stake_eur_from_confidence(confidence), 2)
        if stake_eur <= 0:
            return None, f"stake_zero_or_negative_{stake_eur}"
        
        stake_usd = compute_stake_usd(stake_eur, FX_EUR_USD)
        
        entry_price = signal_row.get("whale_entry_price") or signal_row.get("entry_price") or signal_row.get("current_price")
        if entry_price is None or entry_price <= 0:
            return None, f"invalid_entry_price_{entry_price}"
        
        trade_dict = {
            "wallet": signal_row.get("wallet", ""),
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
            "condition_id": signal_row.get("condition_id") or signal_row.get("event_id", ""),
            "market_id": signal_row.get("market_id", ""),
            "token_id": signal_row.get("token_id", ""),
            "market": signal_row.get("market", ""),
            "category": signal_row.get("category", ""),
            "confidence": confidence,
            "market_question": signal_row.get("market_question") or signal_row.get("question") or signal_row.get("market", "")  # Store full question if available
        }
        
        return trade_dict, "success"
    except Exception as e:
        return None, f"exception_{type(e).__name__}_{str(e)[:100]}"


def format_paper_trade_telegram(trade_dict: Optional[Dict] = None, signal: Optional[Dict] = None, trade_id: Optional[int] = None, confidence: Optional[int] = None) -> str:
    """
    Format Telegram message for paper trade opened.
    
    Args:
        trade_dict: Paper trade dictionary (preferred, contains all fields)
        signal: Signal dictionary (alternative, merged with trade_id/confidence)
        trade_id: Trade ID (optional, merged with signal)
        confidence: Confidence score (optional, merged with signal)
        
    Returns:
        Formatted Telegram message string
    """
    # Merge data sources: prefer trade_dict, fallback to signal + trade_id + confidence
    if trade_dict:
        data = trade_dict.copy()
    elif signal:
        data = signal.copy()
        if trade_id is not None:
            data["trade_id"] = trade_id
        if confidence is not None:
            data["confidence"] = confidence
    else:
        data = {}
    
    # Extract fields safely with defaults
    market = data.get("market") or data.get("question") or data.get("title") or "Unknown"
    market_short = (market[:50] + "...") if len(market) > 50 else market
    
    confidence_val = data.get("confidence", 0)
    confidence_str = f"{confidence_val}/100"
    
    # Use safe position name helper (never blank)
    position = _safe_position_name(data)
    
    # Add range hint with actual values
    position = _range_hint(market, position)
    
    stake_eur = data.get("stake_eur", 0.0)
    stake_usd = data.get("stake_usd", 0.0)
    entry_price = data.get("entry_price") or data.get("whale_entry_price") or data.get("current_price")
    entry_price_str = f"{entry_price:.4f}" if entry_price else "N/A"
    
    days_to_expiry = data.get("days_to_expiry")
    expiry_str = f"{days_to_expiry:.1f} days" if days_to_expiry is not None else "Unknown"
    
    status = data.get("status", "OPEN")
    
    # Add trade_id if available
    trade_id_str = ""
    if data.get("trade_id"):
        trade_id_str = f"Trade ID: {data['trade_id']}\n"
    
    # Add discount if available
    discount_str = ""
    discount_pct = data.get("discount_pct")
    if discount_pct is not None:
        discount_str = f"Discount: {discount_pct*100:.2f}%\n"
    
    # Add trade value if available
    value_str = ""
    trade_value_usd = data.get("trade_value_usd")
    if trade_value_usd is not None:
        value_str = f"Trade Value: ${trade_value_usd:.2f}\n"
    
    return (
        f"🧾 Paper trade opened\n"
        f"{trade_id_str}"
        f"Market: {market_short}\n"
        f"Position: {position}\n"
        f"Status: {status}\n"
        f"Confidence: {confidence_str}\n"
        f"{discount_str}"
        f"{value_str}"
        f"Stake: {stake_eur:.2f} EUR ({stake_usd:.2f} USD)\n"
        f"Entry price: {entry_price_str}\n"
        f"Expiry: {expiry_str}"
    )


if __name__ == "__main__":
    # Sanity check: test the formatter with minimal data
    test_dict = {
        "market": "Test Market",
        "confidence": 75,
        "stake_eur": 3.5,
        "stake_usd": 3.85,
        "entry_price": 0.65,
        "days_to_expiry": 2.5,
        "status": "OPEN",
        "outcome_name": "YES"
    }
    result = format_paper_trade_telegram(trade_dict=test_dict)
    assert isinstance(result, str), "Formatter must return string"
    assert "Test Market" in result, "Market name must be in output"
    assert "75/100" in result, "Confidence must be in output"
    print("Test 1 passed: trade_dict format")
    
    # Test with signal + trade_id + confidence (backwards compatibility)
    test_signal = {
        "market": "Test Market 2",
        "discount_pct": 0.05,
        "trade_value_usd": 200.0
    }
    result2 = format_paper_trade_telegram(signal=test_signal, trade_id=999, confidence=80)
    assert isinstance(result2, str), "Formatter must return string"
    assert "Test Market 2" in result2, "Market name must be in output"
    assert "80/100" in result2, "Confidence must be in output"
    print("Test 2 passed: signal + trade_id + confidence format")
    
    # Test with empty dict (should not crash)
    result3 = format_paper_trade_telegram(trade_dict={})
    assert isinstance(result3, str), "Formatter must return string even with empty dict"
    print("Test 3 passed: empty dict format")
    
    print("All formatter tests passed")

