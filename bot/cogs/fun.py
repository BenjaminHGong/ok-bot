import random

from discord import option
from discord.ext import commands

from grammar import check_grammar
from utils import get_data, update_data

GUILD_IDS = [1024196422637195315, 1099937674200105030]
owner_ids = [755525460267630612]


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = commands.Bot = bot

    @commands.Cog.listener()
    async def on_connect(self):
        print("Fun commands loaded")
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.author.bot:
            grammar_list = await get_data("grammar")
            if message.author.id in grammar_list:
                if await check_grammar(message.content) != False:
                    response = f"<@{message.author.id}> " + await check_grammar(message.content)
                    await message.channel.send(response)


    @commands.slash_command(
        description="Toggle annoying grammar suggestions", guild_id=GUILD_IDS
    )
    async def grammar(self, ctx):
        grammarlist = await get_data("grammar")
        if ctx.user.id in grammarlist:
            grammarlist.remove(ctx.user.id)
            await ctx.respond("You will no longer receive grammar suggestions. :(")
        else:
            grammarlist.append(ctx.user.id)
            await ctx.respond("Time to fix your grammar! >:)")
        await update_data("grammar", grammarlist)

    @commands.slash_command(
        name="8ball",
        description="Settle an argument with this irrefutable evidence",
        guild_ids=GUILD_IDS,
    )
    @option("question", str, description="Question to ask")
    async def eightball(self, ctx, question):
        answers = [
            "That's a sus question",
            "That's a VERY sus question",
            "Don't be a monger, ask again",
            "Ok bud, no",
            "No that's bad",
            "Amogus?",
            "No way!",
            "That's real",
            "No, that's trash",
            "lol, no",
            "Bruh moment",
            "Very questionable",
            "Me when... maybe",
            "I enjoy",
            "No that's cring",
            "OMG yes",
            "WTF no",
            "Right now, yes",
            "I agree",
            "Bruh moment",
            "No, and also L",
            "EZ yes",
            "So true",
            "LMAO! Good question, but idk",
            "True momento",
            "Literally, no",
            "Wow, just wow",
            "No, mald harder",
            "I could tell you, but I don't feel like it",
            "Error: You do not have Ok Bot's respect",
            "No you noob",
            "BRUH what?!?!? I'm not answering that.",
            "brb",
            "Oh! I know the answer to this......actually nvm",
            "Of course, duh",
            "I guess...",
            "Huh, I've never thought about that before. Now that you've brought it up, yes.",
            "6GCkFwidmtD%73C#7L&z27XeizgxVMQ6nY98h7TVFcYHr%^dAd#jE3^H&AP42gGxx3^e&NMxCm$SBG*6@TPP*RBGvbCYt*q^hQu2SnHnH9dNcb75uttfyUkg@XZQVZfg",
            "Stop asking me that RIGHT NOW!!!",
            "Oh, how delightful it would be to enlighten you with an answer to your inquiry! Alas, I fear the depths of my erudition may surpass the limits of your comprehension. But fear not, for the fault lies not with your humble curiosity, but rather with the boundless expanse of knowledge that resides within me.",
        ]

        response = random.choice(answers)
        await ctx.respond(f"Question: {question}\nAnswer: {response}")

    @commands.slash_command(description="Generate random sussy words")  # rsw command
    @option("sussy_length", int, description="Amount of sussy phrases")
    async def rsw(self, ctx, sussy_length=1):
        random_quotes = [
            "real",
            "sus",
            "sussy",
            "monger",
            "ok bud",
            "bad",
            "amogus",
            "no",
            "yes",
            "gud",
            "mald",
            "trash",
            "lol",
            "pro",
            "bruh",
            "very",
            "me when",
            "i enjoy",
            "cring",
            "omg",
            "poop",
            "wtf",
            "right now",
            "agree",
            "moment",
            "L",
            "ez",
            "so",
            "lmao",
            "mommento",
            "literally",
            "wow",
            "rage",
        ]
        response2 = ""
        for _ in range(sussy_length):
            response1 = random.choice(random_quotes)

            response2 = response2 + response1 + " "

        await ctx.respond(response2)


def setup(bot):
    bot.add_cog(Fun(bot))
