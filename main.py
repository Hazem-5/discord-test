import discord
from discord import app_commands
from discord.ext import commands
import os
import logging
import asyncio
import sys
import signal
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Opus Silence generator class
class OpusSilence(discord.AudioSource):
    def __init__(self):
        self.bytes = b'\xF8\xFF\xFE'

    def read(self):
        return self.bytes

    def is_opus(self):
        return True

class PersistentVoiceBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.intentional_disconnects = set()
        self.voice_state_file = "voice_state.json"
        self.saved_voice_state = self.load_voice_state()

    def load_voice_state(self):
        if os.path.exists(self.voice_state_file):
            try:
                with open(self.voice_state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load voice state: {e}")
                return {}
        return {}

    def save_voice_state(self):
        try:
            with open(self.voice_state_file, 'w') as f:
                json.dump(self.saved_voice_state, f)
        except Exception as e:
            logger.error(f"Failed to save voice state: {e}")

    async def setup_hook(self):
        await self.tree.sync()
        logger.info("Command tree synced.")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info('Bot is ready and waiting for commands.')

        # Restore voice connections
        for guild_id_str, channel_id in self.saved_voice_state.items():
            try:
                guild_id = int(guild_id_str)
                guild = self.get_guild(guild_id)
                if guild:
                    channel = guild.get_channel(channel_id)
                    if channel:
                        logger.info(f"Restoring connection to {channel.name} in {guild.name}...")
                        vc = await channel.connect(self_deaf=True)
                        if not vc.is_playing():
                            vc.play(OpusSilence())
                            logger.info(f"Resumed playing silence in {guild.name}")
                    else:
                        logger.warning(f"Channel ID {channel_id} not found in guild {guild.name}")
                else:
                    logger.warning(f"Guild ID {guild_id} not found")
            except Exception as e:
                logger.error(f"Failed to restore connection for guild {guild_id_str}: {e}")

    async def on_voice_state_update(self, member, before, after):
        # We only care about the bot's voice state
        if member.id != self.user.id:
            return

        # Check if disconnected
        if before.channel is not None and after.channel is None:
            if member.guild.id in self.intentional_disconnects:
                logger.info(f"Intentional disconnect from {member.guild.name}. Not reconnecting.")
                self.intentional_disconnects.remove(member.guild.id)
                return

            logger.warning(f"Bot was disconnected from voice channel in server: {member.guild.name} (ID: {member.guild.id})")
            
            # Attempt to reconnect
            try:
                logger.info(f"Wait 5s before reconnecting to {before.channel.name} in {member.guild.name}...")
                await asyncio.sleep(5)

                # Cleanup potential stale voice client
                if member.guild.voice_client:
                    logger.info("Cleaning up stale voice client...")
                    try:
                        await member.guild.voice_client.disconnect(force=True)
                    except Exception as e:
                        logger.warning(f"Error disconnecting stale client: {e}")

                logger.info(f"Connecting to {before.channel.name}...")
                vc = await before.channel.connect(self_deaf=True)
                
                # Play silence to keep connection alive
                if not vc.is_playing():
                    vc.play(OpusSilence())
                    logger.info(f"Resumed playing silence in {member.guild.name} after reconnect")
                
                logger.info(f"Successfully reconnected to {before.channel.name}")
            except Exception as e:
                logger.error(f"Failed to reconnect to {before.channel.name}: {e}")

client = PersistentVoiceBot()

@client.tree.command(name="join", description="Joins your voice channel and stays there.")
@app_commands.checks.has_permissions(administrator=True)
async def join(interaction: discord.Interaction):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("You are not in a voice channel.", ephemeral=True)
        return

    channel = interaction.user.voice.channel
    guild = interaction.guild

    logger.info(f"User {interaction.user} (ID: {interaction.user.id}) requested join in server {guild.name} (ID: {guild.id}) to channel {channel.name} (ID: {channel.id})")

    try:
        # Check if already connected to a voice channel in this guild
        if interaction.guild.voice_client:
            if interaction.guild.voice_client.channel.id == channel.id:
                await interaction.response.send_message("I am already in this channel.", ephemeral=True)
                return
            else:
                await interaction.guild.voice_client.move_to(channel)
                vc = interaction.guild.voice_client
        else:
            vc = await channel.connect(self_deaf=True)

        # Play silence to keep connection alive
        if not vc.is_playing():
            vc.play(OpusSilence())
            logger.info(f"Started playing silence in {guild.name}")

        await interaction.response.send_message(f"Joined {channel.mention} and staying forever!")
        logger.info(f"Successfully joined {channel.name} in {guild.name}")

        # Save state
        client.saved_voice_state[str(guild.id)] = channel.id
        client.save_voice_state()

    except Exception as e:
        logger.error(f"Error joining voice in {guild.name}: {e}")
        await interaction.response.send_message(f"Failed to join: {e}", ephemeral=True)

@client.tree.command(name="leave", description="Leaves the voice channel.")
@app_commands.checks.has_permissions(administrator=True)
async def leave(interaction: discord.Interaction):
    guild = interaction.guild
    
    logger.info(f"User {interaction.user} (ID: {interaction.user.id}) requested leave in server {guild.name} (ID: {guild.id})")

    if interaction.guild.voice_client:
        # Mark as intentional disconnect
        client.intentional_disconnects.add(guild.id)
        
        channel_name = interaction.guild.voice_client.channel.name
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Disconnected.")
        logger.info(f"Disconnected from {channel_name} in {guild.name} by command.")
        
        # Remove from saved state
        if str(guild.id) in client.saved_voice_state:
            del client.saved_voice_state[str(guild.id)]
            client.save_voice_state()
    else:
        await interaction.response.send_message("I am not in a voice channel.", ephemeral=True)

@join.error
@leave.error
async def error_handler(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You need Administrator permissions to use this command.", ephemeral=True)
        logger.warning(f"User {interaction.user} tried to use command without permissions in {interaction.guild.name}")
    else:
        logger.error(f"Command error: {error}")
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)

def signal_handler(signum, frame):
    signame = signal.Signals(signum).name
    logger.info(f"Received signal {signame}, shutting down...")

# Run the bot
token = os.getenv("DISCORD_TOKEN")
if not token:
    logger.error("DISCORD_TOKEN not found in environment variables.")
else:
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    client.run(token)
