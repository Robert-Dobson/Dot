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
            f"BNE time is {aus_time.strftime('%H:%M%p on %d %b')}",
            ephemeral=True,
        )

    @app_commands.command(description="Check bot's voice setup and dependencies")
    async def voice_check(self, interaction):
        """Diagnostic command to check voice setup"""
        import subprocess
        import sys
        
        embed = discord.Embed(title="🔍 Voice Setup Diagnostics", color=0x00ff00)
        
        # Check PyNaCl
        try:
            import nacl
            embed.add_field(name="✅ PyNaCl", value=f"Installed: {nacl.__version__}", inline=False)
        except ImportError:
            embed.add_field(name="❌ PyNaCl", value="Not installed! Run: `pip install PyNaCl`", inline=False)
        
        # Check FFmpeg
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                version = result.stdout.split('\n')[0]
                embed.add_field(name="✅ FFmpeg", value=f"Available: {version[:50]}...", inline=False)
            else:
                embed.add_field(name="❌ FFmpeg", value="Found but not working properly", inline=False)
        except FileNotFoundError:
            embed.add_field(name="❌ FFmpeg", value="Not found! Install: `sudo apt install ffmpeg`", inline=False)
        except subprocess.TimeoutExpired:
            embed.add_field(name="⚠️ FFmpeg", value="Found but slow to respond", inline=False)
        except Exception as e:
            embed.add_field(name="❌ FFmpeg", value=f"Error checking: {str(e)}", inline=False)
        
        # Check Discord.py version
        embed.add_field(name="📦 Discord.py", value=f"Version: {discord.__version__}", inline=False)
        
        # Check Python version
        embed.add_field(name="🐍 Python", value=f"Version: {sys.version.split()[0]}", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command()
    async def sync_slash_commands(self, ctx):
        ctx.bot.tree.copy_global_to(guild=ctx.guild)
        await self.bot.tree.sync(guild=ctx.guild)


async def setup(bot):
    await bot.add_cog(OtherCog(bot))
