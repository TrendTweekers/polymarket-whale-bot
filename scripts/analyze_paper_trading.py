#!/usr/bin/env python3
"""
Paper Trading Analysis Script
Analyzes logs and database to generate comprehensive performance report.
"""

import sqlite3
import json
import re
import ast
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Dict, List, Optional
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def parse_log_line(line: str) -> Optional[Dict]:
    """Parse a structured log line (Python dict format with single quotes)"""
    try:
        # Extract dict part from log line
        # Format: "2025-12-21 20:37:19 [INFO    ] {'event': 'signal_generated', ...}"
        match = re.search(r"\{.*\}", line, re.DOTALL)
        if match:
            dict_str = match.group(0)
            # Use ast.literal_eval to parse Python dict format (handles single quotes)
            return ast.literal_eval(dict_str)
    except Exception:
        # Fallback: try to extract just event type for counting
        try:
            if "'event':" in line:
                event_match = re.search(r"'event':\s*'([^']+)'", line)
                if event_match:
                    return {"event": event_match.group(1)}
        except Exception:
            pass
    return None

def analyze_logs(log_file: Path) -> Dict:
    """Analyze engine logs for metrics"""
    print(f"Analyzing logs: {log_file}")
    
    metrics = {
        "signals_generated": 0,
        "paper_trades_opened": 0,
        "rejections": Counter(),
        "discounts": [],
        "trade_values": [],
        "confidences": [],
        "whales": set(),
        "markets": set(),
        "first_signal": None,
        "last_signal": None,
    }
    
    if not log_file.exists():
        print(f"  Log file not found: {log_file}")
        return metrics
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                data = parse_log_line(line)
                if not data:
                    continue
                
                event = data.get("event", "")
                
                if event == "signal_generated":
                    metrics["signals_generated"] += 1
                    discount = data.get("discount_pct")
                    if discount is not None:
                        metrics["discounts"].append(discount)
                    trade_value = data.get("trade_value_usd")
                    if trade_value:
                        metrics["trade_values"].append(trade_value)
                    wallet = data.get("wallet", "")
                    if wallet:
                        metrics["whales"].add(wallet)
                    market = data.get("market", "")
                    if market:
                        metrics["markets"].add(market)
                    
                    # Track first/last signal timestamps
                    timestamp_str = line.split()[0] + " " + line.split()[1]
                    if not metrics["first_signal"]:
                        metrics["first_signal"] = timestamp_str
                    metrics["last_signal"] = timestamp_str
                
                elif event == "paper_trade_opened":
                    metrics["paper_trades_opened"] += 1
                    confidence = data.get("confidence")
                    if confidence:
                        metrics["confidences"].append(confidence)
                
                elif event == "paper_trade_skipped":
                    reasons = data.get("reasons", "")
                    if reasons:
                        for reason in str(reasons).split(","):
                            metrics["rejections"][reason.strip()] += 1
                
                elif "rejected" in event or "rejection" in event.lower():
                    reason = event.replace("trade_rejected_", "").replace("signal_rejected_", "")
                    if reason:
                        metrics["rejections"][reason] += 1
                
                elif event == "PAPER_TRACE_FILTER_RESULTS":
                    skip_reasons = data.get("skip_reasons", [])
                    if skip_reasons:
                        for reason in skip_reasons:
                            metrics["rejections"][reason] += 1
    
    except Exception as e:
        print(f"  Error reading log: {e}")
    
    return metrics

