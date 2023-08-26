import json

from discord.ext import commands


def get_data_once(name):
    with open(f"data/{name}.json", "r") as f:
        data = json.load(f)
    return data


async def get_data(name):
    with open(f"data/{name}.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


async def update_data(name, list):
    with open(f"data/{name}.json", "w") as f:
        json.dump(list, f)


async def throw_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.respond("This command is reserved for the bot owner.", ephemeral=True)
    elif isinstance(error, commands.CheckFailure):
        await ctx.respond("You don't have permission to use this command.", ephemeral=True)
    else:
        raise error
