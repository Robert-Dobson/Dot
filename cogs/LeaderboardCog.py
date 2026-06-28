from discord import app_commands
from discord.ext import commands
import json
import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)
LEADERBOARD_FILE = Path("./leaderboard.json")


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    def get_leaderboard(self):
        """
        Load the leaderboard from the JSON file. If the file doesn't exist, return an empty dictionary.

        The expected structure of the leaderboard JSON is:
        {
            guild_id_1: {
                user_id_2: message_count,
                ...
            },
        }
        """
        if LEADERBOARD_FILE.exists():
            with open(LEADERBOARD_FILE, "r") as f:
                return json.load(f)
        else:
            return {}

    def write_leaderboard(self, leaderboard):
        """
        Write the leaderboard to the JSON file.
        """
        with open(LEADERBOARD_FILE, "w") as f:
            json.dump(leaderboard, f)

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Listener for the on_message event. This function is called whenever a message is sent in any channel the bot has access to.
        It updates the leaderboard with the message count for the user in the specific guild.
        """
        if message.author == self.bot.user:
            return

        LOGGER.info(f"Message received from {message.author.name} from {message.guild.name}")
        leaderboard = self.get_leaderboard()
        guild_id = str(message.guild.id)
        user_id = str(message.author.id)

        # Increment the message count for the user in the specific guild
        if guild_id not in leaderboard:
            leaderboard[guild_id] = {}

        if user_id in leaderboard[guild_id]:
            leaderboard[guild_id][user_id] += 1
        else:
            leaderboard[guild_id][user_id] = 1

        self.write_leaderboard(leaderboard)

    @app_commands.command(description="Display the leaderboard for the current guild")
    async def leaderboard(self, interaction):
        """
        Command to display the leaderboard for the current guild.
        It retrieves the message counts for all users in the guild and displays them in descending order.
        """
        await interaction.response.send_message("Calculating leaderboard, this might take a while!")
        leaderboard = self.get_leaderboard()
        guild_id = str(interaction.guild.id)

        if guild_id not in leaderboard or not leaderboard[guild_id]:
            await interaction.followup.send("No messages have been recorded for this server yet.")
            return


        # Sort users by message count in descending order
        sorted_leaderboard = sorted(leaderboard[guild_id].items(), key=lambda item: item[1], reverse=True)

        # Create a formatted string for the leaderboard
        leaderboard_message = "Leaderboard:\n"
        for i, (user_id, message_count) in enumerate(sorted_leaderboard):
            user = await self.bot.fetch_user(int(user_id))
            leaderboard_message += f"{i + 1}. {user.display_name}: {message_count} messages\n"

        await interaction.followup.send(leaderboard_message)


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
