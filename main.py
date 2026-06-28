import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
import os
import signal


class DotBot(commands.Bot):
    async def close(self):
        # Flush the leaderboard to disk before shutting down
        leaderboard = self.get_cog("LeaderboardCog")
        if leaderboard is not None:
            try:
                await leaderboard.dump_leaderboard()
            except Exception:
                logging.exception("Failed to flush leaderboard during shutdown")

        await super().close()


async def main():
    handler = RotatingFileHandler(filename="dot.log", encoding="utf-8", mode="a", maxBytes=1024 * 1024 * 20, backupCount=5)

    bot = DotBot(command_prefix="/", intents=discord.Intents.all())

    # Load in all cogs
    for filename in os.listdir("cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")

    loop = asyncio.get_running_loop()

    def stop_bot():
        asyncio.create_task(bot.close())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_bot)
        except NotImplementedError:
            pass

    load_dotenv()
    await bot.start(
        os.getenv("discord_token"),
        log_handler=handler,
        root_logger=True,
        log_level=logging.INFO,
    )


if __name__ == "__main__":
    asyncio.run(main())
