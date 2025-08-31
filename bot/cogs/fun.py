import os
import jsonpickle
from io import BytesIO

import discord
from discord.ext import commands

from google import genai
from google.genai import types
from google.genai.types import GenerateContentConfig, Content, Part
from utils import get_data_once, get_data, update_data

import asyncio

MAX_HISTORY_BYTES = 72 * 1024 * 1024 

def trim_history_jsonpickle(history, max_bytes=MAX_HISTORY_BYTES):
    if not history:
        return []

    # Keep the first two entries (system instruction + bot's acknowledgment)
    system_msgs = history[:2]
    remaining_msgs = history[2:]

    # Pre-encode the system messages to calculate their size once
    system_msgs_size = len(jsonpickle.encode(system_msgs).encode('utf-8'))
    if system_msgs_size > max_bytes:
        raise ValueError("System messages alone exceed the maximum allowed size.")

    trimmed = []
    current_size = system_msgs_size

    # Build from most recent backward
    for msg in reversed(remaining_msgs):
        msg_size = len(jsonpickle.encode([msg]).encode('utf-8'))
        if current_size + msg_size > max_bytes:
            break
        trimmed.insert(0, msg)
        current_size += msg_size

    return system_msgs + trimmed
    
async def keep_typing(channel):
        try:
            while True:
                await channel.trigger_typing()
                await asyncio.sleep(4)  # re-trigger every 4 seconds
        except asyncio.CancelledError:
            pass

# ── Configure your Gemini client ───────────────────────────────────────────────
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

CHAT_MODEL = "gemini-2.0-flash-preview-image-generation"

GUILD_IDS = get_data_once("guilds")


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    system_instruction = (
        "You are Ok Bot, a Discord bot chatting with users in a Discord server.\n"
        "You must obey the following permanently:\n"
        "- Always respond as Ok Bot.\n"
        "- Do not include usernames in your replies.\n"
        "- Every user message starts with their name and colon.\n"
        "- Never repeat usernames in your response.\n"
    )
    bot_response = "Got it! My name is Ok Bot."
    system_instruction_content = Content(parts=[Part(text=system_instruction)], role='user')
    bot_response_content = Content(parts=[Part(text=bot_response)], role='model')
    
    @commands.Cog.listener()
    async def on_connect(self):
        print("Fun commands loaded")
        
    user_message = Content(parts=[Part(text="User message")], role='user')
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not self.bot.user.mentioned_in(message):
            await self.bot.process_commands(message)
            return

        typing_task = asyncio.create_task(keep_typing(message.channel))
        
        try:
            cleaned = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
            for m in message.mentions:
                cleaned = cleaned.replace(m.mention, m.display_name)

            # multimodal / text chat with history
            chat_history = await get_data("chathistory")
            chan_id = str(message.channel.id)
            if chan_id not in chat_history:
                chat_history[chan_id] = jsonpickle.encode([], True)
            hist = jsonpickle.decode(chat_history[chan_id])

            if not hist:
                hist.append(self.system_instruction_content)
                
            hist = trim_history_jsonpickle(hist)
            
            chat = client.chats.create(model=CHAT_MODEL, history=hist, config=GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"], 
                safety_settings=[
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, 
                        threshold=types.HarmBlockThreshold.BLOCK_NONE
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY, 
                        threshold=types.HarmBlockThreshold.BLOCK_NONE
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, 
                        threshold=types.HarmBlockThreshold.BLOCK_NONE
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, 
                        threshold=types.HarmBlockThreshold.BLOCK_NONE
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, 
                        threshold=types.HarmBlockThreshold.BLOCK_NONE
                    )
                ]
            ))

            parts: list[Content | str] = []
            if message.attachments:
                att = message.attachments[0]
                if att.content_type and att.content_type.startswith("image/"):
                    img_bytes = await att.read()
                    parts.append(Part.from_bytes(data=img_bytes, mime_type=att.content_type))

            if cleaned:
                parts.append(f"{message.author.display_name}: {cleaned}")

            resp = await asyncio.to_thread(chat.send_message, parts)

            # check for empty response
            if not resp.candidates:
                await message.channel.send("Ok Bot didn't respond. Try again.")
                return

            image_sent = False
            text_buffer = []
            img_bytes = None
            

            for part in resp.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data is not None:
                    mime_type = part.inline_data.mime_type
                    if mime_type and mime_type.startswith("image/"):
                        img_bytes = part.inline_data.data
                        
                elif hasattr(part, "text") and part.text:
                    text_buffer.append(part.text)
                    
            if text_buffer:
                for line in "\n".join(text_buffer).split("\n"):
                    if line.strip():
                        await message.channel.send(line)
            
            if img_bytes:
                image_sent = True
                await message.channel.send(file=discord.File(BytesIO(img_bytes), filename="image.png"))
            if not image_sent and any("generate" in line.lower() and "image" in line.lower() for line in text_buffer):
                await message.channel.send("_Ok Bot didn't generate an image. Try again? 🤔_")

            # Save updated, trimmed history (including all system & model/user turns)
            new_hist = chat.get_history()
            # Optionally, re-trim new_hist here before saving if you expect growth
            chat_history[chan_id] = jsonpickle.encode(new_hist, True)
            await update_data("chathistory", chat_history)
        except genai.errors.ClientError:
            await message.channel.send("Ok Bot has reached its quota limit. Please try again later.")
            
        finally:
            typing_task.cancel()
        await self.bot.process_commands(message)

    @commands.slash_command(description="Clear chat history with Ok Bot")
    async def clear(self, ctx):
        chat_history = await get_data("chathistory")
        cid = str(ctx.channel.id)
        
        if cid in chat_history:
            chat_history[cid] = jsonpickle.encode([self.system_instruction_content, self.bot_response_content], True)
            await update_data("chathistory", chat_history)
            await ctx.respond("Chat history for this channel has been cleared.")
        else:
            await ctx.respond("No chat history found for this channel.")


def setup(bot):
    bot.add_cog(Fun(bot))
