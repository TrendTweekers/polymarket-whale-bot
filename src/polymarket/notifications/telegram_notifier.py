"""
Telegram Notifier - Sends alerts to your Telegram
"""

import os
import aiohttp
import structlog
from typing import Dict, List, Optional
from datetime import datetime

log = structlog.get_logger()


class TelegramNotifier:
    """
    Send notifications via Telegram Bot
    Uses credentials from .env file
    """
    
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        if not self.bot_token or not self.chat_id:
            log.warning("telegram_credentials_missing",
                       has_token=bool(self.bot_token),
                       has_chat_id=bool(self.chat_id))
            self.enabled = False
        else:
            self.enabled = True
            log.info("telegram_notifier_initialized",
                    chat_id=self.chat_id[:10] + "...")
        
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    async def send_message(self, message: str, parse_mode: str = "HTML"):
        """
        Send a message to Telegram
        """
        if not self.enabled:
            log.debug("telegram_disabled", message=message[:50])
            return False
        
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': parse_mode
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        log.debug("telegram_sent", message_length=len(message))
                        return True
                    else:
                        log.error("telegram_failed", status=response.status)
                        return False
        
        except Exception as e:
            log.error("telegram_error", error=str(e))
            return False
    
    async def notify_bot_started(self, config: Dict):
        """
        Send startup notification
        """
        message = f"""
🤖 <b>Whale Bot Started</b>

💰 Bankroll: ${config['trading']['bankroll']}
📅 Max Days: {config['trading']['max_days_to_resolution']}
🎯 Position Size: {config['trading']['max_position_size']:.1%}
🐋 Whales Tracked: {config.get('whale_count', 0)}

Status: <b>MONITORING</b>
Mode: <b>PAPER TRADING</b>
"""
        await self.send_message(message)
    
    async def notify_whale_detected(self, whale_data: Dict, market_data: Dict, bet_data: Dict):
        """
        Alert when whale activity detected
        """
        message = f"""
🐋 <b>WHALE DETECTED</b>

Whale: <code>{whale_data.get('whale_id', 'Unknown')[:12]}...</code>
Win Rate: {whale_data.get('win_rate', 0):.1%}

📊 Market: {market_data.get('question', 'Unknown')[:80]}
💵 Bet: {bet_data.get('direction', '?')} ${bet_data.get('amount', 0):,.0f}
⏰ Resolves: {market_data.get('days_until_resolution', '?')} days

Status: <b>EVALUATING...</b>
"""
        await self.send_message(message)
    
    async def notify_trade_evaluation(self, evaluation: Dict, whale_data: Dict, market_data: Dict):
        """
        Send evaluation results
        """
        decision = "✅ APPROVED" if evaluation['should_trade'] else "❌ REJECTED"
        
        message = f"""
{decision} <b>Trade Evaluation</b>

🐋 Whale: <code>{whale_data.get('whale_id', 'Unknown')[:12]}...</code>
📊 Market: {market_data.get('question', 'Unknown')[:60]}

<b>Scores:</b>
- Bayesian: {evaluation['scores'].get('bayesian', 0):.2f}
- ML Probability: {evaluation['scores'].get('ml_probability', 0):.2f}
- Ensemble: {evaluation['scores'].get('ensemble', 0):.2f}
<b>Final: {evaluation.get('confidence', 0):.2f}</b>

<b>Filters:</b>
"""
        
        # Add filter results
        for filter_name, passed in evaluation.get('filters_passed', {}).items():
            emoji = "✅" if passed else "❌"
            message += f"• {emoji} {filter_name.title()}\n"
        
        if evaluation['should_trade']:
            message += f"""
<b>Position Size: ${evaluation.get('position_size', 0):.2f}</b>

⚠️ <b>PAPER TRADE - NOT EXECUTED</b>
"""
        else:
            reason = evaluation['reasons'][-1] if evaluation['reasons'] else "Unknown"
            message += f"\nReason: {reason[:100]}"
        
        await self.send_message(message)
    
    async def notify_trade_executed(self, trade_record: Dict):
        """
        Notify when trade executed (paper)
        """
        message = f"""
📝 <b>PAPER TRADE LOGGED</b>

Trade ID: <code>{trade_record['trade_id']}</code>
Market: {trade_record.get('market_question', 'Unknown')[:60]}

Direction: <b>{trade_record['direction']}</b>
Size: <b>${trade_record['position_size']:.2f}</b>
Confidence: {trade_record['confidence']:.2%}

Status: <b>TRACKING</b> (Paper mode)
"""
        await self.send_message(message)
    
    async def notify_trade_outcome(self, trade_id: str, outcome: bool, pnl: float, 
                                  duration_days: int):
        """
        Notify when position closes
        """
        result = "🎉 WIN" if outcome else "😞 LOSS"
        pnl_emoji = "📈" if pnl > 0 else "📉"
        
        message = f"""
{result} <b>Trade Completed</b>

Trade ID: <code>{trade_id}</code>
Duration: {duration_days} days

P&L: {pnl_emoji} <b>${pnl:+.2f}</b>

Status: Updated all learning systems
"""
        await self.send_message(message)
    
    async def notify_daily_summary(self, summary: Dict):
        """
        Send end-of-day summary
        """
        capital_metrics = summary.get('capital_metrics', {})
        
        message = f"""
📊 <b>Daily Summary</b>

<b>Capital Metrics:</b>
- Utilization: {capital_metrics.get('capital_utilization', 0):.1%}
- Free Capital: ${capital_metrics.get('free_capital', 0):.2f}
- Active Positions: {capital_metrics.get('active_positions', 0)}
- Avg Duration: {capital_metrics.get('avg_duration_days', 0):.1f} days

<b>Performance:</b>
- Completed Trades: {summary.get('completed_trades', 0)}
- Monthly Capacity: {capital_metrics.get('monthly_capacity', 0)} trades

<b>Top Whales:</b>
"""
        
        for whale_id, score in summary.get('top_whales', [])[:3]:
            message += f"• <code>{whale_id[:12]}...</code> - {score:.2f}\n"
        
        await self.send_message(message)
    
    async def notify_error(self, error_type: str, error_message: str):
        """
        Alert on critical errors
        """
        message = f"""
🚨 <b>ERROR ALERT</b>

Type: {error_type}
Message: {error_message[:200]}

Bot Status: Check logs
"""
        await self.send_message(message)
    
    async def notify_self_improvement(self, improvement_type: str, details: Dict):
        """
        Notify when bot improves itself
        """
        if improvement_type == "ml_retrained":
            message = f"""
🧠 <b>ML Model Retrained</b>

Samples: {details.get('samples', 0)}
Accuracy: {details.get('accuracy', 0):.1%}

Top Features:
"""
            for feature, importance in details.get('top_features', [])[:3]:
                message += f"• {feature}: {importance:.3f}\n"
        
        elif improvement_type == "ensemble_rebalanced":
            message = f"""
⚖️ <b>Ensemble Rebalanced</b>

Strategy Weights Updated:
"""
            for strategy, weight in details.get('weights', {}).items():
                message += f"• {strategy}: {weight:.1%}\n"
        
        elif improvement_type == "whale_score_updated":
            message = f"""
🐋 <b>Whale Score Updated</b>

Whale: <code>{details.get('whale_id', 'Unknown')[:12]}...</code>
Old Score: {details.get('old_score', 0):.3f}
New Score: {details.get('new_score', 0):.3f}

Trades: {details.get('sample_size', 0)}
"""
        
        else:
            return
        
        await self.send_message(message)
    
    async def get_updates(self, offset: Optional[int] = None) -> List[Dict]:
        """
        Get new messages from Telegram
        """
        if not self.enabled:
            return []
        
        try:
            url = f"{self.api_url}/getUpdates"
            params = {
                'timeout': 5,
                'allowed_updates': ['message']
            }
            
            if offset:
                params['offset'] = offset
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('result', [])
                    return []
        
        except Exception as e:
            log.error("telegram_get_updates_error", error=str(e))
            return []
    
    async def send_stats_summary(self, stats: Dict):
        """
        Send formatted stats summary
        """
        overview = stats['database_stats']['overview']
        performance = stats['database_stats']['performance']
        volume = stats['database_stats']['volume']
        
        message = f"""
📊 <b>PERFORMANCE SUMMARY</b>

<b>📈 Overview:</b>
- Total Trades: {overview['total_trades']}
- Active: {overview['active_trades']} | Completed: {overview['completed_trades']}
- Win Rate: <b>{overview['win_rate']}</b>
- Total P&L: <b>{overview['total_pnl']}</b>
- Avg P&L: {overview['avg_pnl']}

<b>🎯 Performance:</b>
- Wins: {performance['wins']} | Losses: {performance['losses']}
- Best Trade: {performance['best_trade']}
- Worst Trade: {performance['worst_trade']}
- Avg Duration: {performance['avg_duration']}

<b>💰 Volume:</b>
- Total: {volume['total_volume']}
- Avg Position: {volume['avg_position_size']}
"""
        await self.send_message(message)
    
    async def send_recent_trades(self, recent_trades: List[Dict], limit: int = 10):
        """
        Send recent trades list
        """
        if not recent_trades:
            await self.send_message("📝 <b>No trades yet</b>")
            return
        
        message = f"📝 <b>RECENT TRADES (Last {min(limit, len(recent_trades))})</b>\n\n"
        
        for i, trade in enumerate(recent_trades[:limit], 1):
            status_emoji = "✅" if trade.get('outcome') == 'win' else "❌" if trade.get('outcome') == 'loss' else "⏳"
            pnl = trade.get('pnl', 0)
            pnl_str = f"${pnl:+.2f}" if pnl != 0 else "Active"
            
            market = trade.get('market_question', 'Unknown')
            if len(market) > 50:
                market = market[:47] + "..."
            
            message += f"{status_emoji} <b>#{i}</b> {market}\n"
            message += f"   {trade['direction']} ${trade['position_size']:.0f} | {pnl_str}\n"
            message += f"   {trade['timestamp'][:10]}\n\n"
        
        await self.send_message(message)
    
    async def send_active_trades(self, active_trades: List[Dict]):
        """
        Send list of currently active trades
        """
        if not active_trades:
            await self.send_message("⏳ <b>No active trades</b>")
            return
        
        message = f"⏳ <b>ACTIVE TRADES ({len(active_trades)})</b>\n\n"
        
        for i, trade in enumerate(active_trades, 1):
            market = trade.get('market_question', 'Unknown')
            if len(market) > 50:
                market = market[:47] + "..."
            
            opened = trade['timestamp'][:10]
            
            message += f"<b>#{i}</b> {market}\n"
            message += f"   {trade['direction']} ${trade['position_size']:.0f}\n"
            message += f"   Opened: {opened} | Conf: {trade['confidence']:.0%}\n\n"
        
        await self.send_message(message)
    
    async def send_whale_rankings(self, whale_stats: Dict):
        """
        Send whale performance rankings
        """
        if not whale_stats:
            await self.send_message("🐋 <b>No whale data yet</b>")
            return
        
        # Sort whales by P&L
        sorted_whales = sorted(
            whale_stats.items(),
            key=lambda x: x[1].get('pnl', 0),
            reverse=True
        )
        
        message = f"🐋 <b>TOP WHALES</b>\n\n"
        
        for i, (whale_id, stats) in enumerate(sorted_whales[:10], 1):
            trades = stats.get('trades', 0)
            wins = stats.get('wins', 0)
            pnl = stats.get('pnl', 0)
            
            win_rate = (wins / trades * 100) if trades > 0 else 0
            
            whale_short = whale_id[:8] + "..." + whale_id[-6:]
            
            message += f"<b>#{i}</b> <code>{whale_short}</code>\n"
            message += f"   Trades: {trades} | WR: {win_rate:.0f}% | P&L: ${pnl:+.0f}\n\n"
        
        await self.send_message(message)
    
    async def send_help_message(self):
        """
        Send list of available commands
        """
        message = """
🤖 <b>BOT COMMANDS</b>

<b>Statistics:</b>
/stats - Performance summary
/trades - Recent trades (last 10)
/active - Active positions
/whales - Whale rankings

<b>System:</b>
/status - Bot status
/help - This message

Just type any command in this chat!
"""
        await self.send_message(message)
    
    async def send_bot_status(self, bot_status: Dict):
        """
        Send current bot operational status
        """
        capital = bot_status.get('capital_metrics', {})
        
        message = f"""
🤖 <b>BOT STATUS</b>

<b>System:</b>
- Status: <b>RUNNING ✅</b>
- Mode: PAPER TRADING
- Whales Monitored: {bot_status.get('whales_monitored', 0)}

<b>Capital:</b>
- Free: ${capital.get('free_capital', 0):.2f}
- Locked: ${capital.get('locked_capital', 0):.2f}
- Utilization: {capital.get('capital_utilization', 0):.1%}

<b>Activity:</b>
- Active Trades: {bot_status.get('active_trades', 0)}
- Completed: {bot_status.get('completed_trades', 0)}
- Avg Duration: {capital.get('avg_duration_days', 0):.1f} days

Last Update: {bot_status.get('timestamp', 'N/A')}
"""
        await self.send_message(message)
