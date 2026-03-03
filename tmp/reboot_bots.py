import asyncio
import logging
import os
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("reboot_bots")

# Load environment variables
load_dotenv()

async def reboot():
    from tradeengine.database.connection import init_db
    from tradeengine.dashboard.bot_manager import BotManager
    from tradeengine.config import load_config
    from tradeengine.strategies.registry import auto_discover, list_strategies
    
    # 1. Initialize Database
    logger.info("Initializing Supabase connection...")
    try:
        await init_db()
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        return

    # 2. Discover Strategies
    logger.info("Discovering strategies...")
    auto_discover()
    strats = list_strategies()
    logger.info(f"Available strategies: {[s['name'] for s in strats]}")
    
    # 3. Initialize BotManager
    config = load_config()
    bot_manager = BotManager()
    
    logger.info("Initializing BotManager...")
    await bot_manager.init_db()
    
    bots_to_restart = list(bot_manager._pending_restart)
    if not bots_to_restart:
        logger.info("No bots found with auto_start=True in the database.")
        return

    logger.info(f"Bots currently in pending restart: {bots_to_restart}")
    
    # 4. Trigger Auto-Restart
    logger.info("Starting auto-restart process...")
    restarted = await bot_manager.auto_restart_bots(app_config=config)
    
    logger.info(f"Restart process complete. {len(restarted)} bots successfully restarted.")
    logger.info(f"Successfully restarted: {restarted}")
    
    # 5. Summary
    await asyncio.sleep(5)
    from tradeengine.database.connection import get_session
    session = await get_session()
    try:
        result = session.table("bots").select("bot_id, name, status, error_msg").execute()
        running_count = 0
        error_count = 0
        stopped_count = 0
        for bot in result.data:
            status = bot['status']
            if status == "running":
                running_count += 1
            elif status == "error":
                error_count += 1
                logger.warning(f"Bot {bot['bot_id']} ({bot['name']}) failed with error: {bot['error_msg']}")
            else:
                stopped_count += 1
        
        logger.info(f"Final Status Summary: Running={running_count}, Error={error_count}, Stopped={stopped_count}")
    finally:
        await session.close()
    
    # Keep script alive for a bit if tasks are backgrounded (though auto_restart_bots waits)
    await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(reboot())
