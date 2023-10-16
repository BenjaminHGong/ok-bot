import asyncio
import arrow
import dateparser
from math import ceil

import discord
from discord import option
from discord.ext import commands, tasks
from utils import get_data, update_data

GUILD_IDS = [1024196422637195315, 1099937674200105030]
owner_ids = [755525460267630612]


class PaginationView(discord.ui.View):
    def __init__(self, data, title, color=None):
        super().__init__()
        self.data = data
        self.title = title
        self.color = color
        self.current_page = 1
        self.sep = 5

    async def send(self, ctx):
        self.message = await ctx.send(view=self)
        await self.update_message(self.data[: self.sep])

    def create_embed(self, data):
        embed = discord.Embed(title=self.title, color=self.color)
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
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    @tasks.loop(seconds=1)
    async def check_reminders(self):
        all_reminders = await get_data("reminders")
        current_time = arrow.utcnow().to('US/Pacific')
        for user_id, reminders in all_reminders.items():
            reminders_to_remove = list()
            for reminder in reminders:
                reminder_time = arrow.get(reminder["time"]).replace(tzinfo='US/Pacific')
                if reminder_time <= current_time:
                    destination_channel = self.bot.get_channel(reminder["channel"])
                    if destination_channel:
                        await destination_channel.send(
                            f"{reminder['message']}||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​|| _ _ _ _ _ _ <@{user_id}>)"
                        )
                    else:
                        user = self.bot.get_user(int(user_id))
                        if user:
                            await user.send(
                                f"{reminder['message']}||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​|| _ _ _ _ _ _ <@{user_id}>)"
                            )
                    reminders_to_remove.append(reminder)
            for item in reminders_to_remove:
                reminders.remove(item)
        await update_data("reminders", all_reminders)

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
                for respond_config in message_list[str(message.guild.id)]:
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
            if message.guild:
                guild = message.guild
                webhook_ids = []
                for item in await guild.webhooks():
                    webhook_ids.append(int(str(item)[12:31]))
            if (
                message.author.id not in bot_whitelist
                and message.author.id not in webhook_ids
                and message.channel.id not in channel_whitelist
            ):
                await message.delete()
                await message.channel.send("<#1034679492586778674>")

    reminder = discord.SlashCommandGroup("reminder", "Create, edit and delete reminders")

    @reminder.command(
        description="Edit a specific reminder's message", guild_ids=GUILD_IDS
    )
    @option("index", int, description="Index to edit")
    @option("message", str, description="New message")
    async def edit(self, ctx, index, message):
        all_reminders = await get_data("reminders")
        user_id = str(ctx.author.id)
        if user_id in all_reminders:
            reminders = all_reminders[user_id]
            if 0 < index <= len(reminders):
                reminders[index - 1]["message"] = message
                await update_data("reminders", all_reminders)
                await ctx.respond(f"Reminder at index {index} edited successfully.")
            else:
                await ctx.respond("Invalid reminder index.")
        else:
            await ctx.respond("You have no reminders.")

    @reminder.command(
        description="Delete a specific reminder by index", guild_ids=GUILD_IDS
    )
    @option("index", int, description="Index to delete")
    async def delete(self, ctx, index: int):
        all_reminders = await get_data("reminders")
        user_id = str(ctx.author.id)

        if user_id in all_reminders:
            reminders = all_reminders[user_id]
            if index < 1 or index > len(reminders):
                await ctx.respond("Invalid reminder index. Please provide a valid index.")
                return

            # Remove the reminder at the given index.
            deleted_reminder = reminders.pop(index - 1)

            # Update the data in the storage.
            await update_data("reminders", all_reminders)

            # Format the deleted reminder information.
            deleted_time = arrow.get(deleted_reminder["time"]).format("MMMM DD, YYYY - h:mm A")
            deleted_message = discord.utils.escape_mentions(deleted_reminder["message"])

            # Send a response to confirm deletion.
            confirmation_message = (
                f"Deleted reminder at index {index}:\n"
                f"Time: {deleted_time}\n"
                f"Message: {deleted_message}"
            )
            await ctx.respond(confirmation_message)
        else:
            await ctx.respond("You have no reminders.")

    @reminder.command(
        description="See reminders that are currently active", guild_ids=GUILD_IDS
    )
    async def show(self, ctx):
        all_reminders = await get_data("reminders")
        user_id = str(ctx.author.id)

        if user_id in all_reminders:
            reminders = all_reminders[user_id]
            if reminders:
                reminders_list = [
                    (
                        f"{index + 1}: {arrow.get(reminder['time']).format('MMMM DD, YYYY - h:mm A')}",
                        reminder["message"],
                    )
                    for index, reminder in enumerate(reminders)
                ]
                pagination_view = PaginationView(
                    data=reminders_list, title="List of Reminders", color=0x3498DB
                )
                await ctx.respond("Use the index above each message to delete")
                await pagination_view.send(ctx)
            else:
                await ctx.respond("You have no reminders.")
        else:
            await ctx.respond("You have no reminders.")

    @reminder.command(
        description="Let Ok Bot remind you to do something!", guild_ids=GUILD_IDS
    )
    @option("message", str, description="Message to remind you")
    @option("datetime_input", str, description="Date and time")
    @option("channel", discord.TextChannel, description="Channel to send in")
    async def add(self, ctx, message, channel=None):
        channel_id = channel.id if channel else ctx.channel.id
        await ctx.respond("Please enter the date and time for the reminder (e.g., 'tomorrow at 3pm').")

        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel
        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60)  # Wait for user's response
            datetime_input = msg.content
            
            parsed_datetime = dateparser.parse(datetime_input, settings={'TIMEZONE': 'US/Pacific'})
            
            if parsed_datetime is None:
                await ctx.send("Please enter a valid date and time.")
                return
            
            reminders = await get_data("reminders")
            reminder = {"message": message, "time": parsed_datetime.isoformat(), "channel": channel_id}
            user_id = str(ctx.user.id)
            
            if user_id not in reminders:
                reminders[user_id] = []
            
            reminders[user_id].append(reminder)
            reminders[user_id] = sorted(
                reminders[user_id], key=lambda x: arrow.get(x["time"]).datetime
            )
            
            await update_data("reminders", reminders)
            formatted_date = parsed_datetime.strftime("%B %d, %Y")
            formatted_time = parsed_datetime.strftime("%I:%M %p")
            await ctx.send(f"Reminder added for {formatted_date} at {formatted_time}.")
        except asyncio.TimeoutError:
            await ctx.send("You took too long to provide a date and time. The reminder setup has been cancelled.")
        except ValueError:
            await ctx.send("Please enter a valid date and time.")


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

    ar = discord.SlashCommandGroup("ar", "Automatically respond to specific keywords")

    @commands.has_permissions(manage_messages=True)
    @ar.command(description="Create autorespond triggers", guild_ids=GUILD_IDS)
    @option("needle", str, description="Phrase to autorespond to")
    @option("answer", str, description="Message to respond")
    async def create(self, ctx, needle, answer):
        message_list = await get_data("autorespond")
        respond_config = {"needle": needle, "message": answer}
        try:
            message_list[str(ctx.guild.id)].append(respond_config)
            await update_data("autorespond", message_list)
            await ctx.respond("Autoresponse created")
        except KeyError:
            message_list[str(ctx.guild.id)] = []
            message_list[str(ctx.guild.id)].append(respond_config)
            await update_data("autorespond", message_list)
            await ctx.respond("Autoresponse created")

    @commands.has_permissions(manage_messages=True)
    @ar.command(description="Edit autoresponse triggers", guild_ids=GUILD_IDS)
    @option("index", int, description="Autoresponse trigger to edit")
    @option("answer", str, description="Message to change to")
    async def edit(self, ctx, index, answer):
        message_list = await get_data("autorespond")
        message_list[str(ctx.guild.id)][index]["message"] = answer
        if index < 1 or index > len(message_list[str(ctx.guild.id)]):
            await ctx.respond(
                "Invalid autoresponse index. Please provide a valid index."
            )
            return
        await update_data("autorespond", message_list)
        await ctx.respond("Autoresponse edited")

    @commands.has_permissions(manage_messages=True)
    @ar.command(description="Delete autoresponse triggers", guild_ids=GUILD_IDS)
    @option("index", int, description="Autoresponse trigger to delete")
    async def delete(self, ctx, index):
        message_list = await get_data("autorespond")
        if index < 1 or index > len(message_list[str(ctx.guild.id)]):
            await ctx.respond(
                "Invalid autoresponse index. Please provide a valid index."
            )
            return
        message_list[str(ctx.guild.id)].pop(index - 1)
        await update_data("autorespond", message_list)
        await ctx.respond("Autoresponse deleted")

    @ar.command(description="Show autoresponse triggers", guild_ids=GUILD_IDS)
    async def show(self, ctx):
        try:
            message_list = await get_data("autorespond")
            data = []
            if message_list[str(ctx.guild.id)] == []:
                raise KeyError
            for index, item in enumerate(message_list[str(ctx.guild.id)]):
                data.append((f'{index + 1}: {item["needle"]}', f'{item["message"]}'))
            pagination_view = PaginationView(
                data=data, title="Autoresponse Triggers", color=0xFFA500
            )
            await ctx.respond(
                "Use the index above each autoresponse to edit and delete"
            )
            await pagination_view.send(ctx)
        except KeyError:
            await ctx.respond("You have no autoresponse triggers!")

    @commands.slash_command(
        name="ping", description="See if the bot is up", guild_ids=GUILD_IDS
    )
    async def ping(self, ctx):
        await ctx.respond(f"Your latency is {round(self.bot.latency * 1000)} ms")


def setup(bot):
    bot.add_cog(Utility(bot))
