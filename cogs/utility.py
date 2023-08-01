from math import ceil

import discord
from discord import option
from discord.ext import commands

from jsonedit import get_data, update_data
from main import throw_error

GUILD_IDS = [1024196422637195315, 1099937674200105030]
owner_ids = [755525460267630612]


class PaginationView(discord.ui.View):
    current_page: int = 1
    sep: int = 5

    async def send(self, ctx):
        self.message = await ctx.send(view=self)
        await self.update_message(self.data[: self.sep])

    def create_embed(self, data):
        embed = discord.Embed(title="Autoresponse Triggers")
        for key, value in data:
            embed.add_field(name=key, value=value, inline=False)
        return embed

    async def update_message(self, data):
        self.update_buttons()
        await self.message.edit(embed=self.create_embed(data), view=self)

    def update_buttons(self):
        if self.current_page == 1:
            self.first_page_button.disabled = True
            self.prev_button.disabled = True
        else:
            self.first_page_button.disabled = False
            self.prev_button.disabled = False

        if self.current_page == ceil(len(self.data) / self.sep):
            self.last_page_button.disabled = True
            self.next_button.disabled = True
        else:
            self.last_page_button.disabled = False
            self.next_button.disabled = False

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="⏮️")
    async def first_page_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.response.defer()
        self.current_page = 1
        until_item = self.current_page * self.sep
        await self.update_message(self.data[:until_item])

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="◀️")
    async def prev_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.response.defer()
        self.current_page -= 1
        until_item = self.current_page * self.sep
        from_item = until_item - self.sep
        await self.update_message(self.data[from_item:until_item])

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="▶️")
    async def next_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.response.defer()
        self.current_page += 1
        until_item = self.current_page * self.sep
        from_item = until_item - self.sep
        await self.update_message(self.data[from_item:until_item])

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="⏭️")
    async def last_page_button(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        await interaction.response.defer()
        self.current_page = ceil(len(self.data) / self.sep)
        until_item = self.current_page * self.sep
        from_item = until_item - self.sep
        await self.update_message(self.data[from_item:])


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = commands.Bot = bot

    @commands.Cog.listener()
    async def on_connect(self):
        print("Utility commands loaded")

    @commands.Cog.listener()
    async def on_message(self, message):
        mute_list = await get_data("mute")
        if message.author.id in mute_list:
            await message.delete()
            await message.author.send("You are muted")

        if not message.author.bot:
            message_list = await get_data("autorespond")
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
        else:
            bot_whitelist = await get_data("botwhitelist")
            channel_whitelist = await get_data("channelwhitelist")
            if (
                message.author.id not in bot_whitelist
                and message.channel.id not in channel_whitelist
            ):
                await message.delete()
                await message.channel.send("<#1034679492586778674>")

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
        data = []
        for index, item in enumerate(message_list):
            data.append((f'{index}: {item["needle"]}', f'{item["message"]}'))
        pagination_view = PaginationView()
        pagination_view.data = data
        await ctx.respond(
            "Use the index above each autoresponse to edit and delete"
        )
        await pagination_view.send(ctx)

    @commands.slash_command(
        name="ping", description="See if the bot is up", guild_ids=GUILD_IDS
    )
    async def ping(self, ctx):
        await ctx.respond(f"Your latency is {round(self.bot.latency * 1000)} ms")


def setup(bot):
    bot.add_cog(Utility(bot))
