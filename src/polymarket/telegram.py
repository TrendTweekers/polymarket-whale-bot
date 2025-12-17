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

# Track last values for /delta command (in-memory, resets on restart)
_last_delta_values = {
    "signals": 0,
    "open": 0,
    "resolved": 0,
    "timestamp": None
}

def score_to_confidence(score) -> int:
    """
    Convert whale score (0.0-1.0) to confidence percentage (0-100).
    Returns 0 if score is missing or invalid.
    """
    try:
        return int(round(float(score) * 100))
    except Exception:
        return 0

def confidence_tier(confidence: int) -> tuple[str, str]:
    """
    Map confidence (0-100) to emoji and tier label.
    Returns (emoji, label) tuple.
    """
    try:
        c = int(confidence)
    except Exception:
        c = 0
    
    if c >= 80:
        return "🟢", "Strong"
    if c >= 60:
        return "🟡", "Medium"
    if c >= 40:
        return "🟠", "Weak"
    return "🔴", "Skip"

def send_telegram(text: str) -> bool:
    """
    Send Telegram message. Returns True if successful, False otherwise.
    NEVER crashes the engine - swallows all exceptions.
    """
    if not TOKEN or not CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True}
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        # NEVER crash engine due to Telegram (timeouts, network errors, etc.)
        return False

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
    NEVER crashes - swallows all exceptions.
    """
    try:
        market = str(signal_row.get("market", "Unknown")).strip()
        category = str(signal_row.get("category", "unknown")).strip()
        category_inferred = signal_row.get("category_inferred", False)
        score = signal_row.get("whale_score", None)
        discount = signal_row.get("discount_pct", None)
        trades = signal_row.get("cluster_trades_count", 1)
        wallet = signal_row.get("wallet", "")
        wallet_short = wallet[:8] + "..." if wallet and len(wallet) > 8 else wallet
        
        # Format discount: discount is stored as fraction (0.0005 = 0.05%), multiply by 100 for display
        # Example: discount=0.0005 → display=0.05%
        if discount is not None:
            discount_display = discount * 100.0
            discount_str = f"{discount_display:.2f}%"
        else:
            discount_str = "N/A"
        
        # Format confidence from score (0-100 scale) with tier label
        confidence = score_to_confidence(score)
        emoji, tier = confidence_tier(confidence)
        confidence_str = f"{confidence}/100 {emoji} {tier}"
        
        # Format category with inferred label
        category_display = category if not category_inferred else f"{category} (inferred)"
        
        # Format days_to_expiry (for debugging/verification)
        dte = signal_row.get("days_to_expiry", None)
        if dte is not None:
            dte_str = f"{dte:.2f} days"
        else:
            dte_str = "Unknown"
        
        msg = (
            "🐋 Whale Signal\n"
            f"Wallet: {wallet_short}\n"
            f"Market: {market[:100]}\n"  # Truncate long market names
            f"Category: {category_display}\n"
            f"Confidence: {confidence_str}\n"
            f"Discount: {discount_str}\n"
            f"Expiry: {dte_str}\n"
            f"Trades: {trades}"
        )
        send_telegram(msg)
    except Exception:
        # NEVER crash engine due to Telegram formatting errors
        return

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

def format_status_message() -> str:
    """
    Format status message with counts from database.
    Returns formatted message string.
    """
    try:
        import sqlite3
        import os
        from pathlib import Path
        
        # Find database path (same logic as paper_counts.py)
        script_dir = Path(__file__).parent.parent.parent
        db_path = script_dir / "logs" / "paper_trading.sqlite"
        
        if not db_path.exists():
            return "❌ Database not found"
        
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        def one(sql, params=()):
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row else 0
        
        signals = one("SELECT COUNT(*) FROM signals")
        paper_total = one("SELECT COUNT(*) FROM paper_trades")
        paper_open = one("SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'")
        paper_resolved = one("SELECT COUNT(*) FROM paper_trades WHERE status='RESOLVED'")
        wins = one("SELECT COUNT(*) FROM paper_trades WHERE status='RESOLVED' AND won=1")
        losses = one("SELECT COUNT(*) FROM paper_trades WHERE status='RESOLVED' AND won=0")
        pnl_row = conn.execute("SELECT COALESCE(SUM(pnl_usd), 0.0) AS s FROM paper_trades WHERE status='RESOLVED'").fetchone()
        pnl = float(pnl_row["s"]) if pnl_row else 0.0
        
        conn.close()
        
        msg = (
            "✅ Engine Status\n"
            f"Signals: {signals}\n"
            f"Paper trades: {paper_total} (OPEN {paper_open}, RESOLVED {paper_resolved})"
        )
        
        if paper_resolved > 0:
            winrate = (wins / paper_resolved) * 100.0
            msg += f"\nResolved: W {wins} / L {losses} = {winrate:.2f}% win rate"
            msg += f"\nTotal PnL: ${pnl:.2f} USD"
        else:
            msg += "\nResolved: 0 (waiting for markets to close)"
        
        return msg
    except Exception as e:
        return f"❌ Error getting status: {str(e)}"

def send_heartbeat():
    """Send heartbeat status message."""
    msg = format_status_message()
    send_telegram(msg)

def _get_engine_stats():
    """Helper to get engine stats (signals, fingerprint, rolling metrics)."""
    total_signals = 0
    fingerprint = "unknown"
    signals_last_hour = 0
    trades_last_hour = 0
    uptime_seconds = 0
    
    try:
        import sys
        import time as time_module
        # Try multiple possible module names (Python import resolution can vary)
        engine_module = None
        for module_name in ['src.polymarket.engine', 'polymarket.engine', 'engine']:
            if module_name in sys.modules:
                engine_module = sys.modules[module_name]
                break
        
        # Also try direct import as fallback
        if engine_module is None:
            try:
                import src.polymarket.engine as engine_module
            except ImportError:
                try:
                    import polymarket.engine as engine_module
                except ImportError:
                    pass
        
        if engine_module:
            if hasattr(engine_module, 'stats') and engine_module.stats:
                total_signals = engine_module.stats.total_signals
                if hasattr(engine_module.stats, 'started_at'):
                    uptime_seconds = int(time_module.time() - engine_module.stats.started_at)
            if hasattr(engine_module, 'ENGINE_FINGERPRINT'):
                fingerprint = engine_module.ENGINE_FINGERPRINT
            if hasattr(engine_module, '_rolling_metrics'):
                hour_ago = time_module.time() - 3600
                rolling = engine_module._rolling_metrics
                signals_last_hour = sum(val for ts, val in rolling.get("signals", []) if ts > hour_ago)
                trades_last_hour = sum(val for ts, val in rolling.get("trades_considered", []) if ts > hour_ago)
    except Exception as e:
        # Log error for debugging but don't crash
        import logging
        logging.getLogger().debug(f"Error getting engine stats: {e}")
        pass
    
    return total_signals, fingerprint, signals_last_hour, trades_last_hour, uptime_seconds

def _get_paper_trades():
    """Helper to get paper trade counts from database."""
    paper_open = 0
    paper_resolved = 0
    
    try:
        import sqlite3
        from pathlib import Path
        script_dir = Path(__file__).parent.parent.parent
        db_path = script_dir / "logs" / "paper_trading.sqlite"
        
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            
            def one(sql, params=()):
                cur = conn.execute(sql, params)
                row = cur.fetchone()
                return row[0] if row else 0
            
            paper_open = one("SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'")
            paper_resolved = one("SELECT COUNT(*) FROM paper_trades WHERE status='RESOLVED'")
            
            conn.close()
    except Exception:
        pass
    
    return paper_open, paper_resolved

def build_delta_message():
    """
    Build /delta command message showing changes since last check.
    Returns formatted message string.
    """
    try:
        import time as time_module
        total_signals, fingerprint, signals_last_hour, trades_last_hour, _ = _get_engine_stats()
        paper_open, paper_resolved = _get_paper_trades()
        
        # Calculate deltas
        global _last_delta_values
        signals_delta = total_signals - _last_delta_values["signals"]
        open_delta = paper_open - _last_delta_values["open"]
        resolved_delta = paper_resolved - _last_delta_values["resolved"]
        
        # Format delta strings (with + sign for positive)
        signals_delta_str = f"+{signals_delta}" if signals_delta >= 0 else str(signals_delta)
        open_delta_str = f"+{open_delta}" if open_delta >= 0 else str(open_delta)
        resolved_delta_str = f"+{resolved_delta}" if resolved_delta >= 0 else str(resolved_delta)
        
        # Get time since last check
        time_since = ""
        if _last_delta_values["timestamp"]:
            elapsed = int(time_module.time() - _last_delta_values["timestamp"])
            if elapsed < 60:
                time_since = f" ({elapsed}s ago)"
            elif elapsed < 3600:
                time_since = f" ({elapsed // 60}m ago)"
            else:
                time_since = f" ({elapsed // 3600}h {elapsed % 3600 // 60}m ago)"
        
        # Update last values
        _last_delta_values["signals"] = total_signals
        _last_delta_values["open"] = paper_open
        _last_delta_values["resolved"] = paper_resolved
        _last_delta_values["timestamp"] = time_module.time()
        
        # Build delta message
        msg = (
            f"📈 Delta ({fingerprint}){time_since}\n\n"
            f"Signals: {signals_delta_str} (now: {total_signals})\n"
            f"OPEN: {open_delta_str} (now: {paper_open})\n"
            f"RESOLVED: {resolved_delta_str} (now: {paper_resolved})\n\n"
            f"Last 1h: {signals_last_hour} signals, {trades_last_hour} trades"
        )
        
        return msg
    except Exception as e:
        return f"❌ Error getting delta: {str(e)}"

def build_stats_message():
    """
    Build /stats command message with engine statistics.
    Returns formatted message string.
    """
    try:
        total_signals, fingerprint, signals_last_hour, trades_last_hour, _ = _get_engine_stats()
        paper_open, paper_resolved = _get_paper_trades()
        
        # Build stats message
        msg = (
            f"📊 Engine Stats ({fingerprint})\n\n"
            f"Signals total: {total_signals}\n"
            f"Paper trades:\n"
            f"• OPEN: {paper_open}\n"
            f"• RESOLVED: {paper_resolved}\n\n"
            f"Last 1h:\n"
            f"• Signals: {signals_last_hour}\n"
            f"• Trades considered: {trades_last_hour}\n\n"
            f"Status: 🟢 running"
        )
        
        return msg
    except Exception as e:
        return f"❌ Error getting stats: {str(e)}"

def send_message_to_chat(chat_id: str, text: str) -> bool:
    """
    Send Telegram message to a specific chat_id.
    Used for replying to /status commands.
    """
    if not TOKEN:
        return False
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

async def poll_telegram_commands(interval_seconds: int = 5):
    """
    Poll Telegram for bot commands (like /status).
    Runs in background task.
    """
    if not TOKEN:
        return
    
    import asyncio
    import aiohttp
    
    last_update_id = 0
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
            params = {"offset": last_update_id + 1, "timeout": interval_seconds}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=interval_seconds + 5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        updates = data.get("result", [])
                        
                        for update in updates:
                            last_update_id = max(last_update_id, update.get("update_id", 0))
                            
                            message = update.get("message", {})
                            text = message.get("text", "").strip()
                            chat_id = str(message.get("chat", {}).get("id", ""))
                            
                            if text == "/status":
                                status_msg = format_status_message()
                                send_message_to_chat(chat_id, status_msg)
                            elif text == "/stats":
                                stats_msg = build_stats_message()
                                send_message_to_chat(chat_id, stats_msg)
                            elif text == "/open":
                                paper_open, _ = _get_paper_trades()
                                send_message_to_chat(chat_id, f"📂 OPEN: {paper_open}")
                            elif text == "/signals":
                                total_signals, fingerprint, _, _, _ = _get_engine_stats()
                                send_message_to_chat(chat_id, f"📡 Signals: {total_signals} ({fingerprint})")
                            elif text == "/resolved":
                                _, paper_resolved = _get_paper_trades()
                                send_message_to_chat(chat_id, f"✅ RESOLVED: {paper_resolved}")
                            elif text == "/uptime":
                                _, fingerprint, _, _, uptime_seconds = _get_engine_stats()
                                uptime_hours = uptime_seconds // 3600
                                uptime_mins = (uptime_seconds % 3600) // 60
                                send_message_to_chat(chat_id, f"⏱️ Uptime: {uptime_hours}h {uptime_mins}m ({fingerprint})")
                            elif text == "/delta":
                                delta_msg = build_delta_message()
                                send_message_to_chat(chat_id, delta_msg)
                            elif text == "/help":
                                help_msg = (
                                    "🤖 Available commands:\n\n"
                                    "/stats - Full engine statistics\n"
                                    "/delta - Changes since last check\n"
                                    "/status - Engine status with PnL\n"
                                    "/signals - Total signals count\n"
                                    "/open - OPEN paper trades count\n"
                                    "/resolved - RESOLVED paper trades count\n"
                                    "/uptime - Engine uptime\n"
                                    "/help - Show this help"
                                )
                                send_message_to_chat(chat_id, help_msg)
                            elif text.startswith("/"):
                                # Unknown command
                                send_message_to_chat(chat_id, "Unknown command. Type /help for available commands.")
        
        except asyncio.CancelledError:
            break
        except Exception:
            # Don't crash on Telegram polling errors
            pass
        
        await asyncio.sleep(interval_seconds)
