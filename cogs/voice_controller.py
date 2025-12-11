import discord
from discord.ext import commands
from discord import app_commands
from utils.logger import logger
from utils.silence import Silence
import asyncio

class VoiceController(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.target_channel_id = None
        self.is_reconnecting = False
        self.manual_leave = False
        self._ALLOWED_USERS = [624715026669764620]  # Your UID
        self.watchdog_task = self.bot.loop.create_task(self.connection_watchdog())

    async def connection_watchdog(self):
        """Periodically checks if the bot should be connected and reconnects if needed."""
        await self.bot.wait_until_ready()
        logger.info("Connection watchdog started.")
        while not self.bot.is_closed():
            try:
                if self.target_channel_id and not self.manual_leave:
                    # We should be connected
                    connected = False
                    for guild in self.bot.guilds:
                        if guild.voice_client:
                             if guild.voice_client.channel and guild.voice_client.channel.id == self.target_channel_id:
                                 connected = True
                                 break
                    
                    if not connected:
                        logger.warning("Watchdog detected bot is not connected to target channel. Reconnecting...")
                        # Find the guild for the target channel
                        target_guild = None
                        for guild in self.bot.guilds:
                            if guild.get_channel(self.target_channel_id):
                                target_guild = guild
                                break
                        
                        if target_guild:
                            await self.reconnect(target_guild)
                        else:
                            logger.error(f"Could not find guild for target channel {self.target_channel_id}")
                            
            except Exception as e:
                logger.error(f"Error in connection watchdog: {e}")
            
            await asyncio.sleep(5) # Check every 5 seconds

    def is_allowed(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in self._ALLOWED_USERS:
            return True
        if interaction.user.guild_permissions.administrator:
            return True
        return False

    async def keep_alive_loop(self, voice_client):
        """Ensures audio is always playing."""
        logger.info("Starting keep-alive loop.")
        while voice_client.is_connected():
            if not voice_client.is_playing():
                try:
                    voice_client.play(Silence())
                    logger.info("Restarted silence playback.")
                except Exception as e:
                    logger.error(f"Error playing silence: {e}")
            await asyncio.sleep(5) # Check every 5 seconds

    @app_commands.command(name="join", description="Join your voice channel and stay there 24/7.")
    async def join(self, interaction: discord.Interaction):
        if not self.is_allowed(interaction):
            await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("Please join a voice channel first!", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        self.target_channel_id = channel.id
        self.manual_leave = False
        
        await interaction.response.defer()

        try:
            # Check if already connected
            if interaction.guild.voice_client:
                if interaction.guild.voice_client.channel.id == channel.id:
                    await interaction.followup.send(f"Already connected to {channel.mention}.")
                    return
                else:
                    await interaction.guild.voice_client.move_to(channel)
            else:
                await channel.connect(self_deaf=True) # Self-deaf is often better for connection stability

            # Verification step: Ensure we are actually connected
            vc = interaction.guild.voice_client
            if not vc or not vc.is_connected():
                raise Exception("Voice client is None or not connected after connect() call.")

            logger.info(f"Joined voice channel: {channel.name} ({channel.id}) in guild: {interaction.guild.name}")
            
            # Start keep-alive
            try:
                if vc.is_playing():
                    vc.stop() # Stop anything currently playing
                
                vc.play(Silence())
                logger.info("Started playing silence.")
            except Exception as e:
                logger.error(f"Failed to play silence audio: {e}", exc_info=True)
                await interaction.followup.send(f"⚠️ Joined {channel.mention}, but failed to start audio: {repr(e)}")
                
                # Send debug info to chat if available
                if hasattr(self.bot, 'opus_debug_info'):
                     # Truncate to avoid limit
                     debug_preview = self.bot.opus_debug_info[-1500:] 
                     await interaction.followup.send(f"**Debug Info:**\n```\n{debug_preview}\n```")
                # We don't return here, we still try to start the loop often, or maybe we should?
                # If play() fails, the loop might also fail, but let's try to start the loop anyway as a fallback.

            # Also start a background task to monitor playing status
            self.bot.loop.create_task(self.keep_alive_loop(vc))

            await interaction.followup.send(f"✅ Joined {channel.mention} and started persistent session.")

        except Exception as e:
            logger.error(f"Failed to join voice channel: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to join: {e}")

    @app_commands.command(name="leave", description="Leave the voice channel (stops auto-reconnect).")
    async def leave(self, interaction: discord.Interaction):
        if not self.is_allowed(interaction):
            await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)
            return

        if not interaction.guild.voice_client:
            await interaction.response.send_message("I am not in a voice channel.", ephemeral=True)
            return

        self.manual_leave = True
        self.target_channel_id = None
        
        await interaction.guild.voice_client.disconnect(force=True)
        await interaction.response.send_message("👋 Disconnected. Auto-reconnect disabled.")
        logger.info("Manually disconnected by command.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # We only care about the bot's voice state updates
        if member.id != self.bot.user.id:
            return

        if self.manual_leave:
            return

        # If disconnected (channel is None)
        if after.channel is None and self.target_channel_id:
            logger.warning("Bot disconnected unexpectedly! Attempting to reconnect...")
            await self.reconnect(member.guild)

    async def reconnect(self, guild):
        if self.is_reconnecting:
            return
        
        self.is_reconnecting = True
        try:
            channel = guild.get_channel(self.target_channel_id)
            if not channel:
                logger.error(f"Target channel {self.target_channel_id} not found.")
                self.is_reconnecting = False
                return

            # Simple exponential backoff or retry loop
            for i in range(1, 6): # Try 5 times
                try:
                    logger.info(f"Reconnection attempt {i}...")
                    if guild.voice_client:
                        try:
                            await guild.voice_client.disconnect(force=True)
                        except: 
                            pass # Ignore cleanup errors
                    
                    await asyncio.sleep(2 * i) # Wait before retry
                    await channel.connect(self_deaf=True)
                    vc = guild.voice_client
                    vc.play(Silence())
                    self.bot.loop.create_task(self.keep_alive_loop(vc))
                    logger.info("Successfully reconnected!")
                    break
                except Exception as e:
                    logger.error(f"Reconnection attempt {i} failed: {e}")
            else:
                logger.critical("Failed to reconnect after multiple attempts.")
        finally:
            self.is_reconnecting = False

async def setup(bot):
    await bot.add_cog(VoiceController(bot))

