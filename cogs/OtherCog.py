from discord.ext import commands
import random as rand


class OtherCog(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    @commands.hybrid_command(
        brief="Replies with test message (usage /test)",
        description="Replies with test message",
    )
    async def test(self, ctx):
        await ctx.send("Testing 123")

    @commands.hybrid_command(
        brief="Generates a random number from 1 to n (usage /random <n>)",
        description="Generates a random number from 1 to n",
    )
    async def random(self, ctx, num):
        # if len(args) == 0:
        #     await ctx.send("You must provide an arugment (a number)")
        #     return
        # elif len(args) > 1:
        #     await ctx.send("Too many arguments")
        #     return

        if not num.isnumeric():
            await ctx.send("Must provide a number")
            return

        await ctx.send(f"Random number is: {rand.randint(1, int(num))}")

    @commands.command()
    async def sync_slash_commands(self, ctx):
        ctx.bot.tree.copy_global_to(guild=ctx.guild)
        await self.bot.tree.sync(guild=ctx.guild)


async def setup(bot):
    await bot.add_cog(OtherCog(bot))
