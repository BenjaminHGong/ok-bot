import arrow
import asyncio
import discord
import json
import nest_asyncio
import os
import secrets
import subprocess
import sys
import time
import traceback
from cogs.utility import PaginationView
from discord import option
from discord.ext import commands, tasks
from discord.utils import basic_autocomplete
from dotenv import load_dotenv
from pathlib import Path
from utils import update_data, get_data_once


def check_single_instance(lockfile=None):
    if lockfile is None:
        lockfile = Path(__file__).resolve().parent.parent / "bot.lock"

    lock_file = open(lockfile, "w")

    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print("Bot is already running. Stop the existing process before starting a new one.")
            sys.exit(0)
    else:
        import fcntl

        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("Bot is already running. Stop the existing process before starting a new one.")
            sys.exit(0)

    return lock_file


lock = check_single_instance()


def load_credentials(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


load_dotenv(Path(r".env"))
TOKEN = os.environ.get("DISCORD_TOKEN")
nest_asyncio.apply()
log_file = "output.log"
log = open(log_file, "a")
try:
    GUILD_IDS = get_data_once("guilds")
except Exception:
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


class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        


bot = MyBot(
    command_prefix="!", sync_commands=True, intents=discord.Intents.all()
)

extensions_list = []
for filename in os.listdir("bot/cogs"):
    if filename.endswith(".py"):
        extensions_list.append(filename[:-3])


def load_extensions():
    for filename in extensions_list:
        bot.load_extension(f"cogs.{filename}")


async def main():
    load_extensions()
    await bot.run(TOKEN)


@bot.event
async def on_ready():
    global GUILD_IDS
    GUILD_IDS = [guild.id for guild in bot.guilds]
    await update_data("guilds", GUILD_IDS)
    if not change_status.is_running():
        change_status.start()

    print(f"{bot.user} has connected to Discord!")
@bot.event
async def on_application_command_error(ctx, error):
    cause = (
        error.__cause__
        if isinstance(error, discord.ApplicationCommandInvokeError)
        else error
    )
    if isinstance(error, commands.errors.NotOwner):
        desc = "This command is reserved for the bot owner."
    elif isinstance(error, commands.errors.MissingPermissions):
        desc = "You don't have permission to use this command."
    elif isinstance(error, commands.errors.CommandOnCooldown):
        desc = f"Slow down. Try again <t:{int(time.time() + error.retry_after)}:R>."
    else:
        print(
            "".join(
                traceback.format_exception(type(cause), cause, cause.__traceback__)
            )
        )
        desc = f"Something went wrong: {type(cause).__name__}: {cause}"

    try:
        await ctx.respond(desc, ephemeral=True)
    except Exception:
        pass


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
        "Mindustry",
        "Minecraft",
        "Real Life",
        "Muck",
        "Jackbox",
        "Satisfactory",
        "Land.io",
        "Meccha Chameleon",
        "Bopl Battle",
        "Factorio",
        "Peak",
        "Civ VI",
        "Deep Rock Galactic",
        "Slay the Spire 2",
    ]
    await bot.change_presence(activity=discord.Game(secrets.choice(status)))


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
    main_path = str(Path(__file__).resolve())
    root_dir = str(Path(__file__).resolve().parent.parent)
    # Release the single-instance lock BEFORE spawning the new process, otherwise
    # the fresh instance races this one for the lock and can exit with "Bot is
    # already running". os.execv is unreliable on Windows (can raise OSError and
    # never restart), so spawn a new process and exit instead.
    try:
        lock.close()
    except Exception:
        pass
    subprocess.Popen([sys.executable, main_path], cwd=root_dir)
    os._exit(0)


cog = bot.create_group("cog", "Group of cog commands", guild_ids=GUILD_IDS)


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
    except Exception as e:
        desc = f"Failed to load {extension}:\n{type(e).__name__}: {e}"
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
    except Exception as e:
        desc = f"Failed to load {extension}:\n{type(e).__name__}: {e}"

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
    except Exception as e:
        desc = f"Failed to unload {extension}:\n{type(e).__name__}: {e}"

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
        color = 0x00FF00
        try:
            await bot.sync_commands()
        except Exception:
            pass
    except discord.ExtensionNotLoaded:
        desc = f"{extension} is not loaded"
        color = 0xFF0000
    except discord.ExtensionNotFound:
        desc = f"{extension} not found"
        color = 0xFF0000
    except (discord.ExtensionFailed, discord.NoEntryPointError, SyntaxError, ImportError) as e:
        desc = f"Failed to reload {extension}:\n{type(e).__name__}: {e}"
        color = 0xFF0000
    except Exception as e:
        print(
            "".join(traceback.format_exception(type(e), e, e.__traceback__))
        )
        desc = f"Failed to reload {extension}:\n{type(e).__name__}: {e}"
        color = 0xFF0000

    embed = discord.Embed(title="Reload", description=desc, color=color)
    try:
        await ctx.respond(embed=embed, ephemeral=True)
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
    log.close()