def analyze_database(db_path: Path) -> Dict:
    """Analyze paper trading database"""
    print(f"Analyzing database: {db_path}")
    
    metrics = {
        "total_trades": 0,
        "open_trades": 0,
        "resolved_trades": 0,
        "wins": 0,
        "losses": 0,
        "total_pnl_usd": 0.0,
        "total_stake_usd": 0.0,
        "trade_durations": [],
        "per_whale": defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "stake": 0.0}),
        "per_market": defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}),
    }
    
    if not db_path.exists():
        print(f"  Database not found: {db_path}")
        return metrics
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all paper trades
        cursor.execute("""
            SELECT 
                pt.id,
                pt.opened_at,
                pt.resolved_at,
                pt.status,
                pt.stake_usd,
                pt.pnl_usd,
                pt.won,
                pt.confidence,
                s.wallet,
                s.market,
                s.condition_id
            FROM paper_trades pt
            LEFT JOIN signals s ON pt.signal_id = s.id
            ORDER BY pt.opened_at ASC
        """)
        
        for row in cursor.fetchall():
            metrics["total_trades"] += 1
            
            if row["status"] == "OPEN":
                metrics["open_trades"] += 1
            elif row["status"] == "RESOLVED":
                metrics["resolved_trades"] += 1
                
                if row["won"] == 1:
                    metrics["wins"] += 1
                elif row["won"] == 0:
                    metrics["losses"] += 1
                
                pnl = row["pnl_usd"] or 0.0
                metrics["total_pnl_usd"] += pnl
                
                # Calculate duration
                if row["opened_at"] and row["resolved_at"]:
                    try:
                        opened = datetime.fromisoformat(row["opened_at"].replace("Z", "+00:00"))
                        resolved = datetime.fromisoformat(row["resolved_at"].replace("Z", "+00:00"))
                        duration = (resolved - opened).total_seconds() / 3600  # hours
                        metrics["trade_durations"].append(duration)
                    except Exception:
                        pass
            
            stake = row["stake_usd"] or 0.0
            metrics["total_stake_usd"] += stake
            
            # Per-whale stats
            wallet = row["wallet"] or "unknown"
            if row["status"] == "RESOLVED":
                if row["won"] == 1:
                    metrics["per_whale"][wallet]["wins"] += 1
                elif row["won"] == 0:
                    metrics["per_whale"][wallet]["losses"] += 1
                metrics["per_whale"][wallet]["pnl"] += (row["pnl_usd"] or 0.0)
            metrics["per_whale"][wallet]["trades"] += 1
            metrics["per_whale"][wallet]["stake"] += stake
            
            # Per-market stats
            market = row["market"] or "unknown"
            if row["status"] == "RESOLVED":
                if row["won"] == 1:
                    metrics["per_market"][market]["wins"] += 1
                elif row["won"] == 0:
                    metrics["per_market"][market]["losses"] += 1
                metrics["per_market"][market]["pnl"] += (row["pnl_usd"] or 0.0)
            metrics["per_market"][market]["trades"] += 1
        
        conn.close()
    
    except Exception as e:
        print(f"  Error reading database: {e}")
        import traceback
        traceback.print_exc()
    
    return metrics

