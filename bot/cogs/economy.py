import asyncio
import discord
import math
import random
import time
from discord import option
from discord.ext import commands
from lists import mainshop, botshop, DEFAULT_BOT_CONFIG
from operator import itemgetter
from bank_store import load_users, save_users, ensure_ready
from utils import (
    get_data_once,
    load_bot_config,
    save_bot_config,
)

GUILD_IDS = get_data_once("guilds")
ERROR_1 = "That object isn't there!"
ERROR_2 = "Please specify a positive amount"

# Serializes every read-modify-write of the bank store so concurrent commands
# (and the chat reward flow) can't clobber each other's wallet changes. The
# whole get -> mutate -> write sequence must sit inside `async with bank_lock:`.
bank_lock = asyncio.Lock()

PRINTER_RATE = 30000
PRINTER_DAYS = 7
PRINTER_INTERVAL = 86400
VAULT_RATE = 0.05
VAULT_DAYS = 30
VAULT_INTERVAL = 86400
JOB_PAY_MIN = 15000
JOB_PAY_MAX = 40000
JOB_COOLDOWN = 21600
BOUNTY_DURATION = 7 * 86400
STOCK_MIN = 0.3
STOCK_MAX = 3.0

all_shop_items = mainshop + botshop


def get_stock_price(item):
    base = item.get("stock_base", item["price"])
    day = int(time.time() // 86400)
    r = random.Random(f"{item['name']}|{day}")
    return int(base * r.uniform(STOCK_MIN, STOCK_MAX))


def generate_chat_payout() -> int:
    """
    Generates a payout centered around a 1,000 peak,
    with precise tail probabilities matching your target milestones.
    """
    roll = random.random()  # Generates a float between 0.0 and 1.0

    # Milestone 1: 1 Million has a 0.1% chance (Top 0.001 of rolls)
    if roll >= 0.999:
        return 1_000_000

    # Milestone 2: 100k has a 1% overall chance (Next 0.9% of rolls)
    elif roll >= 0.990:
        # Smoothly distribute between 100k and 500k
        return int(random.uniform(100_000, 500_000))

    # Milestone 3: 10k has a 10% overall chance (Next 1.5% of rolls)
    elif roll >= 0.90:
        # Smoothly distribute between 10k and 99k
        return int(random.uniform(10_000, 99_999))

    # The Core Bell Curve: 90% of all chat messages land here
    else:
        # random.gauss(mu, sigma) creates a perfect, natural bell curve.
        # Mu=1000 sets the center, Sigma=250 ensures 99% of these
        # standard rolls stay safely between 250 and 1,750 points.
        standard_payout = random.gauss(1000, 250)
        return max(1, int(standard_payout))


async def read_bank():
    await ensure_ready()
    return await asyncio.to_thread(load_users)


async def write_bank(data):
    await ensure_ready()
    await asyncio.to_thread(save_users, data)


async def add_coins(user_id, amount):
    async with bank_lock:
        users = await read_bank()
        if str(user_id) not in users:
            users[str(user_id)] = {"wallet": 0, "bank": 0, "bag": []}
        users[str(user_id)]["wallet"] = max(0, users[str(user_id)]["wallet"] + amount)
        await write_bank(users)
        return users[str(user_id)]["wallet"]


async def get_wallet(user_id):
    async with bank_lock:
        users = await read_bank()
        data = users.get(str(user_id))
        if not data:
            return 0
        return data.get("wallet", 0)


class BuyView(discord.ui.View):
    def __init__(self, cog, user, item_name, amount):
        super().__init__(timeout=60)
        self.cog = cog
        self.user = user
        self.item_name = item_name
        self.amount = amount
        self.used = False

    @discord.ui.button(
        style=discord.ButtonStyle.success,
        label="Use Now",
        emoji="⚡",
    )
    async def use_now(self, button, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "This isn't your purchase!", ephemeral=True
            )
            return

        self.use_now.disabled = True
        await interaction.response.defer()

        item_meta = await self.cog.find_item(self.item_name)
        if item_meta is None:
            await interaction.followup.send("Item not found.")
            return

        results = []

        if "config" in item_meta:
            config = item_meta["config"]
            if config.get("mode") == "prompt":
                results.append(
                    f"{self.item_name} needs a value — use `/use item:{self.item_name} value:<...>` instead."
                )
            else:
                actual = config.get("value")
                if actual is not None:
                    if config["type"] == "thinking_level" and actual not in (
                        "minimal",
                        "low",
                        "medium",
                        "high",
                    ):
                        results.append(f"Invalid thinking level: {actual}")
                    elif config["type"] == "thinking_summaries" and actual not in (
                        "auto",
                        "none",
                    ):
                        results.append(f"Invalid thinking summaries value: {actual}")
                    elif config["type"] == "tool_choice" and actual not in (
                        "auto",
                        "any",
                        "none",
                        "validated",
                    ):
                        results.append(f"Invalid tool choice: {actual}")
                    else:
                        res = await self.cog.use_this(
                            self.user, self.item_name, 1
                        )
                        if res[0]:
                            botconfig = await load_bot_config()
                            ctype = config["type"]
                            if ctype == "system_instruction":
                                botconfig["system_instruction"] = actual
                            elif ctype == "model":
                                botconfig["model"] = actual
                            elif ctype == "max_output_tokens":
                                botconfig["max_output_tokens"] = int(actual)
                            elif ctype == "thinking_level":
                                botconfig["thinking_level"] = actual
                            elif ctype == "thinking_summaries":
                                botconfig["thinking_summaries"] = actual
                            elif ctype == "tool_choice":
                                botconfig["tool_choice"] = actual
                            elif ctype == "seed":
                                botconfig["seed"] = int(actual)
                            elif ctype == "stop_sequences":
                                botconfig["stop_sequences"] = [
                                    s.strip() for s in actual.split(",") if s.strip()
                                ]
                            await save_bot_config(botconfig)
                            results.append(
                                item_meta.get("usemsg", "Applied.")
                            )
                        else:
                            results.append(
                                f"You don't have {self.item_name} in your bag."
                            )
                else:
                    results.append(
                        f"{self.item_name} needs a value — use `/use item:{self.item_name} value:<...>` instead."
                    )
        elif item_meta.get("effect") == "gift_wrap":
            results.append(
                f"{self.item_name} needs a target — use `/use item:{self.item_name} value:<@user> <item>` instead."
            )
        elif item_meta.get("effect") == "mystery_crate":
            res = await self.cog.use_this(self.user, self.item_name, self.amount)
            if res[0]:
                results.append(
                    await self.cog.bulk_mystery_crate(self.user, self.amount)
                )
            else:
                results.append(f"You don't have {self.amount} {self.item_name} in your bag.")
        elif item_meta.get("effect"):
            for _ in range(self.amount):
                res = await self.cog.use_this(self.user, self.item_name, 1)
                if res[0]:
                    results.append(
                        await self.cog.apply_item_effect(interaction, item_meta, None)
                    )
                else:
                    results.append(f"You don't have {self.item_name} in your bag.")
                    break
        else:
            res = await self.cog.use_this(self.user, self.item_name, self.amount)
            if res[0]:
                results.append(item_meta.get("usemsg") or "Done.")
            else:
                results.append(f"You don't have {self.amount} {self.item_name} in your bag.")

        self.used = True
        await interaction.followup.send("\n".join(results))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if hasattr(self, "message") and self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_connect(self):
        print("Economy commands loaded")

    async def get_shop_items(self, ctx: discord.AutocompleteContext):
        items = []
        for item in all_shop_items:
            items.append(item["name"])
        return items

    @commands.slash_command(
        description="Check anyone's Ok Bot balance", guild_ids=GUILD_IDS
    )  # balance command
    @option("member", discord.Member, description="Person to check for balance")
    async def bal(self, ctx, member=None):
        if member is None:
            user = ctx.user
        else:
            user = member

        await self.open_account(user)

        claim = await self.claim_passive_income(user)

        bal = await self.update_bank(user)

        description = f"Wallet balance: {bal[0]} \n Bank balance: {bal[1]}"
        if claim:
            description += f"\n\n{claim}"

        balance_embed = discord.Embed(
            title=f"{user.name}'s Balance",
            description=description,
            color=discord.Color.blue(),
        )

        await ctx.respond(embed=balance_embed)

    async def claim_passive_income(self, user):
        users = await self.get_bank_data()
        data = users.get(str(user.id))
        if not data:
            return None
        now = time.time()
        changed = False
        lines = []
        if data.get("printer_until", 0) > now:
            if now - data.get("printer_last", 0) >= PRINTER_INTERVAL:
                data["wallet"] = data.get("wallet", 0) + PRINTER_RATE
                data["printer_last"] = now
                changed = True
                lines.append(f"🖨️ Money Printer paid {PRINTER_RATE} coins")
        if data.get("vault_until", 0) > now:
            if now - data.get("vault_last", 0) >= VAULT_INTERVAL:
                interest = int(data.get("bank", 0) * data.get("vault_rate", VAULT_RATE))
                if interest > 0:
                    data["bank"] = data.get("bank", 0) + interest
                    data["vault_last"] = now
                    changed = True
                    lines.append(f"🏦 Interest Vault paid {interest} coins")
        if changed:
            await write_bank(users)
            return " | ".join(lines)
        return None

    @commands.slash_command(description="Beg for free money", guild_ids=GUILD_IDS)  # beg command
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def beg(self, ctx):
        user = ctx.user
        await self.open_account(user)
        await ctx.defer()

        # The bank update is committed BEFORE the reply so a failure can never
        # claim coins the player didn't actually receive, and a concurrent
        # command can't clobber the credit.
        async with bank_lock:
            users = await self.get_bank_data()
            chance = random.choice([1, 2])
            if chance == 1:
                money = generate_chat_payout()
                users[str(user.id)]["wallet"] += money
            await write_bank(users)

        if chance == 1:
            if money >= 1_000_000:
                tier = "jackpot"
            elif money >= 100_000:
                tier = "huge"
            elif money >= 10_000:
                tier = "big"
            else:
                tier = "small"
            description = f"{self._beg_flavor(tier)}\n\n**+{money:,} coins**"
            beg_embed = discord.Embed(
                title="SOMEBODY GAVE YOU MONEY!",
                description=description,
                color=discord.Color.green(),
            )
            await ctx.respond(embed=beg_embed)
        else:
            beg_fail_embed = discord.Embed(
                title="NOBODY GAVE YOU MONEY",
                description=self._beg_flavor("fail"),
                color=discord.Color.red(),
            )
            await ctx.respond(embed=beg_fail_embed)

    @staticmethod
    def _beg_flavor(tier):
        lines = {
            "jackpot": [
                "You hold out your hand for pocket change and a billionaire's armored car pulls up. The window rolls down. Life changes.",
                "A mysterious benefactor walks up, whispers 'pick a number between one and everything', and hands you a wheelbarrow of coins.",
                "You trip, drop your coins, and the universe overcompensates with a fortune. You're not asking questions.",
            ],
            "huge": [
                "A stranger shoves a huge sack of coins into your hands, mumbles 'you need this more than me', and vanishes into a crowd.",
                "You beg politely and a surprisingly generous person just dumps a pile of coins on you. No strings attached.",
                "A delivery truck 'loses' a crate of coins right in front of you. It would be rude not to take it.",
            ],
            "big": [
                "A kind stranger takes pity on you and drops a solid stack of coins into your palm.",
                "Someone overhears your story and hands you a fistful of coins with a 'good luck, champ'.",
                "You get a random act of kindness from a passerby who clearly just won something.",
            ],
            "small": [
                "A stranger fishes some coins out of their pocket and hands them to you. Spare change to them, a feast to you.",
                "You get a few coins from a passerby who looks mildly annoyed but strangely generous.",
                "Someone throws a handful of coins at you like they're feeding a pigeon. You're not proud, but you're fed.",
            ],
            "fail": [
                "You hold out your hand. A stranger makes eye contact, shakes their head, and walks away. Brutal.",
                "You beg with your best puppy eyes. The local cat has a better begging game than you.",
                "Nobody's biting today. You spend your entire charm budget on one guy who turns out to be the landlord.",
                "You ask politely for coins. Someone gives you advice instead. You can't buy bread with advice.",
            ],
        }
        return random.choice(lines[tier])

    @commands.slash_command(
        description="Claim a welfare check when you're flat broke", guild_ids=GUILD_IDS
    )  # welfare command
    async def welfare(self, ctx):
        WELFARE_AMOUNT = 10000
        WELFARE_COOLDOWN = 86400

        user = ctx.user
        await self.open_account(user)
        users = await self.get_bank_data()
        data = users[str(user.id)]
        total = data.get("wallet", 0) + data.get("bank", 0)
        last = data.get("welfare_at", 0)
        now = time.time()

        if total > 0:
            await ctx.respond(
                embed=discord.Embed(
                    title="You're not broke yet",
                    description="Welfare is only for people with 0 coins. Go grind.",
                    color=discord.Color.red(),
                )
            )
            return

        if now - last < WELFARE_COOLDOWN:
            retry_at = int(last + WELFARE_COOLDOWN)
            await ctx.respond(
                embed=discord.Embed(
                    title="Welfare already claimed",
                    description=f"Come back <t:{retry_at}:R>.",
                    color=discord.Color.yellow(),
                )
            )
            return

        data["wallet"] = WELFARE_AMOUNT
        data["welfare_at"] = now
        await write_bank(users)

        await ctx.respond(
            embed=discord.Embed(
                title="Welfare check 💰",
                description=f"Ok Bot spotted you {WELFARE_AMOUNT} coins. Don't spend it all in one place.",
                color=discord.Color.green(),
            )
        )

    @commands.slash_command(description="Rob someone", guild_ids=GUILD_IDS)  # rob command
    @commands.cooldown(1, 5, commands.BucketType.user)
    @option("member", discord.Member, description="Discord member to rob")
    async def rob(self, ctx, member):
        victim = member
        robber = ctx.user

        if robber == victim:
            await ctx.respond("You can't rob yourself!")
            return

        if victim.bot:
            await ctx.respond("You can't rob a bot. Go find a real target.")
            return

        await self.open_account(victim)
        await self.open_account(robber)
        users = await self.get_bank_data()
        victim_wallet = users[str(victim.id)]["wallet"]
        robber_wallet = users[str(robber.id)]["wallet"]

        MIN_WALLET = 5000
        if robber_wallet <= MIN_WALLET:
            await ctx.respond(
                "You don't have enough money to rob (wallet money > 5000)"
            )
            return

        if victim_wallet <= MIN_WALLET:
            await ctx.respond(
                f"<@{victim.id}> doesn't have enough money to get robbed"
            )
            return

        # The heist amount is a slice of the VICTIM's wallet. If the robbery
        # fails, the fine is the same amount; anything the robber can't cover
        # becomes a bounty on their head that other players can collect.
        attempted = int(victim_wallet * random.uniform(0.1, 0.2))

        if random.random() < 0.35:
            users[str(robber.id)]["wallet"] += attempted
            users[str(victim.id)]["wallet"] = max(
                0, users[str(victim.id)]["wallet"] - attempted
            )
            extra = ""
            now = time.time()
            if (
                users[str(victim.id)].get("bounty_amount", 0) > 0
                and users[str(victim.id)].get("bounty_until", 0) > now
            ):
                bounty = users[str(victim.id)]["bounty_amount"]
                # The bounty is a real debt: collecting it garnishes the bounty
                # holder's coins instead of minting coins out of thin air. Take
                # from their wallet first, then their bank. Only what they can
                # cover is collected; any remainder stays on their head so
                # robbing a broke debtor doesn't wipe the bounty free.
                wallet = users[str(victim.id)].get("wallet", 0)
                bank = users[str(victim.id)].get("bank", 0)
                collected = min(bounty, wallet + bank)
                from_wallet = min(wallet, collected)
                users[str(victim.id)]["wallet"] = wallet - from_wallet
                users[str(victim.id)]["bank"] = bank - (collected - from_wallet)
                users[str(robber.id)]["wallet"] += collected
                remaining = bounty - collected
                if remaining <= 0:
                    del users[str(victim.id)]["bounty_amount"]
                    del users[str(victim.id)]["bounty_until"]
                    extra = f" You also collected a {collected} coin bounty!"
                else:
                    users[str(victim.id)]["bounty_amount"] = remaining
                    extra = (
                        f" You also collected a {collected} coin bounty; "
                        f"{remaining} coins are still on <@{victim.id}>'s head!"
                    )
            await write_bank(users)
            rob_embed = discord.Embed(
                title="Robbery Results",
                description=f"You have stolen {attempted} coins from <@{victim.id}>.{extra}",
                color=discord.Color.green(),
            )
            await ctx.respond(embed=rob_embed)

        else:
            if users.get(str(robber.id), {}).get("rob_insurance"):
                users[str(robber.id)]["rob_insurance"] = False
                await write_bank(users)
                em = discord.Embed(
                    title="Unsuccessful Robbery",
                    description=f"<@{victim.id}> caught you robbing, but your Rob Insurance covered the fine. No penalty!",
                    color=discord.Color.yellow(),
                )
                await ctx.respond(embed=em)
            else:
                fine = attempted
                paid = min(robber_wallet, fine)
                users[str(robber.id)]["wallet"] -= paid
                users[str(victim.id)]["wallet"] += paid
                unpaid = fine - paid
                msg = (
                    f"<@{victim.id}> caught you robbing. A fine of {fine} coins was "
                    f"owed; you paid {paid}."
                )
                if unpaid > 0:
                    existing_bounty = users[str(robber.id)].get("bounty_amount", 0)
                    existing_until = users[str(robber.id)].get("bounty_until", 0)
                    if existing_bounty > 0 and existing_until > time.time():
                        users[str(robber.id)]["bounty_amount"] = existing_bounty + unpaid
                        users[str(robber.id)]["bounty_until"] = max(
                            existing_until, time.time() + BOUNTY_DURATION
                        )
                    else:
                        users[str(robber.id)]["bounty_amount"] = unpaid
                        users[str(robber.id)]["bounty_until"] = time.time() + BOUNTY_DURATION
                    msg += f" The remaining {unpaid} coins turned into a bounty on your head!"
                await write_bank(users)
                em = discord.Embed(
                    title="Unsuccessful Robbery",
                    description=msg,
                    color=discord.Color.red(),
                )
                await ctx.respond(embed=em)

    @commands.slash_command(
        description="Deposit coins into the bank", guild_ids=GUILD_IDS
    )  # deposit command
    @option("amount", int, description="Amount of coins to deposit", min_value=0)
    @option("all", bool, description="Deposit your entire wallet", default=False)
    async def deposit(self, ctx, amount, all=False):
        user = ctx.user
        await self.open_account(user)
        bal = await self.update_bank(user)

        if all:
            amount = bal[0]

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
        description="Transfer coins to another user", guild_ids=GUILD_IDS
    )
    @option("member", discord.Member, description="User to transfer coins to")
    @option("amount", int, description="Amount of coins to transfer", min_value=1)
    async def transfer(self, ctx, member: discord.Member, amount: int):
        sender = ctx.user
        
        if sender == member:
            await ctx.respond("You can't transfer coins to yourself!")
            return
            
        await self.open_account(sender)
        await self.open_account(member)
        
        sender_bal = await self.update_bank(sender)
        
        if amount > sender_bal[0]:
            await ctx.respond("You don't have enough coins in your wallet!")
            return
            
        await self.update_bank(sender, -1 * amount, "wallet")
        await self.update_bank(member, amount, "wallet")
        
        transfer_embed = discord.Embed(
            title="Transfer Successful! 💸",
            description=f"You sent {amount} coins to {member.display_name}",
            color=discord.Color.green()
        )
        await ctx.respond(embed=transfer_embed)

    @commands.slash_command(
        description="Withdraw coins from the bank", guild_ids=GUILD_IDS
    )  # withdraw command
    @option("amount", int, description="Amount of coins to withdraw")
    @option("all", bool, description="Withdraw your entire bank", default=False)
    async def withdraw(self, ctx, amount, all=False):
        user = ctx.user
        await self.open_account(user)
        bal = await self.update_bank(user)

        if all:
            amount = bal[1]

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

    async def open_account(self, user):  # open_account function
        async with bank_lock:
            users = await self.get_bank_data()

            if str(user.id) in users:
                return False

            users[str(user.id)] = {}
            users[str(user.id)]["wallet"] = 0
            users[str(user.id)]["bank"] = 0
            users[str(user.id)]["bag"] = []

            await write_bank(users)

            return True

    async def get_bank_data(self):  # get_bank_data function
        return await read_bank()

    async def update_bank(self, user, change=0, mode="wallet"):  # update_bank function
        async with bank_lock:
            users = await self.get_bank_data()
            users[str(user.id)][mode] = max(0, users[str(user.id)][mode] + change)

            await write_bank(users)

            bal = [users[str(user.id)]["wallet"], users[str(user.id)]["bank"]]
            return bal

    @commands.slash_command(
        description="Check out what items you can buy with your coins", guild_ids=GUILD_IDS
    )  # shop command
    async def shop(self, ctx):
        em = discord.Embed(title="Shop", color=discord.Color.gold())
        for item in mainshop:
            name = item["name"]
            price = get_stock_price(item) if item.get("stock") else item["price"]
            desc = item["description"]
            em.add_field(
                name=name,
                value=f"<:icon_bling:1108989584022437972>**{price}** | {desc}",
            )

        await ctx.respond(embed=em)

    @commands.slash_command(
        description="Check out items that change Ok Bot's behavior", guild_ids=GUILD_IDS
    )  # botshop command
    async def botshop(self, ctx):
        em = discord.Embed(
            title="Ok Bot Config Shop",
            description="Spend coins to change Ok Bot's brain, model, and settings. Buy one, then use it from your bag.",
            color=discord.Color(0xFFA500),
        )
        for item in botshop:
            em.add_field(
                name=item["name"],
                value=f"<:icon_bling:1108989584022437972>**{item['price']}** | {item['description']}",
            )

        await ctx.respond(embed=em)

    @commands.slash_command(
        description="See Ok Bot's current configuration", guild_ids=GUILD_IDS
    )  # config command
    async def config(self, ctx):
        botconfig = await load_bot_config()
        em = discord.Embed(title="Ok Bot Config", color=discord.Color.blue())
        em.add_field(
            name="Model",
            value=botconfig.get("model") or "default",
            inline=False,
        )
        em.add_field(
            name="Max output tokens",
            value=botconfig.get("max_output_tokens") or "default",
            inline=False,
        )
        em.add_field(
            name="Thinking level",
            value=botconfig.get("thinking_level") or "default",
            inline=False,
        )
        em.add_field(
            name="Thinking summaries",
            value=botconfig.get("thinking_summaries") or "default",
            inline=False,
        )
        em.add_field(
            name="Tool choice",
            value=botconfig.get("tool_choice") or "default",
            inline=False,
        )
        em.add_field(
            name="Seed",
            value=botconfig.get("seed") or "random",
            inline=False,
        )
        em.add_field(
            name="Stop sequences",
            value=", ".join(botconfig.get("stop_sequences") or []) or "none",
            inline=False,
        )
        em.add_field(
            name="Custom brain",
            value="active" if botconfig.get("system_instruction") else "default",
            inline=False,
        )
        await ctx.respond(embed=em)

    @commands.slash_command(description="Check what items you have", guild_ids=GUILD_IDS)  # bag command
    async def bag(self, ctx):
        await self.open_account(ctx.user)
        user = ctx.user
        users = await self.get_bank_data()

        bag = users[str(user.id)]["bag"]
        items = [item for item in bag if item.get("amount", 0) > 0]
        em = discord.Embed(title="Bag", color=discord.Color.blue())
        if not items:
            em = discord.Embed(
                title="Bag",
                color=discord.Color.blue(),
                description="You have nothing in your bag",
            )

        for item in items:
            name = item["item"].title()
            amount = item["amount"]

            em.add_field(name=name, value=amount)

        await ctx.respond(embed=em)

    @commands.slash_command(description="Buy something with your coins", guild_ids=GUILD_IDS)  # buy command
    @option("item", str, description="Item to buy", autocomplete=get_shop_items)
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
            view = BuyView(self, ctx.user, item, amount)
            msg = await ctx.respond(
                f"You just bought {amount} {item} (Wallet balance: {bal[0]})",
                view=view,
            )
            view.message = msg

    async def buy_this(self, user, item_name, amount):  # buy_this function
        item_name = item_name.lower()
        name_ = None
        for item in all_shop_items:
            name = item["name"].lower()
            if name == item_name:
                name_ = name
                price = get_stock_price(item) if item.get("stock") else item["price"]
                break

        if name_ is None:
            return [False, 1]

        cost = price * amount

        # One atomic read-modify-write: balance check, bag update and wallet
        # deduction are committed together so concurrent commands can't clobber
        # any of them.
        async with bank_lock:
            users = await self.get_bank_data()
            if users[str(user.id)]["wallet"] < cost:
                return [False, 2]

            bag = users[str(user.id)]["bag"]
            if not isinstance(bag, list):
                bag = []
                users[str(user.id)]["bag"] = bag
            for thing in bag:
                if thing["item"] == item_name:
                    thing["amount"] += amount
                    break
            else:
                bag.append({"item": item_name, "amount": amount})

            users[str(user.id)]["wallet"] -= cost
            await write_bank(users)

        return [True, "Worked"]

    @commands.slash_command(description="Sell items in your bag", guild_ids=GUILD_IDS)  # sell command
    @option("item", str, description="Item to sell", autocomplete=get_shop_items)
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
        for item in all_shop_items:
            name = item["name"].lower()
            if name == item_name:
                name_ = name
                if price is None:
                    if item.get("stock"):
                        price = get_stock_price(item)
                    else:
                        price = 0.9 * item["price"]
                break

        if name_ is None:
            return [False, 1]

        cost = math.floor(price * amount)

        # Single atomic read-modify-write: bag removal and wallet credit are
        # committed together, so no concurrent command can see the item gone
        # without the payment (or vice versa).
        async with bank_lock:
            users = await self.get_bank_data()
            bag = users[str(user.id)]["bag"]
            if not isinstance(bag, list):
                return [False, 3]
            for index, thing in enumerate(bag):
                if thing["item"] == item_name:
                    new_amt = thing["amount"] - amount
                    if new_amt < 0:
                        return [False, 2]
                    if new_amt == 0:
                        bag.pop(index)
                    else:
                        thing["amount"] = new_amt
                    break
            else:
                return [False, 3]

            users[str(user.id)]["wallet"] += cost
            await write_bank(users)

        return [True, "Worked"]

    @commands.slash_command(description="Use something in your bag", guild_ids=GUILD_IDS)  # use command
    @option("item", str, description="Item to use", autocomplete=get_shop_items)
    @option("amount", int, description="Amount to use")
    @option(
        "value",
        str,
        description="Value for config items (e.g. value:<@user>)",
        default=None,
    )
    async def use(self, ctx, item, amount=1, value=None):
        await self.open_account(ctx.user)
        if amount < 1:
            await ctx.respond(ERROR_2)
            return

        item_meta = await self.find_item(item)
        if item_meta is None:
            await ctx.respond(ERROR_1)
            return

        if "config" in item_meta:
            if amount != 1:
                await ctx.respond("Config items are used one at a time.")
                return
            await ctx.respond(await self.use_config_item(ctx, item_meta, value))
            return

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
        if item_meta.get("effect"):
            if item_meta["effect"] == "mystery_crate":
                await ctx.respond(await self.bulk_mystery_crate(ctx.user, amount))
            else:
                responses = []
                for _ in range(amount):
                    responses.append(await self.apply_item_effect(ctx, item_meta, value))
                await ctx.respond("\n".join(responses))
        else:
            await ctx.respond(item_meta.get("usemsg") or "Done.")

    async def find_item(self, item_name):  # find_item function
        item_name = item_name.lower()
        for item in all_shop_items:
            if item["name"].lower() == item_name:
                return item
        return None

    async def use_config_item(self, ctx, item_meta, value):  # use_config_item
        config = item_meta["config"]
        ctype = config["type"]

        if ctype == "reset_all":
            res = await self.use_this(ctx.user, item_meta["name"], 1)
            if not res[0]:
                return "You don't have this item in your bag."
            botconfig = await load_bot_config()
            for key, default in DEFAULT_BOT_CONFIG.items():
                if key == "system_instruction":
                    continue
                botconfig[key] = default
            await save_bot_config(botconfig)
            return item_meta.get("usemsg", "Config reset.")

        if ctype == "system_instruction" and config.get("mode") == "reset":
            res = await self.use_this(ctx.user, item_meta["name"], 1)
            if not res[0]:
                return "You don't have this item in your bag."
            botconfig = await load_bot_config()
            botconfig["system_instruction"] = None
            await save_bot_config(botconfig)
            return item_meta.get("usemsg", "Default brain restored.")

        if config.get("mode") == "prompt":
            if not value or not value.strip():
                return f"Please provide a value with `/use item:{item_meta['name']} value:<...>`"
            actual = value.strip()
        else:
            actual = config.get("value")

        if actual is None:
            return "This item is missing a value."

        if ctype == "thinking_level":
            if actual not in ("minimal", "low", "medium", "high"):
                return "Thinking level must be one of: minimal, low, medium, high."
        elif ctype == "thinking_summaries":
            if actual not in ("auto", "none"):
                return "Thinking summaries must be one of: auto, none."
        elif ctype == "tool_choice":
            if actual not in ("auto", "any", "none", "validated"):
                return "Tool choice must be one of: auto, any, none, validated."

        if ctype in ("max_output_tokens", "seed"):
            try:
                actual = int(actual)
            except ValueError:
                return f"Please provide a valid number for {item_meta['name']}."
        elif ctype == "stop_sequences":
            actual = [s.strip() for s in actual.split(",") if s.strip()]

        res = await self.use_this(ctx.user, item_meta["name"], 1)
        if not res[0]:
            return "You don't have this item in your bag."

        botconfig = await load_bot_config()
        if ctype == "system_instruction":
            botconfig["system_instruction"] = actual
        elif ctype == "model":
            botconfig["model"] = actual
        elif ctype == "max_output_tokens":
            botconfig["max_output_tokens"] = actual
        elif ctype == "thinking_level":
            botconfig["thinking_level"] = actual
        elif ctype == "thinking_summaries":
            botconfig["thinking_summaries"] = actual
        elif ctype == "tool_choice":
            botconfig["tool_choice"] = actual
        elif ctype == "seed":
            botconfig["seed"] = actual
        elif ctype == "stop_sequences":
            botconfig["stop_sequences"] = actual
        await save_bot_config(botconfig)

        return item_meta.get("usemsg", "Applied.")

    async def apply_item_effect(self, ctx, item_meta, value):  # apply_item_effect
        effect = item_meta.get("effect")
        if effect == "mystery_crate":
            return await self.effect_mystery_crate(ctx.user)
        if effect == "money_printer":
            return await self.effect_money_printer(ctx.user)
        if effect == "rob_insurance":
            return await self.effect_rob_insurance(ctx.user)
        if effect == "interest_vault":
            return await self.effect_interest_vault(ctx.user)
        if effect == "job_contract":
            return await self.effect_job_contract(ctx.user)
        if effect == "gift_wrap":
            return await self.effect_gift_wrap(ctx, value)
        return item_meta.get("usemsg") or "Done."

    @staticmethod
    def _roll_crate():
        # Net-zero gamble: weighted payouts average out to the 20k crate price.
        # 0.40*8000 + 0.20*37500 + 0.05*186000 = 3200 + 7500 + 9300 = 20000.
        roll = random.random()
        if roll < 0.35:
            return 0, "nothing but a soggy sock"
        if roll < 0.75:
            return random.randint(1000, 15000), "a decent haul"
        if roll < 0.95:
            return random.randint(15000, 60000), "a fat stack"
        return random.randint(60000, 312000), "a golden jackpot"

    async def effect_mystery_crate(self, user):
        coins, flavor = self._roll_crate()
        if coins:
            await self.update_bank(user, coins, "wallet")
            return f"You cracked the crate open and found **{coins} coins** — {flavor}!"
        return f"You cracked the crate open and found {flavor}. Yikes."

    async def bulk_mystery_crate(self, user, amount):
        total = 0
        hits = 0
        duds = 0
        for _ in range(amount):
            coins, _ = self._roll_crate()
            if coins:
                total += coins
                hits += 1
            else:
                duds += 1
        if total:
            await self.update_bank(user, total, "wallet")
        if hits == 0:
            return f"Opened {amount} crates... all duds. Yikes."
        return f"Opened {amount} crates for a total of **{total:,} coins** ({hits} hits, {duds} duds)."

    async def effect_money_printer(self, user):
        users = await self.get_bank_data()
        data = users[str(user.id)]
        data.setdefault("wallet", 0)
        data.setdefault("bank", 0)
        now = time.time()
        data["printer_until"] = max(data.get("printer_until", 0), now) + PRINTER_DAYS * 86400
        await write_bank(users)
        return f"Your Money Printer runs until <t:{int(data['printer_until'])}:R>, paying {PRINTER_RATE} coins/day on /bal."

    async def effect_rob_insurance(self, user):
        users = await self.get_bank_data()
        users[str(user.id)]["rob_insurance"] = True
        await write_bank(users)
        return "You're now covered by Rob Insurance for your next failed robbery."

    async def effect_interest_vault(self, user):
        users = await self.get_bank_data()
        data = users[str(user.id)]
        data.setdefault("wallet", 0)
        data.setdefault("bank", 0)
        now = time.time()
        data["vault_until"] = max(data.get("vault_until", 0), now) + VAULT_DAYS * 86400
        data["vault_rate"] = VAULT_RATE
        await write_bank(users)
        return f"Your Interest Vault pays {int(VAULT_RATE * 100)}% daily on your bank balance until <t:{int(data['vault_until'])}:R>."

    async def effect_job_contract(self, user):
        users = await self.get_bank_data()
        users[str(user.id)]["has_job"] = True
        await write_bank(users)
        return "You're hired! Use /work to earn coins."

    async def _resolve_target(self, ctx, value):
        if not value:
            return None
        value = value.strip()
        try:
            user_id = int(value.strip("<@!>"))
        except ValueError:
            return None
        return ctx.guild.get_member(user_id)

    async def effect_gift_wrap(self, ctx, value):
        if not value or not value.strip():
            return "Please provide a target and item with value:<@user> <item name>."
        parts = value.strip().split(None, 1)
        if len(parts) != 2:
            return "Format: value:<@user> <item name>"
        target = await self._resolve_target(ctx, parts[0])
        if target is None:
            return "Couldn't find that target user."
        item_query = parts[1].strip().lower()

        users = await self.get_bank_data()
        sender_data = users[str(ctx.user.id)]
        index = None
        for i, thing in enumerate(sender_data["bag"]):
            if thing["item"].lower() == item_query:
                index = i
                break
        if index is None:
            return "You don't have that item in your bag."
        gift_name = sender_data["bag"][index]["item"]
        sender_data["bag"][index]["amount"] -= 1
        if sender_data["bag"][index]["amount"] <= 0:
            sender_data["bag"].pop(index)

        tdata = users.get(str(target.id))
        if tdata is None:
            users[str(target.id)] = {"wallet": 0, "bank": 0, "bag": []}
            tdata = users[str(target.id)]
        for thing in tdata["bag"]:
            if thing["item"].lower() == gift_name.lower():
                thing["amount"] += 1
                break
        else:
            tdata["bag"].append({"item": gift_name, "amount": 1})
        await write_bank(users)
        return f"You wrapped and sent **{gift_name}** to <@{target.id}>!"

    async def use_this(self, user, item_name, amount):  # use_this function
        item_name = item_name.lower()
        name_ = None
        for item in all_shop_items:
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

        await write_bank(users)

        return [True, "Worked"]

    @commands.slash_command(
        description="Check out the richest people", guild_ids=GUILD_IDS
    )  # baltop command
    @option("x", int, description="Display up to the xth richest person")
    async def baltop(self, ctx, x=10):
        users = await self.get_bank_data()
        leader_board = []
        total = []
        for user in users:
            try:
                name = int(user)
            except ValueError:
                continue
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

        try:
            await self.open_account(self.bot.user)
        except Exception:
            pass

        # Deduct the bet up front (win or lose) and hand it to Ok Bot so coins
        # are conserved. On a win the full payout (amount * multiplier) is
        # transferred back; on a loss nothing is paid.
        await self.update_bank(user, -amount, "wallet")
        await self.update_bank(self.bot.user, amount, "wallet")

        if userroll > botroll:
            diff = userroll - botroll
            if diff <= 15:
                multiplier = 1.2
                win_title = "Close Win!"
            elif diff <= 35:
                multiplier = 1.5
                win_title = "Decent Win!"
            elif diff <= 55:
                multiplier = 2.0
                win_title = "Solid Win!"
            elif diff <= 80:
                multiplier = 3.0
                win_title = "Crushing Win!"
            else:
                multiplier = 6.0
                win_title = "PERFECT WIN!"
            payout = int(amount * multiplier)

            bot_bal = await self.update_bank(self.bot.user)
            bot_wallet = bot_bal[0]

            if bot_wallet < payout:
                # Refund the bet since Ok Bot can't cover the payout.
                await self.update_bank(self.bot.user, -amount, "wallet")
                bal = await self.update_bank(user, amount, "wallet")
                embed = discord.Embed(
                    title=win_title,
                    description="Ok Bot doesn't have enough funds to pay out right now. Your bet was refunded.",
                    color=discord.Color.yellow(),
                )
                embed.add_field(name=f"{user} rolled", value=f"{userroll}", inline=True)
                embed.add_field(
                    name=f"{self.bot.user} rolled", value=f"{botroll}", inline=True
                )
                embed.add_field(name=DESC, value=f"{bal[0]}", inline=False)
                return await ctx.respond(embed=embed)

            # Transfer the full payout from bot to user
            await self.update_bank(self.bot.user, -payout, "wallet")
            bal = await self.update_bank(user, payout, "wallet")

            embed = discord.Embed(
                title=win_title,
                description=f"**Payout:** {payout} coins *(+{payout - amount} profit)*",
                color=discord.Color.green(),
            )
            embed.add_field(name=f"{user} rolled", value=f"{userroll}", inline=True)
            embed.add_field(
                name=f"{self.bot.user} rolled", value=f"{botroll}", inline=True
            )
            embed.add_field(name=DESC, value=f"{bal[0]}", inline=False)
            return await ctx.respond(embed=embed)

        elif userroll < botroll:
            bal = await self.update_bank(user)
            embed = discord.Embed(
                title="You Lost...",
                description=f"**Loss:** -{amount} coins",
                color=discord.Color.red(),
            )
            embed.add_field(name=f"{user} rolled", value=f"{userroll}", inline=True)
            embed.add_field(
                name=f"{self.bot.user} rolled", value=f"{botroll}", inline=True
            )
            embed.add_field(name=DESC, value=f"{bal[0]}", inline=False)
            return await ctx.respond(embed=embed)

        else:
            # Draw: give the bet back
            await self.update_bank(self.bot.user, -amount, "wallet")
            bal = await self.update_bank(user, amount, "wallet")
            embed = discord.Embed(title="Draw", color=discord.Color.yellow())
            embed.add_field(name=f"{user} rolled", value=f"{userroll}", inline=True)
            embed.add_field(
                name=f"{self.bot.user} rolled", value=f"{botroll}", inline=True
            )
            embed.add_field(name=DESC, value=f"{bal[0]}", inline=False)
            return await ctx.respond(embed=embed)

    @commands.slash_command(description="Work your job for coins", guild_ids=GUILD_IDS)
    async def work(self, ctx):
        user = ctx.user
        await self.open_account(user)
        users = await self.get_bank_data()
        data = users[str(user.id)]

        if not data.get("has_job"):
            await ctx.respond(
                embed=discord.Embed(
                    title="No job",
                    description="You don't have a job. Buy a 📄 Job Contract from the shop first!",
                    color=discord.Color.red(),
                )
            )
            return

        now = time.time()
        last = data.get("work_at", 0)
        if now - last < JOB_COOLDOWN:
            await ctx.respond(
                embed=discord.Embed(
                    title="Not yet",
                    description=f"Come back <t:{int(last + JOB_COOLDOWN)}:R>.",
                    color=discord.Color.yellow(),
                )
            )
            return

        pay = random.randint(JOB_PAY_MIN, JOB_PAY_MAX)
        data["wallet"] = data.get("wallet", 0) + pay
        data["work_at"] = now
        await write_bank(users)

        await ctx.respond(
            embed=discord.Embed(
                title="Payday 💼",
                description=f"You earned {pay} coins from your job.",
                color=discord.Color.green(),
            )
        )


def setup(bot):
    bot.add_cog(Economy(bot))
