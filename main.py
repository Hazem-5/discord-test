import discord
from discord import app_commands
from discord.ext import commands
import os
import logging
import asyncio
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Silence generator class
class Silence(discord.AudioSource):
    def __init__(self):
        self.bytes = b'\x00' * 3840 # 20ms of silence for 48kHz stereo

    def read(self):
        return self.bytes

    def is_opus(self):
        return False

class PersistentVoiceBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        logger.info("Command tree synced.")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info('Bot is ready and waiting for commands.')

    async def on_voice_state_update(self, member, before, after):
        # We only care about the bot's voice state
        if member.id != self.user.id:
            return

        # Check if disconnected
        if before.channel is not None and after.channel is None:
            logger.warning(f"Bot was disconnected from voice channel in server: {member.guild.name} (ID: {member.guild.id})")
            # Optional: Attempt to reconnect if it wasn't a manual leave? 
            # For now, just log as requested.

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
            vc = await channel.connect()

        # Play silence to keep connection alive
        if not vc.is_playing():
            vc.play(Silence())
            logger.info(f"Started playing silence in {guild.name}")

        await interaction.response.send_message(f"Joined {channel.mention} and staying forever!")
        logger.info(f"Successfully joined {channel.name} in {guild.name}")

    except Exception as e:
        logger.error(f"Error joining voice in {guild.name}: {e}")
        await interaction.response.send_message(f"Failed to join: {e}", ephemeral=True)

@client.tree.command(name="leave", description="Leaves the voice channel.")
@app_commands.checks.has_permissions(administrator=True)
async def leave(interaction: discord.Interaction):
    guild = interaction.guild
    
    logger.info(f"User {interaction.user} (ID: {interaction.user.id}) requested leave in server {guild.name} (ID: {guild.id})")

    if interaction.guild.voice_client:
        channel_name = interaction.guild.voice_client.channel.name
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Disconnected.")
        logger.info(f"Disconnected from {channel_name} in {guild.name} by command.")
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

# Run the bot
token = os.getenv("DISCORD_TOKEN")
if not token:
    logger.error("DISCORD_TOKEN not found in environment variables.")
else:
    client.run(token)
