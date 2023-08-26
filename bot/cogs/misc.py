import discord
from discord import option
from discord.ext import commands

from complex import fibonacci, multi_msg

GUILD_IDS = [1024196422637195315, 1099937674200105030]
owner_ids = [755525460267630612]


class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = commands.Bot = bot

    @commands.Cog.listener()
    async def on_connect(self):
        print("Misc commands loaded")

    @commands.slash_command(
        description="Calculate big fibonacci numbers", guild_id=GUILD_IDS
    )
    @option(
        "n",
        int,
        description="The nth term of the fibonacci sequence (0 <= n <= 1000000)",
    )
    async def fibonacci(self, ctx, n):
        if n < 0:
            ctx.respond("Please enter a positive integer.")
        elif n > 10000001:
            ctx.respond("Bruh way too big")
        else:
            message = "Working on it... The "
            if n % 10 == 1 and n != 11:
                message += f"{n}st "
            elif n % 10 == 2 and n != 12:
                message += f"{n}nd "
            elif n % 10 == 3 and n != 13:
                message += f"{n}rd "
            else:
                message += f"{n}th "
            message += "number in the fibonacci sequence is:"
            await ctx.respond(message)
            number = fibonacci(int(n))
            messages = number[0]
            messages = multi_msg(messages)
            for item in messages:
                await ctx.send(item)


def setup(bot):
    bot.add_cog(Misc(bot))
