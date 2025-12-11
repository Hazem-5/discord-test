import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from utils.logger import logger
import discord.opus
import ctypes.util
import glob
import platform

load_dotenv()

class PersistentVoiceBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.guilds = True 
        # Message content is not strictly needed for slash commands, 
        # but good to have if you expand features or use text commands later.
        # intents.message_content = True 

        super().__init__(
            command_prefix="!", 
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        # Load extensions/cogs
        try:
            await self.load_extension('cogs.voice_controller')
            logger.info("Loaded extension: cogs.voice_controller")
        except Exception as e:
            logger.error(f"Failed to load extension: {e}")
        
        # Sync application commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s).")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info(f'Connected to {len(self.guilds)} guilds')

    async def on_connect(self):
        logger.info("Bot connected to Discord Gateway.")
        
    async def on_disconnect(self):
        logger.warning("Bot disconnected from Discord Gateway.")

def main():
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.critical("DISCORD_TOKEN not found in environment variables.")
    if not token:
        logger.critical("DISCORD_TOKEN not found in environment variables.")
        return

    # Check and load Opus
    logger.info("=== OPUS DEBUG START ===")
    logger.info(f"OS: {os.name}, Platform: {platform.system()} {platform.release()} ({platform.machine()})")
    
    found_lib = ctypes.util.find_library('opus')
    logger.info(f"ctypes.util.find_library('opus') -> {found_lib}")
    
    # Manual scan of common dirs
    search_paths = ['/usr/lib', '/usr/local/lib', '/lib', '/lib64', '/usr/lib64']
    for path in search_paths:
        try:
            matches = glob.glob(f"{path}/**/*opus*.so*", recursive=True)
            for m in matches:
                logger.info(f"Found candidate: {m}")
        except Exception as e:
            logger.error(f"Error scanning {path}: {e}")
    logger.info("=== OPUS DEBUG END ===")

    if not discord.opus.is_loaded():
        try:
            discord.opus.load_opus('opus')
        except Exception as e:
            logger.warning(f"Could not load 'opus': {e}")
            
            # IMPROVEMENT: Try common Linux filename specifically
            try:
                discord.opus.load_opus('libopus.so.0')
                logger.info("Successfully loaded 'libopus.so.0'")
            except Exception as e2:
                logger.warning(f"Could not load 'libopus.so.0': {e2}")

            logger.warning("Voice may not work. If on Windows, please ensure 'opus.dll' is in the bot directory.")
            
            # Try to help user by pointing to likely filename if on Windows
            if os.name == 'nt':
                try:
                    discord.opus.load_opus('./opus.dll')
                    logger.info("Successfully loaded './opus.dll'")
                except:
                    pass # We already logged the warning above

    if not discord.opus.is_loaded():
         logger.critical("Opus library is NOT loaded. Voice features will fail! Please download opus.dll.")

    bot = PersistentVoiceBot()
    try:
        bot.run(token, log_handler=None) # We use our own logger setup
    except Exception as e:
        logger.critical(f"Bot execution failed: {e}")

if __name__ == '__main__':
    main()
