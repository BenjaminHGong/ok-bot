import discord
from discord import option
from discord.ext import commands

from grammar import check_grammar
from jsonedit import get_data, update_data
from main import throw_error

from complex import fibonacci, multi_msg

GUILD_IDS = [1024196422637195315, 1099937674200105030]
owner_ids = [755525460267630612]


class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = commands.Bot = bot

    @commands.Cog.listener()
    async def on_connect(self):
        print("Misc commands loaded")

    @commands.Cog.listener()
    async def on_message(self, message):
        mute_list = await get_data("mute")
        if message.author.id in mute_list:
            await message.delete()
            await message.author.send("You are muted")

        if not message.author.bot:
            grammar_list = await get_data("grammar")
            message_list = await get_data("autorespond")
            if message.author.id in grammar_list:
                if await check_grammar(message.content) != False:
                    response = f"<@{message.author.id}> " + await check_grammar(
                        message.content
                    )
                    await message.channel.send(response)
            if len(message_list) > 0:
                for respond_config in message_list:
                    needle = respond_config["needle"]
                    needle.lower()
                    if " " not in needle:
                        message.content.lower()
                        txt = message.content.split()
                    else:
                        txt = message.content.lower()
                    if needle in txt:
                        await message.channel.send(respond_config["message"])
                        break
        if (
            message.author.bot
            and message.author.id != 1099931878926078022
            and message.author.id != 235148962103951360
            and message.guild.id != 1099937674200105030
            and message.channel.id != 1034679492586778674
        ):
            await message.delete()
            await message.channel.send("<#1034679492586778674>")
    
    @commands.slash_command(
        description="Calculate big fibonacci numbers", guild_id=GUILD_IDS
    )
    @option("n", int, description="The nth term of the fibonacci sequence (0 <= n <= 1000000)")
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
        

    @commands.slash_command(
        description="Toggle annoying grammar suggestions", guild_id=GUILD_IDS
    )
    async def grammar(self, ctx):
        grammarlist = await get_data("grammar")
        if ctx.user.id in grammarlist:
            grammarlist.remove(ctx.user.id)
            await ctx.respond("You will no longer receive grammar suggestions. :(")
        else:
            grammarlist.append(ctx.user.id)
            await ctx.respond("Time to fix your grammar! >:)")
        await update_data("grammar", grammarlist)

    @commands.slash_command(description="Benjamin Gong only!", guild_ids=GUILD_IDS)
    @commands.is_owner()
    @option("user", discord.Member, description="User to mute")
    async def mute(self, ctx, user):
        mute_list = await get_data("mute")
        if user.id in mute_list:
            await ctx.respond("This person is already muted", ephemeral=True)
        else:
            mute_list.append(user.id)
            await update_data("mute", mute_list)

            await ctx.respond("Muted", ephemeral=True)

    @mute.error
    async def mute_error(self, ctx, error):
        await throw_error(ctx, error)

    @commands.slash_command(description="Benjamin Gong only!", guild_ids=GUILD_IDS)
    @commands.is_owner()
    @option("user", discord.Member, description="User to unmute")
    async def unmute(self, ctx, user):
        mute_list = await get_data("mute")
        if user.id in mute_list:
            mute_list.remove(user.id)
            await update_data("mute", mute_list)
            await ctx.respond("Unmuted", ephemeral=True)
        else:
            await ctx.respond("This person is not muted", ephemeral=True)

    @unmute.error
    async def unmute_error(self, ctx, error):
        await throw_error(ctx, error)

    @commands.slash_command(description="Make a custom poll", guild_ids=GUILD_IDS)
    @option("question", str, description="Question to ask")
    @option(
        "options",
        str,
        description="Type your options here. Seperate the options with a comma and space (ex: yes, no, maybe)",
    )
    async def poll(self, ctx, question, options):
        olist = options.split(", ")
        desc = ""
        for i in range(len(olist)):
            if i == 0:
                emoji = "1️⃣"
            elif i == 1:
                emoji = "2️⃣"
            elif i == 2:
                emoji = "3️⃣"
            elif i == 3:
                emoji = "4️⃣"
            elif i == 4:
                emoji = "5️⃣"
            elif i == 5:
                emoji = "6️⃣"
            elif i == 6:
                emoji = "7️⃣"
            elif i == 7:
                emoji = "8️⃣"
            else:
                emoji = "9️⃣"
            desc = desc + emoji + ": " + olist[i] + "\n"
        embed = discord.Embed(title=question, description=desc)
        message = await ctx.respond(embed=embed)
        msg = await message.original_response()
        for i in range(len(olist)):
            if i == 0:
                emoji = "1️⃣"
            elif i == 1:
                emoji = "2️⃣"
            elif i == 2:
                emoji = "3️⃣"
            elif i == 3:
                emoji = "4️⃣"
            elif i == 4:
                emoji = "5️⃣"
            elif i == 5:
                emoji = "6️⃣"
            elif i == 6:
                emoji = "7️⃣"
            elif i == 7:
                emoji = "8️⃣"
            else:
                emoji = "9️⃣"
            await msg.add_reaction(emoji)

    ar = discord.SlashCommandGroup("ar", "Group of autoresponse commands")

    @ar.command(description="Create autorespond triggers", guild_ids=GUILD_IDS)
    @option("needle", str, description="Phrase to autorespond to")
    @option("answer", str, description="Message to respond")
    async def create(self, ctx, needle, answer):
        message_list = await get_data("autorespond")
        respond_config = {"needle": needle, "message": answer}
        message_list.append(respond_config)
        await update_data("autorespond", message_list)
        await ctx.respond("Autoresponse created")

    @ar.command(description="Edit autoresponse triggers", guild_ids=GUILD_IDS)
    @option("index", int, description="Autoresponse trigger to edit")
    @option("answer", str, description="Message to change to")
    async def edit(self, ctx, index, answer):
        message_list = await get_data("autorespond")
        message_list[index]["message"] = answer
        await update_data("autorespond", message_list)
        await ctx.respond("Autoresponse edited")

    @ar.command(description="Delete autoresponse triggers", guild_ids=GUILD_IDS)
    @option("index", int, description="Autoresponse trigger to delete")
    async def delete(self, ctx, index):
        message_list = await get_data("autorespond")
        message_list.pop(index)
        await update_data("autorespond", message_list)
        await ctx.respond("Autoresponse deleted")

    @ar.command(description="Show autoresponse triggers", guild_ids=GUILD_IDS)
    async def show(self, ctx):
        message_list = await get_data("autorespond")
        result = (
            "This is the configuration. Use the index at the front to edit and delete"
        )
        code = "```"
        for index, item in enumerate(message_list):
            code += f'{index}: {item["needle"]} -> {item["message"]} \n'
        code += "```"
        result += code
        await update_data("autorespond", message_list)
        await ctx.respond(result)

    @commands.slash_command(
        name="ping", description="See if the bot is up", guild_ids=GUILD_IDS
    )  # ping command
    async def ping(self, ctx):
        await ctx.respond(f"Your latency is {round(self.bot.latency * 1000)} ms")


def setup(bot):
    bot.add_cog(Misc(bot))
