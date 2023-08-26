from discord.ext import commands
import random as rand


class OtherCog(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    @commands.command(
        brief="Replies with test message (usage /test)",
        description="Replies with test message",
    )
    async def test(self, ctx):
        await ctx.send("Testing 123")

    @commands.command(
        brief="Generates a random number from 1 to n (usage /random <n>)",
        description="Generates a random number from 1 to n\n" \
        "Arguments: <n> - Random number to generate up to",
    )
    async def random(self, ctx, *args):
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


async def setup(bot):
    await bot.add_cog(OtherCog(bot))
