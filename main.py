import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import logging

bot = commands.Bot(command_prefix = "/", intents = discord.Intents.all())

# Load in all cogs
for filename in os.listdir('cogs'):
    if filename.endswith('.py'):
        asyncio.run(bot.load_extension(f'cogs.{filename[:-3]}'))

@bot.command()
async def test(ctx):
    await ctx.send("Testing 123")

# Run Bot
handler = logging.FileHandler(filename='dot.log', encoding='utf-8', mode='a')
load_dotenv()
bot.run(os.getenv("discord_token"), log_handler=handler, root_logger=True, log_level=logging.INFO) 