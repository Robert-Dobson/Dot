import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
import os


bot = commands.Bot(command_prefix="/", intents=discord.Intents.all())

# Load in all cogs
for filename in os.listdir("cogs"):
    if filename.endswith(".py"):
        asyncio.run(bot.load_extension(f"cogs.{filename[:-3]}"))

# Run Bot
handler = logging.FileHandler(filename="dot.log", encoding="utf-8", mode="a")
load_dotenv()
bot.run(
    os.getenv("discord_token"),
    log_handler=handler,
    root_logger=True,
    log_level=logging.INFO,
)
