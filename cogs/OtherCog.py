from datetime import datetime
from discord import app_commands
from discord.ext import commands
from zoneinfo import ZoneInfo
import random as rand


class OtherCog(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    @app_commands.command(description="Replies with test message")
    async def test(self, interaction):
        await interaction.response.send_message("Testing 123")

    @app_commands.command(description="Generates a random number from 1 to n")
    async def random(self, interaction, num: int):
        if num <= 0:
            await interaction.response.send_message(
                "Must provide a number greater than 0"
            )
            return

        await interaction.response.send_message(
            f"Random number is: {rand.randint(1, num)}"
        )

    @app_commands.command(description="Replies with what you enter")
    async def echo(self, interaction, msg: str):
        await interaction.response.send_message("Message recieved", ephemeral=True)
        await interaction.channel.send(msg)

    @app_commands.command(description="Gives current time in London and Brisbane")
    async def time(self, interaction):
        uk_time = datetime.now(ZoneInfo("Europe/London"))
        aus_time = datetime.now(ZoneInfo("Australia/Brisbane"))
        await interaction.response.send_message(
            f"LON time is {uk_time.strftime('%H:%M%p on %d %b')}\n"
            f"BRIS time is {aus_time.strftime('%H:%M%p on %d %b')}",
            ephemeral=True,
        )

    @commands.command()
    async def sync_slash_commands(self, ctx):
        ctx.bot.tree.copy_global_to(guild=ctx.guild)
        await self.bot.tree.sync(guild=ctx.guild)


async def setup(bot):
    await bot.add_cog(OtherCog(bot))
