import sys

import discord
from discord import option
from discord.ext import commands

sys.set_int_max_str_digits(0)

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
        async def multiply(x, y):
            _CUTOFF = 1536
            if x.bit_length() <= _CUTOFF or y.bit_length() <= _CUTOFF:
                return x * y

            else:
                n = max(x.bit_length(), y.bit_length())
                half = (n + 32) // 64 * 32
                mask = (1 << half) - 1
                xlow = x & mask
                ylow = y & mask
                xhigh = x >> half
                yhigh = y >> half

                a = await multiply(xhigh, yhigh)
                b = await multiply(xlow + xhigh, ylow + yhigh)
                c = await multiply(xlow, ylow)
                d = b - a - c
                return (((a << half) + d) << half) + c

        async def fibonacci(n):
            if n == 0:
                return (0, 1)
            else:
                a, b = await fibonacci(n // 2)
                c = await multiply(a, (await multiply(b, 2) - a))
                d = await multiply(a, a) + await multiply(b, b)
                if n % 2 == 0:
                    return (c, d)
                else:
                    return (d, c + d)

        async def multi_msg(seq):
            seq = str(seq)
            while seq:
                yield int(seq[:2000])
                seq = seq[2000:]

        if n < 0:
            ctx.respond("Please enter a positive integer.")
        elif n > 1000000:
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
            number = await fibonacci(int(n))
            messages = number[0]
            messages = await multi_msg(messages)
            for item in messages:
                await ctx.send(item)


def setup(bot):
    bot.add_cog(Misc(bot))