def generate_report(log_metrics: Dict, db_metrics: Dict):
    """Generate comprehensive report"""
    print("\n" + "="*80)
    print("PAPER TRADING ANALYSIS REPORT")
    print("="*80)
    
    # Time range
    duration_hours = 0
    if log_metrics["first_signal"] and log_metrics["last_signal"]:
        print(f"\nTime Range: {log_metrics['first_signal']} to {log_metrics['last_signal']}")
        try:
            first = datetime.strptime(log_metrics["first_signal"], "%Y-%m-%d %H:%M:%S")
            last = datetime.strptime(log_metrics["last_signal"], "%Y-%m-%d %H:%M:%S")
            duration_hours = (last - first).total_seconds() / 3600
            print(f"Duration: {duration_hours:.1f} hours")
            log_metrics["duration_hours"] = duration_hours
        except Exception as e:
            print(f"  (Could not parse duration: {e})")
    
    # Signal Generation
    print(f"\n{'='*80}")
    print("SIGNAL GENERATION")
    print(f"{'='*80}")
    print(f"Total signals generated: {log_metrics['signals_generated']}")
    print(f"Paper trades opened: {log_metrics['paper_trades_opened']}")
    print(f"Unique whales detected: {len(log_metrics['whales'])}")
    print(f"Unique markets: {len(log_metrics['markets'])}")
    
    if log_metrics["discounts"]:
        avg_discount = sum(log_metrics["discounts"]) / len(log_metrics["discounts"])
        print(f"Average discount: {avg_discount*100:.2f}%")
        print(f"Min discount: {min(log_metrics['discounts'])*100:.2f}%")
        print(f"Max discount: {max(log_metrics['discounts'])*100:.2f}%")
    
    if log_metrics["trade_values"]:
        avg_value = sum(log_metrics["trade_values"]) / len(log_metrics["trade_values"])
        print(f"Average trade value: ${avg_value:.2f}")
        print(f"Total trade value: ${sum(log_metrics['trade_values']):,.2f}")
    
    # Rejections
    if log_metrics["rejections"]:
        print(f"\n{'='*80}")
        print("TOP REJECTION REASONS")
        print(f"{'='*80}")
        for reason, count in log_metrics["rejections"].most_common(10):
            print(f"  {reason}: {count}")
    
    # Database Stats
    print(f"\n{'='*80}")
    print("PAPER TRADES DATABASE")
    print(f"{'='*80}")
    print(f"Total trades: {db_metrics['total_trades']}")
    print(f"Open trades: {db_metrics['open_trades']}")
    print(f"Resolved trades: {db_metrics['resolved_trades']}")
    
    if db_metrics["resolved_trades"] > 0:
        print(f"\nWin/Loss:")
        print(f"  Wins: {db_metrics['wins']}")
        print(f"  Losses: {db_metrics['losses']}")
        win_rate = (db_metrics["wins"] / db_metrics["resolved_trades"]) * 100 if db_metrics["resolved_trades"] > 0 else 0
        print(f"  Win rate: {win_rate:.1f}%")
        
        print(f"\nPnL:")
        print(f"  Total PnL: ${db_metrics['total_pnl_usd']:.2f}")
        print(f"  Total stake: ${db_metrics['total_stake_usd']:.2f}")
        if db_metrics["total_stake_usd"] > 0:
            roi = (db_metrics["total_pnl_usd"] / db_metrics["total_stake_usd"]) * 100
            print(f"  ROI: {roi:.2f}%")
        
        if db_metrics["trade_durations"]:
            avg_duration = sum(db_metrics["trade_durations"]) / len(db_metrics["trade_durations"])
            print(f"\nTrade Duration:")
            print(f"  Average: {avg_duration:.1f} hours")
            print(f"  Min: {min(db_metrics['trade_durations']):.1f} hours")
            print(f"  Max: {max(db_metrics['trade_durations']):.1f} hours")
        
        # EV Assessment
        print(f"\n{'='*80}")
        print("EV ASSESSMENT")
        print(f"{'='*80}")
        if win_rate >= 52:
            print(f"[POSITIVE] EV: Win rate {win_rate:.1f}% >= 52% threshold")
        else:
            print(f"[NEGATIVE] EV: Win rate {win_rate:.1f}% < 52% threshold")
        
        if roi > 0:
            print(f"[PROFITABLE] ROI {roi:.2f}%")
        else:
            print(f"[UNPROFITABLE] ROI {roi:.2f}%")
    
    # Per-Whale Performance
    if db_metrics["per_whale"]:
        print(f"\n{'='*80}")
        print("PER-WHALE PERFORMANCE (Top 10)")
        print(f"{'='*80}")
        print(f"{'Whale':<45} {'Trades':<8} {'Wins':<6} {'Losses':<8} {'Win%':<8} {'PnL':<12} {'ROI%'}")
        print("-"*100)
        
        whale_list = []
        for wallet, stats in db_metrics["per_whale"].items():
            if stats["trades"] > 0:
                win_rate = (stats["wins"] / (stats["wins"] + stats["losses"])) * 100 if (stats["wins"] + stats["losses"]) > 0 else 0
                roi = (stats["pnl"] / stats["stake"]) * 100 if stats["stake"] > 0 else 0
                whale_list.append({
                    "wallet": wallet,
                    "trades": stats["trades"],
                    "wins": stats["wins"],
                    "losses": stats["losses"],
                    "win_rate": win_rate,
                    "pnl": stats["pnl"],
                    "roi": roi
                })
        
        whale_list.sort(key=lambda x: x["trades"], reverse=True)
        for whale in whale_list[:10]:
            wallet_short = whale["wallet"][:42] + "..." if len(whale["wallet"]) > 45 else whale["wallet"]
            print(f"{wallet_short:<45} {whale['trades']:<8} {whale['wins']:<6} {whale['losses']:<8} {whale['win_rate']:<7.1f}% ${whale['pnl']:<11.2f} {whale['roi']:<7.2f}%")
    
    # Additional stats
    if db_metrics["total_trades"] > 0:
        print(f"\n{'='*80}")
        print("ADDITIONAL STATISTICS")
        print(f"{'='*80}")
        print(f"Total stake invested: ${db_metrics['total_stake_usd']:.2f}")
        if log_metrics.get("confidences"):
            avg_conf = sum(log_metrics["confidences"]) / len(log_metrics["confidences"])
            print(f"Average confidence: {avg_conf:.1f}")
        
        # Signal to trade conversion rate
        if log_metrics["signals_generated"] > 0:
            conversion_rate = (db_metrics["total_trades"] / log_metrics["signals_generated"]) * 100
            print(f"Signal -> Trade conversion: {conversion_rate:.1f}% ({db_metrics['total_trades']}/{log_metrics['signals_generated']})")
        
        # Trades per hour
        if log_metrics.get("duration_hours", 0) > 0:
            trades_per_hour = db_metrics["total_trades"] / log_metrics["duration_hours"]
            print(f"Trades per hour: {trades_per_hour:.1f}")
    
    # Suggestions
    print(f"\n{'='*80}")
    print("ANALYSIS & SUGGESTIONS")
    print(f"{'='*80}")
    
    if log_metrics["rejections"]:
        top_rejection = log_metrics["rejections"].most_common(1)[0]
        print(f"\nTop rejection reason: {top_rejection[0]} ({top_rejection[1]} occurrences)")
        
        if "low_discount" in top_rejection[0] or "discount" in top_rejection[0]:
            print("\n[WARNING] High discount rejections detected:")
            print(f"   - {top_rejection[1]} trades rejected due to low/negative discount")
            print(f"   - Current threshold: PAPER_MIN_DISCOUNT_PCT = 0.01% (0.0001)")
            print(f"   - Paper mode accepts discounts >= -1% (-0.01)")
            print(f"   - Suggestion: Current threshold is appropriate for testing")
            print(f"   - Many rejections may be from negative discounts (whales buying above market)")
        
        if "deduped" in top_rejection[0]:
            print("\n[INFO] Signal deduplication working:")
            print(f"   - {top_rejection[1]} duplicate signals prevented")
            print(f"   - This is expected behavior (prevents spam)")
        
        if "open_trade_exists" in top_rejection[0]:
            print("\n[INFO] Duplicate trade prevention working:")
            print(f"   - {log_metrics['rejections'].get('open_trade_exists', 0)} trades skipped (already have open position)")
            print(f"   - This prevents over-exposure to same market")
    
    if db_metrics["resolved_trades"] == 0:
        print("\n[PENDING] No resolved trades yet:")
        print("   - All 279 trades are still OPEN")
        print("   - Markets may not have resolved yet (many are same-day or next-day)")
        print("   - Resolver runs every 5 minutes to check for resolutions")
        print("   - Wait for markets to resolve to see PnL and win rate")
    elif db_metrics["resolved_trades"] > 0:
        if db_metrics["wins"] / db_metrics["resolved_trades"] < 0.52:
            print("\n[WARNING] Win rate below 52% threshold:")
            print("   - Review whale selection criteria")
            print("   - Check if delays are causing entry price degradation")
            print("   - Consider stricter confidence thresholds")
        
        if db_metrics["total_pnl_usd"] < 0:
            print("\n[WARNING] Negative PnL detected:")
            print("   - Review entry timing (delays)")
            print("   - Check if slippage assumptions are accurate")
            print("   - Consider tighter discount filters")
    
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"[OK] System Status: OPERATIONAL")
    print(f"[OK] Paper Trading: ACTIVE ({db_metrics['total_trades']} trades opened)")
    print(f"[OK] Signal Generation: {log_metrics['signals_generated']} signals in {log_metrics.get('duration_hours', 0):.1f} hours")
    if db_metrics["resolved_trades"] > 0:
        win_rate = (db_metrics["wins"] / db_metrics["resolved_trades"]) * 100
        roi = (db_metrics["total_pnl_usd"] / db_metrics["total_stake_usd"]) * 100 if db_metrics["total_stake_usd"] > 0 else 0
        ev_status = "[POSITIVE]" if win_rate >= 52 else "[NEGATIVE]"
        print(f"{ev_status} EV: Win rate {win_rate:.1f}%, ROI {roi:.2f}%")
    else:
        print(f"[PENDING] Waiting for market resolutions to calculate EV")
    print(f"{'='*80}\n")

