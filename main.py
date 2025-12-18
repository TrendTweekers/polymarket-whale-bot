"""
Main entry point for the whale bot
"""

import asyncio
import yaml
import structlog
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

from src.polymarket import WhaleBot

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

log = structlog.get_logger()


async def main():
    """Main function"""
    
    # Load configuration
    config_path = Path("config/config.yaml")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    log.info("bot_starting", config=config_path)
    
    # Initialize bot
    bot = WhaleBot(config)
    
    try:
        # Start bot
        await bot.start()
    
    except KeyboardInterrupt:
        log.info("shutdown_requested")
        await bot.stop()
    
    except Exception as e:
        log.error("bot_error", error=str(e))
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
