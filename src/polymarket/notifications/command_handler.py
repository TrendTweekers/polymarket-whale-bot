"""
Telegram Command Handler - Process user commands
"""

import structlog
from typing import Dict, Optional

log = structlog.get_logger()


class CommandHandler:
    """
    Handles incoming Telegram commands
    """
    
    def __init__(self, bot, telegram_notifier):
        self.bot = bot
        self.telegram = telegram_notifier
        self.last_update_id = 0
        
        # Command mapping
        self.commands = {
            '/start': self.cmd_start,
            '/help': self.cmd_help,
            '/stats': self.cmd_stats,
            '/trades': self.cmd_trades,
            '/active': self.cmd_active,
            '/whales': self.cmd_whales,
            '/status': self.cmd_status,
        }
        
        log.info("command_handler_initialized", commands=list(self.commands.keys()))
    
    async def process_updates(self):
        """
        Check for new messages and process commands
        """
        updates = await self.telegram.get_updates(offset=self.last_update_id + 1)
        
        for update in updates:
            # Update offset
            update_id = update.get('update_id', 0)
            if update_id > self.last_update_id:
                self.last_update_id = update_id
            
            # Get message
            message = update.get('message', {})
            text = message.get('text', '').strip()
            
            if not text:
                continue
            
            # Extract command
            command = text.split()[0].lower()
            
            if command in self.commands:
                log.info("command_received", command=command)
                
                try:
                    await self.commands[command](message)
                except Exception as e:
                    log.error("command_error", command=command, error=str(e))
                    await self.telegram.send_message(
                        f"❌ Error processing command: {str(e)}"
                    )
    
    async def cmd_start(self, message: Dict):
        """Handle /start command"""
        await self.telegram.send_message(
            "🐋 <b>Whale Bot Active!</b>\n\n"
            "Type /help to see available commands."
        )
    
    async def cmd_help(self, message: Dict):
        """Handle /help command"""
        await self.telegram.send_help_message()
    
    async def cmd_stats(self, message: Dict):
        """Handle /stats command"""
        stats = self.bot.get_performance_summary()
        await self.telegram.send_stats_summary(stats)
    
    async def cmd_trades(self, message: Dict):
        """Handle /trades command"""
        # Get limit from message (e.g., "/trades 20")
        text = message.get('text', '')
        parts = text.split()
        limit = 10
        
        if len(parts) > 1:
            try:
                limit = int(parts[1])
                limit = min(limit, 50)  # Cap at 50
            except ValueError:
                pass
        
        recent_trades = self.bot.db.get_recent_trades(limit)
        await self.telegram.send_recent_trades(recent_trades, limit)
    
    async def cmd_active(self, message: Dict):
        """Handle /active command"""
        active_trades = self.bot.db.get_active_trades()
        await self.telegram.send_active_trades(active_trades)
    
    async def cmd_whales(self, message: Dict):
        """Handle /whales command"""
        whale_stats = self.bot.db.stats.get('whales_tracked', {})
        await self.telegram.send_whale_rankings(whale_stats)
    
    async def cmd_status(self, message: Dict):
        """Handle /status command"""
        from datetime import datetime
        
        bot_status = {
            'whales_monitored': len(self.bot.whale_watchlist),
            'active_trades': len(self.bot.db.get_active_trades()),
            'completed_trades': len(self.bot.db.get_completed_trades()),
            'capital_metrics': self.bot.capital_tracker.get_velocity_metrics(),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        await self.telegram.send_bot_status(bot_status)
