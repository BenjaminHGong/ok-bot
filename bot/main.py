import arrow
import asyncio
import discord
import json
import nest_asyncio
import os
import random
import subprocess
import sys
from cogs.utility import PaginationView
from discord import option
from discord.ext import commands, tasks
from discord.utils import basic_autocomplete
from dotenv import load_dotenv
from pathlib import Path
from utils import update_data


def load_credentials(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


load_dotenv(Path(r".env"))
TOKEN = os.environ.get("DISCORD_TOKEN")
nest_asyncio.apply()
log_file = "output.log"
log = open(log_file, "a")
GUILD_IDS = []


class CustomStream:
    def __init__(self, log_file):
        self.log_file = log_file
        self.should_write_timestamp = True  # Flag to control timestamp writing

    def write(self, text):
        if self.should_write_timestamp:
            timestamp = arrow.utcnow().to("US/Pacific").format("YYYY-MM-DD HH:mm:ss")
            self.log_file.write(f"[{timestamp}] ")
        self.log_file.write(text)
        self.log_file.flush()
        if "\n" in text:
            self.should_write_timestamp = True  # Reset the flag after a newline
        else:
            self.should_write_timestamp = (
                False  # Do not write timestamp for the next line
            )

    def flush(self):
        sys.__stdout__.flush()


sys.stdout = CustomStream(log)
bot = commands.Bot(
    command_prefix="!", sync_commands=True, intents=discord.Intents.all()
)
GUILD_IDS = []
extensions_list = []
for filename in os.listdir("bot\cogs"):
    if filename.endswith(".py"):
        extensions_list.append(filename[:-3])


async def load_extensions():
    for filename in extensions_list:
        bot.load_extension(f"cogs.{filename}")


async def main():
    await load_extensions()
    await bot.run(TOKEN)


@bot.event
async def on_ready():
    global GUILD_IDS
    GUILD_IDS = [guild.id for guild in bot.guilds]
    await update_data("guilds", GUILD_IDS)
    change_status.start()
    print(f"{bot.user} has connected to Discord!")


@bot.event
async def on_application_command_error(ctx, error):
    if isinstance(error, commands.errors.NotOwner):
        await ctx.respond("This command is reserved for the bot owner.", ephemeral=True)
    elif isinstance(error, commands.errors.MissingPermissions):
        await ctx.respond(
            "You don't have permission to use this command.", ephemeral=True
        )
    else:
        raise error


@tasks.loop(seconds=3600)  # status changing
async def change_status():
    status = [
        "Among Us",
        "Brawl Stars",
        "PvZ Heroes",
        "Geometry Dash",
        "Destiny 2",
        "Gomoku",
        "Chess",
        "Bomb Party",
        "Minecraft",
        "Real Life",
        "Muck",
        "Jackbox",
    ]
    await bot.change_presence(activity=discord.Game(random.choice(status)))


@bot.slash_command(
    description="Show a list of all available commands", guild_ids=GUILD_IDS
)
async def help(ctx):
    commands_data = []
    for cog in bot.cogs.values():
        for command in cog.get_commands():
            commands_data.append(
                (f"/{command.name}", command.description or "No description available")
            )
    commands_data = sorted(commands_data)
    view = PaginationView(data=commands_data, title="Commands", color=0x57F287)
    await ctx.respond(
        f"Ok Bot is an all-purpose bot created by Benjamin Gong, with over {len(commands_data)} commands and counting."
    )
    await view.send(ctx)


@bot.slash_command(description="Benjamin Gong only!", guild_ids=GUILD_IDS)
@commands.is_owner()
async def restart(ctx):
    await ctx.respond("Restarting...", ephemeral=True)
    subprocess.Popen(["pythonw", "bot/main.py"])
    os._exit(0)


cog = bot.create_group("cog", "Group of cog commands")


@cog.command(description="Check if a cog is loaded", guild_ids=GUILD_IDS)
@commands.is_owner()
@option(
    "extension",
    str,
    description="Extension to check (ex. 'test' for test.py)",
    autocomplete=basic_autocomplete(extensions_list),
)
async def check(ctx, extension):
    try:
        bot.load_extension(f"cogs.{extension}")
    except discord.ExtensionAlreadyLoaded:
        desc = "Cog is loaded"
    except discord.ExtensionNotFound:
        desc = "Cog not found"
    else:
        desc = "Cog is unloaded"
        bot.unload_extension(f"cogs.{extension}")
    embed = discord.Embed(title="Check", description=desc, color=0xFF00C8)
    await ctx.respond(embed=embed, ephemeral=True)


@cog.command(description="Load a cog", guild_ids=GUILD_IDS)  # load command
@commands.is_owner()
@option(
    "extension",
    str,
    description="Extension to load (ex. 'test' for test.py)",
    autocomplete=basic_autocomplete(extensions_list),
)
async def load(ctx, extension):
    try:
        bot.load_extension(f"cogs.{extension}")
        desc = f"{extension} successfully loaded"
    except discord.ExtensionNotFound:
        desc = f"{extension} not found"
    except discord.ExtensionAlreadyLoaded:
        desc = f"{extension} already loaded"

    embed = discord.Embed(title="Load", description=desc, color=0xFF00C8)
    await ctx.respond(embed=embed, ephemeral=True)


@cog.command(description="Unload a cog", guild_ids=GUILD_IDS)  # unload command
@commands.is_owner()
@option(
    "extension",
    str,
    description="Extension to unload (ex. 'test' for test.py)",
    autocomplete=basic_autocomplete(extensions_list),
)
async def unload(ctx, extension):
    try:
        bot.unload_extension(f"cogs.{extension}")
        desc = f"{extension} successfully unloaded"
    except discord.ExtensionNotLoaded:
        desc = f"{extension} is not loaded"
    except discord.ExtensionNotFound:
        desc = f"{extension} not found"

    embed = discord.Embed(title="Unload", description=desc, color=0xFF00C8)
    await ctx.respond(embed=embed, ephemeral=True)


@cog.command(description="Reload a cog", guild_ids=GUILD_IDS)  # reload command
@commands.is_owner()
@option(
    "extension",
    str,
    description="Extension to reload (ex. 'test' for test.py)",
    autocomplete=basic_autocomplete(extensions_list),
)
async def reload(ctx, extension):
    try:
        bot.reload_extension(f"cogs.{extension}")
        desc = f"{extension} successfully reloaded"
    except discord.ExtensionNotLoaded:
        desc = f"{extension} is not loaded"

    embed = discord.Embed(title="Reload", description=desc, color=0xFF00C8)
    await ctx.respond(embed=embed, ephemeral=True)


if __name__ == "__main__":
    asyncio.run(main())
    log.close()
