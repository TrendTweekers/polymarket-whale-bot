# src/polymarket/telegram.py
import os
import requests
from pathlib import Path

# Load .env file if dotenv is available
try:
    from dotenv import load_dotenv
    # Load from project root (where .env file is located)
    env_path = Path(__file__).parent.parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    pass  # dotenv not installed, rely on system env vars
except Exception:
    # Fallback: try loading from current directory
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except:
        pass

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

def send_telegram(text: str) -> None:
    if not TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10,
        )
    except Exception:
        pass  # Silently fail - don't break engine if Telegram is down

def notify_engine_start():
    send_telegram("🟢 Polymarket engine started")

def notify_engine_stop():
    send_telegram("🔴 Polymarket engine stopped")

def notify_engine_crash(err: str):
    send_telegram(f"⚠️ Polymarket engine crashed:\n{err}")

def notify_signal(signal_row: dict):
    """
    Send Telegram notification for a whale signal.
    Expects signal dict with: market, category, whale_score, discount_pct, cluster_trades_count, wallet
    """
    market = str(signal_row.get("market", "Unknown")).strip()
    category = str(signal_row.get("category", "unknown")).strip()
    score = signal_row.get("whale_score", None)
    discount = signal_row.get("discount_pct", None)
    trades = signal_row.get("cluster_trades_count", 1)
    wallet = signal_row.get("wallet", "")
    wallet_short = wallet[:8] + "..." if wallet and len(wallet) > 8 else wallet
    
    # Format discount (multiply by 100 if stored as ratio, e.g., 0.03 = 3%)
    # Discount is stored as ratio (0.03 = 3%), so multiply by 100 for display
    if discount is not None:
        discount_display = discount * 100.0
        discount_str = f"{discount_display:.2f}%"
    else:
        discount_str = "N/A"
    
    # Format score
    score_str = f"{score:.2f}" if score is not None else "N/A"
    
    msg = (
        "🐋 Whale Signal\n"
        f"Wallet: {wallet_short}\n"
        f"Market: {market[:100]}\n"  # Truncate long market names
        f"Category: {category}\n"
        f"Score: {score_str}\n"
        f"Discount: {discount_str}\n"
        f"Trades: {trades}"
    )
    send_telegram(msg)

def notify_phase1b_bypass(wallet: str, condition_id: str = None, note: str = None):
    """Notify when Phase 1b bypass is used (missing discount)."""
    wallet_short = wallet[:8] + "..." if wallet and len(wallet) > 8 else wallet
    cond_short = condition_id[:20] + "..." if condition_id and len(condition_id) > 20 else (condition_id or "N/A")
    note_str = f"\nNote: {note}" if note else ""
    
    msg = (
        "⚠️ Phase 1b Bypass Active\n"
        f"Wallet: {wallet_short}\n"
        f"Condition: {cond_short}{note_str}"
    )
    send_telegram(msg)

def notify_csv_write_attempt(signal: dict):
    """Notify when CSV write is attempted."""
    wallet = signal.get("wallet", "")
    wallet_short = wallet[:8] + "..." if wallet and len(wallet) > 8 else wallet
    market = str(signal.get("market", "Unknown"))[:50]
    
    msg = (
        "📝 CSV Write Attempt\n"
        f"Wallet: {wallet_short}\n"
        f"Market: {market}"
    )
    send_telegram(msg)

def notify_csv_write_done(log_file: str):
    """Notify when CSV write completes."""
    msg = (
        "✅ CSV Write Complete\n"
        f"File: {log_file}"
    )
    send_telegram(msg)
