import google.generativeai as genai
import jsonpickle
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
    "gemini-1.5-flash", safety_settings=safety_settings
)


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
                    chat_history = await get_data("chathistory")
                    channel_id = str(message.channel.id)
                    if channel_id not in chat_history.keys(): 
                        chat_history[channel_id] = jsonpickle.encode([], True)
                    chat = model.start_chat(history=jsonpickle.decode(chat_history[channel_id]))
                    cleaned_content = message.content.replace(
                        "<@1099931878926078022>", ""
                    )
                    for mention in message.mentions:
                        cleaned_content = cleaned_content.replace(
                            mention.mention, mention.display_name
                        )
                    response = chat.send_message(f"{message.author.display_name}: {cleaned_content}")
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
                    chat_history[channel_id] = jsonpickle.encode(chat.history, True)
                    await update_data("chathistory", chat_history)

                except ValueError:
                    await message.channel.trigger_typing()
                    await message.channel.send("sorry can't answer that")
        await self.bot.process_commands(message)
    @commands.slash_command(description="Clear chat history with Ok Bot")
    async def clear(self, ctx):
        chat_history = await get_data("chathistory")
        channel_id = str(ctx.channel.id)
        chat_history[channel_id] = jsonpickle.encode([], True)
        await update_data("chathistory", chat_history)
        await ctx.respond("Chat history cleared")



def setup(bot):
    bot.add_cog(Fun(bot))
