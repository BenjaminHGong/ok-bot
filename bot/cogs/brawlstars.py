from fractions import Fraction
from math import floor

import discord
from discord import option
from discord.ext import commands
from discord.utils import basic_autocomplete
from utils import get_data, get_data_once

GUILD_IDS = [1024196422637195315, 1099937674200105030]
dc_r = {
    "Chance": Fraction(1, 2),
    "Power Points": Fraction(85, 215),
    "Coins": Fraction(75, 215),
    "Token Doublers": Fraction(45, 215),
    "Bling": Fraction(5, 215),
    "Credits": Fraction(5, 215),
}
dc_sr = {
    "Chance": Fraction(7, 25),
    "Power Points": Fraction(60, 151),
    "Coins": Fraction(45, 151),
    "Token Doublers": Fraction(37, 151),
    "Bling": Fraction(5, 151),
    "Credits": Fraction(4, 151),
}
dc_e = {
    "Chance": Fraction(3, 20),
    "Power Points": Fraction(90, 227),
    "Coins": Fraction(60, 227),
    "Token Doublers": Fraction(45, 227),
    "Common Pin": Fraction(10, 227),
    "Profile Icon": Fraction(7, 227),
    "Rare Brawler": Fraction(7, 227),
    "Spray": Fraction(5, 227),
    "Super Rare Brawler": Fraction(3, 227),
}
dc_m = {
    "Chance": Fraction(1, 20),
    "Power Points": Fraction(35, 135),
    "Coins": Fraction(25, 135),
    "Common Pin": Fraction(25, 135),
    "Profile Icon": Fraction(14, 135),
    "Rare Pin": Fraction(10, 135),
    "Rare Skin": Fraction(10, 135),
    "Epic Brawler": Fraction(7, 135),
    "Spray": Fraction(2, 135),
    "Super Rare Skin": Fraction(2, 135),
}
dc_l = {
    "Chance": Fraction(1, 50),
    "Gadget": Fraction(35, 116),
    "Star Power": Fraction(30, 116),
    "Epic Pin": Fraction(12, 116),
    "Rare Skin": Fraction(10, 116),
    "Epic Brawler": Fraction(9, 116),
    "Super Rare Skin": Fraction(6, 116),
    "Spray": Fraction(5, 116),
    "Epic Skin": Fraction(4, 116),
    "Mythic Brawler": Fraction(3, 116),
    "Legendary Brawler": Fraction(2, 116),
}


class Brawlstars(commands.Cog):
    def __init__(self, bot):
        self.bot = commands.Bot = bot

    @staticmethod
    def starrdropAutocomplete(self):
        chosen_rarity = self.options["rarity"]
        match chosen_rarity:
            case "Rare":
                return dc_r.keys()
            case "Super Rare":
                return dc_sr.keys()
            case "Epic":
                return dc_e.keys()
            case "Mythic":
                return dc_m.keys()
            case "Legendary":
                return dc_l.keys()
            case None:
                return [
                    "Power Points",
                    "Coins",
                    "Token Doublers",
                    "Bling",
                    "Credits",
                    "Common Pin",
                    "Rare Pin",
                    "Epic Pin",
                    "Rare Skin",
                    "Super Rare Skin",
                    "Epic Skin",
                    "Rare Brawler",
                    "Super Rare Brawler",
                    "Epic Brawler",
                    "Mythic Brawler",
                    "Legendary Brawler",
                    "Spray",
                    "Gadget",
                    "Star Power",
                    "Profile Icon",
                ]

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
        description="See the drop chances of items in Starr Drops", guild_ids=GUILD_IDS
    )
    @option(
        "rarity",
        str,
        description="Rarity of Starr Drop",
        autocomplete=basic_autocomplete(
            ["Rare", "Super Rare", "Epic", "Mythic", "Legendary"]
        ),
    )
    @option(
        "item",
        str,
        description="Chances of the item drop",
        autocomplete=basic_autocomplete(starrdropAutocomplete),
    )
    @option("sf", int, description="Number of significant figures")
    async def drops(self, ctx, rarity=None, item=None, sf=4):
        if rarity and item:
            try:
                indefinite_article = "a"
                if rarity == "Epic":
                    indefinite_article = "an"
                chance = 0
                match rarity:
                    case "Rare":
                        chance = dc_r[item] * dc_r["Chance"]
                    case "Super Rare":
                        chance = dc_sr[item] * dc_sr["Chance"]
                    case "Epic":
                        chance = dc_e[item] * dc_e["Chance"]
                    case "Mythic":
                        chance = dc_m[item] * dc_m["Chance"]
                    case "Legendary":
                        chance = dc_l[item] * dc_l["Chance"]
                item_name = item.lower()
                if item_name[-1] != "s":
                    if item_name[0] in ["a", "e", "i", "o", "u"]:
                        item_name = "an " + item_name
                    else:
                        item_name = "a " + item_name
                k = floor(1 / chance)
                if abs(chance - 1 / k) > abs(chance - 1 / (k + 1)):
                    fraction = f"1/{k}"
                else:
                    fraction = f"1/{k + 1}"
                percentage = f"%.{sf - 2}f" % (float(chance) * 100)
                await ctx.respond(
                    f"The chances of getting {indefinite_article} {rarity} Starr Drop and then getting {item_name} is {percentage}% or around {fraction}."
                )
            except KeyError:
                ctx.respond("Rarity/item not found")
        elif rarity:
            try:
                pic = open(f"starrdrops\{rarity.lower()}.png", "rb")
                picture = discord.File(pic)
                await ctx.respond(file=picture)
            except FileNotFoundError:
                await ctx.respond("Rarity not found")
        elif item:
            try:
                chance = 0
                if item in dc_r:
                    chance += dc_r[item] * dc_r["Chance"]
                if item in dc_sr:
                    chance += dc_sr[item] * dc_sr["Chance"]
                if item in dc_e:
                    chance += dc_e[item] * dc_e["Chance"]
                if item in dc_m:
                    chance += dc_m[item] * dc_m["Chance"]
                if item in dc_l:
                    chance += dc_l[item] * dc_l["Chance"]
                k = floor(1 / chance)
                if abs(chance - 1 / k) < abs(chance - 1 / (k + 1)):
                    fraction = f"1/{k}"
                else:
                    fraction = f"1/{k + 1}"
                percentage = f"%.{sf - 2}f" % (float(chance) * 100)
                item_name = item.lower()
                if item_name[-1] != "s":
                    if item_name[0] in ["a", "e", "i", "o", "u"]:
                        item_name = "an " + item_name
                    else:
                        item_name = "a " + item_name
                await ctx.respond(
                    f"The chances of getting {item_name} overall is {percentage}% or around {fraction}."
                )
            except KeyError:
                ctx.respond("Item not found")
        else:
            await ctx.respond("Please specify a rarity or an item drop.")

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
