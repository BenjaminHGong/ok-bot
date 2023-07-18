import asyncio
import os
import random
from pathlib import Path

import discord
import nest_asyncio
from discord import option
from discord.ext import commands, tasks
from dotenv import load_dotenv

dotenv_path = Path(r"C:\Users\singi\Desktop\.env")
load_dotenv(dotenv_path=dotenv_path)
nest_asyncio.apply()
GUILD_IDS = [1024196422637195315, 1099937674200105030]
owner_ids = [755525460267630612]
TOKEN = os.getenv("DISCORD_TOKEN")

bot = discord.Bot(sync_commands=True, intents=discord.Intents.all())


async def load_extensions():
    for filename in os.listdir("cogs"):
        if filename.endswith(".py"):
            bot.load_extension(f"cogs.{filename[:-3]}")


@bot.event
async def on_ready():
    change_status.start()
    print(f"{bot.user} has connected to Discord!")


async def main():
    await load_extensions()
    await bot.run(TOKEN)


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


async def throw_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.respond("You don't have permission!", ephemeral=True)
    else:
        raise error


@bot.slash_command(description="Check if a cog is loaded", guild_ids=GUILD_IDS)
@commands.is_owner()
@option("extension", str, description="Extension to check (ex. 'test' for test.py)")
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


@check.error
async def check_error(ctx, error):
    throw_error(ctx, error)


@bot.slash_command(
    description="Load Ok Bot commands", guild_ids=GUILD_IDS
)  # load command
@commands.is_owner()
@option("extension", str, description="Extension to load (ex. 'test' for test.py)")
async def load(ctx, extension):
    try:
        bot.load_extension(f"cogs.{extension}")
        desc = f"{extension} successfully loaded"
    except discord.ExtensionNotFound:
        desc = f"{extension} not found"

    embed = discord.Embed(title="Load", description=desc, color=0xFF00C8)
    await ctx.respond(embed=embed, ephemeral=True)


@load.error
async def load_error(ctx, error):
    throw_error(ctx, error)


@bot.slash_command(
    description="Unload Ok Bot commands", guild_ids=GUILD_IDS
)  # unload command
@commands.is_owner()
@option("extension", str, description="Extension to unload (ex. 'test' for test.py)")
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


@unload.error
async def unload_error(ctx, error):
    throw_error(ctx, error)


@bot.slash_command(
    description="Reload Ok Bot commands", guild_ids=GUILD_IDS
)  # reload command
@commands.is_owner()
@option("extension", str, description="Extension to reload (ex. 'test' for test.py)")
async def reload(ctx, extension):
    try:
        bot.reload_extension(f"cogs.{extension}")
        desc = f"{extension} successfully reloaded"
    except discord.ExtensionNotLoaded:
        desc = f"{extension} is not loaded"

    embed = discord.Embed(title="Reload", description=desc, color=0xFF00C8)
    await ctx.respond(embed=embed, ephemeral=True)


@reload.error
async def reload_error(ctx, error):
    throw_error(ctx, error)


if __name__ == "__main__":
    asyncio.run(main())
