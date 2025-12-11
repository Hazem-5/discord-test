import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from utils.logger import logger

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
        return

    bot = PersistentVoiceBot()
    try:
        bot.run(token, log_handler=None) # We use our own logger setup
    except Exception as e:
        logger.critical(f"Bot execution failed: {e}")

if __name__ == '__main__':
    main()
