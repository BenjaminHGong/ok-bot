import asyncio
import os
import random
import subprocess
from pathlib import Path

import discord
import nest_asyncio
from cogs.utility import PaginationView
from discord import option
from discord.ext import commands, tasks
from discord.utils import basic_autocomplete
from dotenv import load_dotenv

dotenv_path = Path(r"C:\Users\singi\Desktop\.env")
load_dotenv(dotenv_path=dotenv_path)
nest_asyncio.apply()
GUILD_IDS = [1024196422637195315, 1099937674200105030]
owner_ids = [755525460267630612]
TOKEN = os.getenv("DISCORD_TOKEN")

bot = commands.Bot(
    command_prefix="!", sync_commands=True, intents=discord.Intents.all()
)

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


async def throw_error(ctx, error):
    if isinstance(error, commands.errors.NotOwner):
        await ctx.respond("This command is reserved for the bot owner.", ephemeral=True)
    elif isinstance(error, commands.errors.MissingPermissions):
        await ctx.respond(
            "You don't have permission to use this command.", ephemeral=True
        )
    else:
        raise error


@bot.event
async def on_ready():
    change_status.start()
    print(f"{bot.user} has connected to Discord!")


@bot.event
async def on_application_command_error(ctx, error):
    await throw_error(ctx, error)


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
    subprocess.Popen(["python", "bot/main.py"])
    exit()


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
