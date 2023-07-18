import json
import math
import random
from operator import itemgetter

import discord
from discord import option
from discord.ext import commands

from lists import mainshop

GUILD_IDS = [1024196422637195315, 1099937674200105030]
BANK = "data/bank.json"
ERROR_1 = "That object isn't there!"
ERROR_2 = "Please specify a positive amount"


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = commands.Bot = bot

    @commands.Cog.listener()
    async def on_connect(self):
        print("Economy commands loaded")

    async def get_mainshop(self, ctx: discord.AutocompleteContext):
        items = []
        for item in mainshop:
            items.append(item["name"])
        return items

    @commands.slash_command(
        description="Check anyone's Ok Bot balance"
    )  # balance command
    @option("member", discord.Member, description="Person to check for balance")
    async def bal(self, ctx, member=None):
        if member is None:
            user = ctx.user
        else:
            user = member

        await self.open_account(user)

        bal = await self.update_bank(user)

        balance_embed = discord.Embed(
            title=f"{user.name}'s Balance",
            description=f"Wallet balance: {bal[0]} \n Bank balance: {bal[1]}",
            color=discord.Color.blue(),
        )

        await ctx.respond(embed=balance_embed)

    @commands.slash_command(description="Beg for free money")  # beg command
    async def beg(self, ctx):
        user = ctx.user
        await self.open_account(user)
        users = await self.get_bank_data()
        money = min(random.randint(1, 1000000) for _ in range(1000))

        chance = random.choice([1, 5])
        if chance == 1:
            users[str(user.id)]["wallet"] += money
            beg_embed = discord.Embed(
                title="SOMEBODY GAVE YOU MONEY!",
                description=f"Somebody gave you {money} coins",
                color=discord.Color.green(),
            )
            await ctx.respond(embed=beg_embed)
        else:
            beg_fail_embed = discord.Embed(
                title="NOBODY GAVE YOU MONEY",
                description="Sorry but looks like nobody gave you money",
                color=discord.Color.red(),
            )
            await ctx.respond(embed=beg_fail_embed)

        with open(BANK, "w") as f:
            json.dump(users, f)

    @commands.slash_command(description="Rob someone")  # rob command
    @option("member", discord.Member, description="Discord member to rob")
    async def rob(self, ctx, member):
        user = member
        user2 = ctx.user
        await self.open_account(user)
        await self.open_account(user2)
        users = await self.get_bank_data()
        user_money = users[str(user.id)]["wallet"]
        user2_money = users[str(user2.id)]["wallet"]

        if user2_money > 5000:
            a = random.randrange(1, 100)
            if user_money > 5000:
                if a > 60:
                    money = random.randrange(0, user_money)
                    await self.update_bank(user2, money * 1, "wallet")
                    await self.update_bank(member, money * -1, "wallet")
                    rob_embed = discord.Embed(
                        title="Robbery Results",
                        description=f"You have stolen {money} coins from <@{user.id}>",
                        color=discord.Color.green(),
                    )
                    await ctx.respond(embed=rob_embed)

                else:
                    money = random.randrange(0, user_money)
                    await self.update_bank(member, money * 1, "wallet")
                    await self.update_bank(user2, money * -1, "wallet")
                    em = discord.Embed(
                        title="Unsuccessful Robbery",
                        description=f"<@{user.id}> caught you robbing. a fine of {money} was paid to <@{user.id}>",
                        color=discord.Color.red(),
                    )
                    await ctx.respond(embed=em)

            else:
                await ctx.respond(
                    f"<@{user.id}> dosent have enough money to get robbed"
                )

        else:
            await ctx.respond(
                "You don't have enough money to rob (wallet money > 5000)"
            )

    @commands.slash_command(
        description="Deposit coins into the bank"
    )  # deposit command
    @option("amount", int, description="Amount of coins to deposit")
    async def deposit(self, ctx, amount):
        user = ctx.user
        await self.open_account(user)
        bal = await self.update_bank(user)

        if amount > bal[0]:
            await ctx.respond("Insufficient funds. Try again.")

        else:
            await self.update_bank(user, amount * 1, "bank")
            await self.update_bank(user, amount * -1, "wallet")

            dep_embed = discord.Embed(
                title="Deposit Successful",
                description=f"{amount} coins have been moved to the bank",
                color=discord.Color.green(),
            )
            await ctx.respond(embed=dep_embed)

    @commands.slash_command(
        description="Withdraw coins from the bank"
    )  # withdraw command
    @option("amount", int, description="Amount of coins to withdraw")
    async def withdraw(self, ctx, amount):
        user = ctx.user
        await self.open_account(user)
        bal = await self.update_bank(user)

        if amount > bal[1]:
            await ctx.respond("Insufficient funds. Try again.")

        else:
            await self.update_bank(user, amount * -1, "bank")
            await self.update_bank(user, amount * 1, "wallet")
            with_embed = discord.Embed(
                title="Withdrawl Successful",
                description=f"{amount} coins have been moved to your wallet",
                color=discord.Color.green(),
            )
            await ctx.respond(embed=with_embed)
            with open(BANK, "r") as f:
                json.load(f)

    async def open_account(self, user):  # open_account function
        users = await self.get_bank_data()

        if str(user.id) in users:
            return False

        else:
            users[str(user.id)] = {}
            users[str(user.id)]["wallet"] = 0
            users[str(user.id)]["bank"] = 0
            users[str(user.id)]["bag"] = []

        with open(BANK, "w") as f:
            json.dump(users, f)

        return True

    async def get_bank_data(self):  # get_bank_data function
        with open(BANK, "r") as f:
            users = json.load(f)
        return users

    async def update_bank(self, user, change=0, mode="wallet"):  # update_bank function
        users = await self.get_bank_data()
        users[str(user.id)][mode] += change

        with open(BANK, "w") as f:
            json.dump(users, f)

        bal = [users[str(user.id)]["wallet"], users[str(user.id)]["bank"]]
        return bal

    @commands.slash_command(
        description="Check out what items you can buy with your coins"
    )  # shop command
    async def shop(self, ctx):
        em = discord.Embed(title="Shop", color=discord.Color.gold())
        for item in mainshop:
            name = item["name"]
            price = item["price"]
            desc = item["description"]
            em.add_field(
                name=name,
                value=f"<:icon_bling:1108989584022437972>**{price}** | {desc}",
            )

        await ctx.respond(embed=em)

    @commands.slash_command(description="Check what items you have")  # bag command
    async def bag(self, ctx):
        await self.open_account(ctx.user)
        user = ctx.user
        users = await self.get_bank_data()

        bag = users[str(user.id)]["bag"]
        em = discord.Embed(title="Bag", color=discord.Color.blue())
        if bag == []:
            em = discord.Embed(
                title="Bag",
                color=discord.Color.blue(),
                description="You have nothing in your bag",
            )

        for item in bag:
            name = item["item"].title()
            amount = item["amount"]

            em.add_field(name=name, value=amount)

        await ctx.respond(embed=em)

    @commands.slash_command(description="Buy something with your coins")  # buy command
    @option("item", str, description="Item to buy", autocomplete=get_mainshop)
    @option("amount", int, description="Amount to buy")
    async def buy(self, ctx, item, amount=1):
        await self.open_account(ctx.user)
        if amount < 1:
            await ctx.respond(ERROR_2)
        else:
            res = await self.buy_this(ctx.user, item, amount)

            if not res[0]:
                if res[1] == 1:
                    await ctx.respond(ERROR_1)
                    return
                if res[1] == 2:
                    await ctx.respond(
                        f"You don't have enough money in your wallet to buy {amount} {item}"
                    )
                    return
            bal = await self.update_bank(ctx.user)
            await ctx.respond(
                f"You just bought {amount} {item} (Wallet balance: {bal[0]})"
            )

    async def buy_this(self, user, item_name, amount):  # buy_this function
        item_name = item_name.lower()
        name_ = None
        for item in mainshop:
            name = item["name"].lower()
            if name == item_name:
                name_ = name
                price = item["price"]
                break

        if name_ is None:
            return [False, 1]

        cost = price * amount

        users = await self.get_bank_data()

        bal = await self.update_bank(user)
        if bal[0] < cost:
            return [False, 2]

        try:
            index = 0
            t = None
            for thing in users[str(user.id)]["bag"]:
                n = thing["item"]
                if n == item_name:
                    old_amt = thing["amount"]
                    new_amt = old_amt + amount
                    users[str(user.id)]["bag"][index]["amount"] = new_amt
                    t = 1
                    break
                index += 1
            if t is None:
                obj = {"item": item_name, "amount": amount}
                users[str(user.id)]["bag"].append(obj)
        except:
            obj = {"item": item_name, "amount": amount}
            users[str(user.id)]["bag"] = [obj]
            raise

        with open(BANK, "w") as f:
            json.dump(users, f)

        await self.update_bank(user, cost * -1, "wallet")

        return [True, "Worked"]

    @commands.slash_command(description="Sell items in your bag")  # sell command
    @option("item", str, description="Item to sell", autocomplete=get_mainshop)
    @option("amount", int, description="Amount to sell")
    async def sell(self, ctx, item, amount=1):
        await self.open_account(ctx.user)
        if amount < 1:
            await ctx.respond(ERROR_2)
        else:
            oldbal = await self.update_bank(ctx.user)
            res = await self.sell_this(ctx.user, item, amount)

            if not res[0]:
                if res[1] == 1:
                    await ctx.respond(ERROR_1)
                    return
                if res[1] == 2:
                    await ctx.respond(f"You don't have {amount} {item} in your bag.")
                    return
                if res[1] == 3:
                    await ctx.respond(f"You don't have {item} in your bag.")
                    return

        bal = await self.update_bank(ctx.user)
        await ctx.respond(
            f"You just sold {amount} {item} and got {bal[0] - oldbal[0]} coins. (Wallet balance: {bal[0]})"
        )

    async def sell_this(
        self, user, item_name, amount, price=None
    ):  # sell_this function
        item_name = item_name.lower()
        name_ = None
        for item in mainshop:
            name = item["name"].lower()
            if name == item_name:
                name_ = name
                if price is None:
                    price = 0.9 * item["price"]
                break

        if name_ is None:
            return [False, 1]

        cost = math.floor(price * amount)

        users = await self.get_bank_data()

        try:
            index = 0
            t = None
            for thing in users[str(user.id)]["bag"]:
                n = thing["item"]
                if n == item_name:
                    old_amt = thing["amount"]
                    new_amt = old_amt - amount
                    if new_amt < 0:
                        return [False, 2]
                    users[str(user.id)]["bag"][index]["amount"] = new_amt
                    t = 1
                    break
                index += 1
            if t is None:
                return [False, 3]
            if users[str(user.id)]["bag"][index]["amount"] == 0:
                users[str(user.id)]["bag"].remove(users[str(user.id)]["bag"][index])

        except:
            return [False, 3]
            raise

        with open(BANK, "w") as f:
            json.dump(users, f)

        await self.update_bank(user, cost, "wallet")

        return [True, "Worked"]

    @commands.slash_command(description="Use something in your bag")  # use command
    @option("item", str, description="Item to use", autocomplete=get_mainshop)
    @option("amount", int, description="Amount to use")
    async def use(self, ctx, item, amount=1):
        await self.open_account(ctx.user)
        if amount < 1:
            await ctx.respond(ERROR_2)
        else:
            res = await self.use_this(ctx.user, item, amount)

            if not res[0]:
                if res[1] == 1:
                    await ctx.respond(ERROR_1)
                    return
                if res[1] == 2:
                    await ctx.respond(f"You don't have {amount} {item} in your bag.")
                    return
                if res[1] == 3:
                    await ctx.respond(f"You don't have {item} in your bag.")
                    return
            for item_ in mainshop:
                if item_["name"] == item:
                    msg = item_["usemsg"]
                    break
            await ctx.respond(f"{msg}")

    async def use_this(self, user, item_name, amount):  # use_this function
        item_name = item_name.lower()
        name_ = None
        for item in mainshop:
            name = item["name"].lower()
            if name == item_name:
                name_ = name
                break

        if name_ is None:
            return [False, 1]

        users = await self.get_bank_data()

        try:
            index = 0
            t = None
            for thing in users[str(user.id)]["bag"]:
                n = thing["item"]
                if n == item_name:
                    old_amt = thing["amount"]
                    new_amt = old_amt - amount
                    if new_amt < 0:
                        return [False, 2]
                    users[str(user.id)]["bag"][index]["amount"] = new_amt
                    t = 1
                    break
                index += 1
            if t is None:
                return [False, 3]
        except:
            return [False, 3]
            raise

        with open(BANK, "w") as f:
            json.dump(users, f)

        return [True, "Worked"]

    @commands.slash_command(
        description="Check out the richest people"
    )  # baltop command
    @option("x", int, description="Display up to the xth richest person")
    async def baltop(self, ctx, x=10):
        users = await self.get_bank_data()
        leader_board = []
        total = []
        for user in users:
            name = int(user)
            leader_board.append(name)
            total_amount = users[user]["wallet"] + users[user]["bank"]
            total.append(total_amount)

        leader_board = list(zip(leader_board, total))
        leader_board = sorted(leader_board, key=itemgetter(1), reverse=True)

        em = discord.Embed(
            title=f"Top {x} Richest People",
            description="This is decided on the basis of raw money in the bank and wallet",
            color=discord.Color(0xFA43EE),
        )
        index = 1
        for id_ in leader_board:
            coins = id_[1]
            member = await self.bot.fetch_user(id_[0])

            em.add_field(name=f"{index}. {member.name}", value=f"{coins}", inline=False)
            if index == x:
                break
            else:
                index += 1

        await ctx.respond(embed=em)

    @commands.slash_command(description="Double or nothing", guild_ids=GUILD_IDS)
    @option("amount", int, description="Amount to gamble (min = 500)")
    async def gamble(self, ctx, amount=500):
        DESC = "Current wallet balance:"

        user = ctx.user
        await self.get_bank_data()
        bal = await self.update_bank(user)
        if amount < 500:
            return await ctx.respond(
                embed=discord.Embed(
                    description="You need to bet at least 500 coins.",
                    color=discord.Color.red(),
                )
            )

        if bal[0] < amount:
            return await ctx.respond(
                embed=discord.Embed(
                    description="You don't have enough money in your wallet.",
                    color=discord.Color.red(),
                )
            )

        userroll = random.randint(0, 100)
        botroll = random.randint(0, 100)

        if userroll > botroll:
            percent = (userroll - botroll) * 5
            winnings = round(amount * (percent / 100))
            bal = await self.update_bank(user, winnings, "wallet")
            embed = discord.Embed(
                title="You Won!",
                description=f"Winnings: {winnings}",
                color=discord.Color.green(),
            )
            embed.add_field(name=f"{user} rolled", value=f"{userroll}", inline=True)
            embed.add_field(
                name=f"{self.bot.user} rolled", value=f"{botroll}", inline=True
            )
            embed.add_field(name=DESC, value=f"{bal[0]}", inline=False)
            return await ctx.respond(embed=embed)

        elif userroll < botroll:
            percent = (botroll - userroll) * 5
            losses = round(amount * (percent / 100) * -1)
            bal = await self.update_bank(user, losses, "wallet")
            embed = discord.Embed(
                title="You Lost...",
                description=f"Losses: {losses}",
                color=discord.Color.red(),
            )
            embed.add_field(name=f"{user} rolled", value=f"{userroll}", inline=True)
            embed.add_field(
                name=f"{self.bot.user} rolled", value=f"{botroll}", inline=True
            )
            embed.add_field(name=DESC, value=f"{bal[0]}", inline=False)
            return await ctx.respond(embed=embed)

        else:
            embed = discord.Embed(title="Draw", color=discord.Color.yellow())
            embed.add_field(name=f"{user} rolled", value=f"{userroll}", inline=True)
            embed.add_field(
                name=f"{self.bot.user} rolled", value=f"{botroll}", inline=True
            )
            embed.add_field(name=DESC, value=f"{bal[0]}", inline=False)


def setup(bot):
    bot.add_cog(Economy(bot))
