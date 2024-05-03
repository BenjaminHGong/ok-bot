import google.generativeai as genai
import language_tool_python
from discord.ext import commands
from utils import get_data_once, get_data, update_data

genai.configure(transport="grpc")
safety_settings = [
    {
        "category": "HARM_CATEGORY_DANGEROUS",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_NONE",
    },
]
model = genai.GenerativeModel(
    "tunedModels/ok-bot-ja3if8ae8vcw", safety_settings=safety_settings
)

tool = language_tool_python.LanguageTool("en-US")

GUILD_IDS = get_data_once("guilds")


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
            if self.bot.user.mentioned_in(message):
                try:
                    await message.channel.trigger_typing()
                    cleaned_content = message.content.replace(
                        "<@1099931878926078022>", ""
                    )
                    for mention in message.mentions:
                        cleaned_content = cleaned_content.replace(
                            mention.mention, mention.display_name
                        )
                    response = model.generate_content(cleaned_content)
                    response_text = response.text
                    paragraphs = response_text.split("\n")
                    chunk = ""
                    for paragraph in paragraphs:
                        if len(chunk) + len(paragraph) > 2000:
                            await message.channel.send(chunk)
                            chunk = ""
                        chunk += paragraph + "\n"
                    if chunk:
                        await message.channel.send(chunk)

                except ValueError:
                    await message.channel.trigger_typing()
                    await message.channel.send("sorry can't answer that")
        await self.bot.process_commands(message)

    @commands.slash_command(
        description="Toggle annoying grammar suggestions", guild_ids=GUILD_IDS
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


def setup(bot):
    bot.add_cog(Fun(bot))
