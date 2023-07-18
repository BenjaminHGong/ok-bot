import discord
from discord import option
from discord.ext import commands
from discord.utils import basic_autocomplete

from jsonedit import get_data, get_data_once

GUILD_IDS = [1024196422637195315, 1099937674200105030]


class Brawlstars(commands.Cog):
    def __init__(self, bot):
        self.bot = commands.Bot = bot

    maplist_names = []
    maps = get_data_once("maps")
    for map in maps:
        maplist_names.append(map)
    maplist_names = sorted(maplist_names)

    brawler_names = []
    brawlers = get_data_once("brawlers")
    for name in brawlers:
        brawler_names.append(name)
    brawler_names = sorted(brawler_names)

    @commands.Cog.listener()
    async def on_connect(self):
        print("Brawl Stars commands loaded")

    @commands.slash_command(
        description="Look up the counters of brawlers!!!", guild_ids=GUILD_IDS
    )  # ct command
    @option(
        "brawler",
        str,
        description="Brawler to search up",
        autocomplete=basic_autocomplete(brawler_names),
    )
    async def ct(self, ctx, brawler):
        found = False
        brawlers = await get_data("brawlers")
        for name in brawlers:
            if brawler.lower() == name.lower():
                counters = brawlers[str(name)]["counters"]
                await ctx.respond(f"{name}: {counters}")
                found = True
                break
        if found is False:
            await ctx.respond("Brawler not found", ephemeral=True)

    @commands.slash_command(
        description="Get detailed info on drafting on any Power League map",
        guild_ids=GUILD_IDS,
    )  # map command
    @option(
        "map",
        str,
        description="Map to search up",
        autocomplete=basic_autocomplete(maplist_names),
    )
    async def map(self, ctx, map):
        try:
            pic = open(f"maps\{map.lower()}.png", "rb")
            picture = discord.File(pic)
            await ctx.respond(file=picture)
        except FileNotFoundError:
            await ctx.respond("Map not found")


def setup(bot):
    bot.add_cog(Brawlstars(bot))
