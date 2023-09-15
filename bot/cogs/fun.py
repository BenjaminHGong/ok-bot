import random

import language_tool_python
from discord import option
from discord.ext import commands
from utils import get_data, update_data

tool = language_tool_python.LanguageTool("en-US")
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
                if await self.check_grammar(message.content) != False:
                    response = f"<@{message.author.id}> " + await self.check_grammar(
                        message.content
                    )
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

    async def check_grammar(self, text):
        if len(tool.check(text)) > 0:
            correct_text = tool.correct(text)
            response = "Bruh, your grammar is trash.\n"
            response += "Original Text: " + text + "\n"
            response += "Text after correction: " + correct_text
            return response
        else:
            return False

    @commands.slash_command(
        name="8ball",
        description="Settle an argument with this irrefutable evidence",
        guild_ids=GUILD_IDS,
    )
    @option("question", str, description="Question to ask")
    async def eightball(self, ctx, question):
        positive = [
            "That's real",
            "I enjoy",
            "OMG yes",
            "Right now, yes",
            "So true",
            "True momento",
            "100% True",
            "YES!!!!!",
            "Real 👍",
            "Yup, that's right",
            "Yeah",
            "Yes, no question about it lmao",
            "I gotta agree lol",
            "I guess...",
            "Huh, I've never thought about that before. Now that you've brought it up, yes.",
            "EZ yes",
            "I agree",
            "Of course, duh",
        ]
        negative = [
            "Ok bud, no",
            "No that's bad",
            "No way!",
            "No, that's trash",
            "lol, no",
            "Literally, no",
            "No you noob",
            "No, mald harder",
            "No that's cring",
            "WTF no",
            "No, and also L",
            "NO!!!!!!!",
            "Non",
            "Nah not true",
            "What no",
        ]
        other = [
            "That's a VERY sus question",
            "Don't be a monger, ask again",
            "Amogus?",
            "What the sus",
            "Make poop?",
            "Stop making questions of floccinaucinihilipilification",
            "Bruh moment",
            "Very questionable question",
            "Me when... maybe",
            "LMAO! Good question, but idk",
            "Wow, just wow",
            "I could tell you, but I don't feel like it",
            "Error: You do not have Ok Bot's respect",
            "BRUH what?!?!? I'm not answering that.",
            "brb",
            "Uhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh",
            "💀",
            "wdym i don't get what you're trying to ask",
            "Get 100%% on your next test and I'll tell you",
            "Oh! I know the answer to this......actually nvm",
            "6GCkFwidmtD%73C#7L&z27XeizgxVMQ6nY98h7TVFcYHr%^dAd#jE3^H&AP42gGxx3^e&NMxCm$SBG*6@TPP*RBGvbCYt*q^hQu2SnHnH9dNcb75uttfyUkg@XZQVZfg",
            "Stop asking me that RIGHT NOW!!!",
            "Oh, how delightful it would be to enlighten you with an answer to your inquiry! Alas, I fear the depths of my erudition may surpass the limits of your comprehension. But fear not, for the fault lies not with your humble curiosity, but rather with the boundless expanse of knowledge that resides within me.",
        ]
        i = random.randrange(4)
        response = ""
        if i == 0 or i == 1:
            response = random.choice(positive)
        elif i == 2:
            response = random.choice(negative)
        else:
            response = random.choice(other)
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