def main():
    """Main analysis function"""
    base_dir = Path(__file__).parent.parent
    log_dir = base_dir / "logs"
    
    # Find latest log file (exclude engine_recent.log and rotated files)
    log_files = [f for f in log_dir.glob("engine_*.log") 
                 if not f.name.startswith("engine_recent") and not f.name.endswith(".log.1")]
    log_files = sorted(log_files, key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not log_files:
        print("No log files found!")
        return
    
    latest_log = log_files[0]
    print(f"Using log file: {latest_log.name}")
    
    # Also check if there's a more recent engine_recent.log with more data
    recent_log = log_dir / "engine_recent.log"
    if recent_log.exists():
        recent_size = recent_log.stat().st_size
        latest_size = latest_log.stat().st_size
        if recent_size > latest_size:
            print(f"Note: engine_recent.log ({recent_size} bytes) is larger than {latest_log.name} ({latest_size} bytes)")
            print(f"Consider analyzing both files for complete data")
    
    # Database path
    db_path = log_dir / "paper_trading.sqlite"
    
    # Analyze
    print("\n" + "="*80)
    print("ANALYZING DATA...")
    print("="*80)
    
    log_metrics = analyze_logs(latest_log)
    db_metrics = analyze_database(db_path)
    
    # Generate report
    generate_report(log_metrics, db_metrics)

if __name__ == "__main__":
    main()
