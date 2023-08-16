import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import random as rand
import logging
import os


bot = commands.Bot(command_prefix="/", intents=discord.Intents.all())

# Load in all cogs
for filename in os.listdir("cogs"):
    if filename.endswith(".py"):
        asyncio.run(bot.load_extension(f"cogs.{filename[:-3]}"))


@bot.command()
async def test(ctx):
    await ctx.send("Testing 123")


@bot.command()
async def random(ctx, *args):
    if len(args) == 0:
        await ctx.send("You must provide an arugment (a number)")
        return
    elif len(args) > 1:
        await ctx.send("Too many arguments")
        return

    if not args[0].isnumeric():
        await ctx.send("Must provide a number")
        return

    await ctx.send(f"Random number is: {rand.randint(1, int(args[0]))}")


# Run Bot
handler = logging.FileHandler(filename="dot.log", encoding="utf-8", mode="a")
load_dotenv()
bot.run(
    os.getenv("discord_token"),
    log_handler=handler,
    root_logger=True,
    log_level=logging.INFO,
)
