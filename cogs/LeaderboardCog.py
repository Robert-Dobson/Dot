import asyncio
from discord import app_commands
from discord.ext import commands, tasks
import json
import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)
LEADERBOARD_FILE = Path("./leaderboard.json")
LOCK = asyncio.Lock()  # Lock around any leaderboard read/write operations to prevent race conditions


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.leaderboard = {}

    async def load_leaderboard(self):
        """
        Load the leaderboard from the JSON file and save to self.leaderboard.

        The expected structure of the leaderboard JSON is:
        {
            guild_id_1: {
                user_id_2: message_count,
                ...
            },
        }
        """

        async with LOCK:
            if LEADERBOARD_FILE.exists():
                with open(LEADERBOARD_FILE, "r") as f:
                    self.leaderboard = json.load(f)
            else:
                self.leaderboard = {}

    async def dump_leaderboard(self):
        """
        Write the leaderboard to the JSON file.
        """
        async with LOCK:
            with open(LEADERBOARD_FILE, "w") as f:
                json.dump(self.leaderboard, f)

    def cog_unload(self):
        if self.bot.loop.is_running():
            LOGGER.info("Saving leaderboard (unscheduled) ...")
            self.bot.loop.create_task(self.dump_leaderboard())

    @tasks.loop(minutes=5)
    async def save_leaderboard(self):
        """
        Periodically save the leaderboard to the JSON file so it can be recovered on stop.
        """
        LOGGER.info("Saving leaderboard (scheduled) ...")
        await self.dump_leaderboard()

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Listener for the on_message event. This function is called whenever a message is sent in any channel the bot has access to.
        It updates the leaderboard with the message count for the user in the specific guild.
        """
        if message.author == self.bot.user:
            return

        guild_id = str(message.guild.id)
        user_id = str(message.author.id)

        async with LOCK:
            # Increment the message count for the user in the specific guild
            if guild_id not in self.leaderboard:
                self.leaderboard[guild_id] = {}

            if user_id in self.leaderboard[guild_id]:
                self.leaderboard[guild_id][user_id] += 1
            else:
                self.leaderboard[guild_id][user_id] = 1

    @app_commands.command(description="Display the leaderboard for the current guild")
    async def leaderboard(self, interaction):
        """
        Command to display the leaderboard for the current guild.
        It retrieves the message counts for all users in the guild and displays them in descending order.
        """
        await interaction.response.send_message("Calculating leaderboard, this might take a while!")
        guild_id = str(interaction.guild.id)

        async with LOCK:
            if guild_id not in self.leaderboard or not self.leaderboard[guild_id]:
                await interaction.followup.send("No messages have been recorded for this server yet.")
                return

            # Sort users by message count in descending order
            sorted_leaderboard = sorted(self.leaderboard[guild_id].items(), key=lambda item: item[1], reverse=True)

            # Create a formatted string for the leaderboard
            leaderboard_message = "Leaderboard:\n"
            for i, (user_id, message_count) in enumerate(sorted_leaderboard):
                user = await self.bot.fetch_user(int(user_id))
                leaderboard_message += f"{i + 1}. {user.display_name}: {message_count} messages\n"

            await interaction.followup.send(leaderboard_message)


async def setup(bot):
    cog = LeaderboardCog(bot)
    await cog.load_leaderboard()
    await bot.add_cog(cog)
