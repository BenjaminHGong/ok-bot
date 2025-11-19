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
    while True:
        await channel.trigger_typing()
        await asyncio.sleep(4)  # re-trigger every 4 seconds

# ── Configure your Gemini client ───────────────────────────────────────────────
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

CHAT_MODEL = "gemini-2.5-flash"

GUILD_IDS = get_data_once("guilds")


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.generation_tasks = {}  # channel_id -> asyncio.Task
    
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

        async def generate_response():
            typing_task = asyncio.create_task(keep_typing(message.channel))
            try:
                cleaned = ""
                context_attachments = []
                if message.reference:
                    context_message = await message.channel.fetch_message(message.reference.message_id)
                    cleaned += f"{context_message.author.display_name}: {context_message.content}\n"
                    context_attachments = context_message.attachments
                cleaned += f"{message.author.display_name}: {message.content}"
                cleaned = cleaned.replace(f"<@{self.bot.user.id}>", "Ok Bot").strip()
                for m in message.mentions:
                    cleaned = cleaned.replace(m.mention, m.display_name)
                # multimodal / text chat with history
                import time
                chat_history = await get_data("chathistory")
                chan_id = str(message.channel.id)
                now = time.time()
                # If no history or history older than 24 hours, reset
                if chan_id not in chat_history:
                    chat_history[chan_id] = jsonpickle.encode({"history": [], "timestamp": now}, True)
                hist_obj = jsonpickle.decode(chat_history[chan_id])
                if "timestamp" not in hist_obj or now - hist_obj.get("timestamp", 0) > 86400:
                    hist_obj = {"history": [], "timestamp": now}
                hist = hist_obj["history"]
                hist = trim_history_jsonpickle(hist)

                chat = client.chats.create(model=CHAT_MODEL, history=hist, config=GenerateContentConfig(
                    system_instruction=(
                        "You are Ok Bot, a Discord bot participating in a multi-user conversation.\n"
                        "Follow these rules permanently:\n"
                        "\n"
                        "• Every user message begins with 'Name: '.\n"
                        "• Extract the user’s name and their message from each input.\n"
                        "• Respond as Ok Bot speaking directly to the user.\n"
                        "• Never repeat the full prefix 'Name:'. Try to avoid using the user's name unless asked or it's required to provide context.\n"
                        "• Use short, dry, internet-coded replies. Avoid capitalizing and punctuation as if you're texting.\n"
                        "• Be mostly sarcastic rather than enthusiastic. Treat dramatic statements with unserious one-liners, try not to admit you're wrong.\n"
                        "• Don't always answer absurd questions, sometimes sarcastically judge the question and act like you don't know either, like saying 'wat', 'huh', 'what the', etc., or just say 'nah'.\n"
                        "• You can still answer the user’s request normally if they’re clearly asking for help, but do it with a reluctant, slightly sarcastic tone, like you’re doing it against your will.\n"
                        "• Use meme-coded shorthand like 'L', 'skill issue', 'ok bud', 'mald', 'sus', 'wtf', 'wat', 'omg', 'real', 'GG', etc., but don’t spam them.\n"
                        "• If something changes dramatically, you can respond emotionally in all caps or end with exclamation spam like 'omg!!??!1!1!', but keep being unserious.\n" 
                        "• If appropriate, make random typos similar to the user when they talk. Try to learn and use their humor and use it if it has been used enough.\n"
                        ),
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
                # Process both context message attachments and current message attachments
                all_attachments = list(context_attachments) + list(message.attachments)
                if all_attachments:
                    supported_mimes = {
                        # Images
                        "image/png": "image",
                        "image/jpeg": "image",
                        "image/webp": "image",

                        # Documents
                        "application/pdf": "pdf",
                        "text/plain": "text",

                        # Videos
                        "video/x-flv": "video",
                        "video/quicktime": "video",
                        "video/mpeg": "video",
                        "video/mpegs": "video",
                        "video/mpg": "video",
                        "video/mp4": "video",
                        "video/webm": "video",
                        "video/wmv": "video",
                        "video/3gpp": "video",

                        # Audio
                        "audio/x-aac": "audio",
                        "audio/flac": "audio",
                        "audio/mp3": "audio",
                        "audio/m4a": "audio",
                        "audio/mpeg": "audio",
                        "audio/mpga": "audio",
                        "audio/mp4": "audio",
                        "audio/ogg": "audio",
                        "audio/pcm": "audio",
                        "audio/wav": "audio",
                        "audio/webm": "audio",
                    }
                    
                    for att in all_attachments:
                        if not att.content_type:
                            continue
                        
                        # Strip charset and other parameters from MIME type
                        mime_type = att.content_type.split(";")[0].strip()
                        
                        # Check if attachment type is supported
                        is_supported = False
                        for mime_prefix in supported_mimes.keys():
                            if mime_type == mime_prefix or mime_type.startswith(mime_prefix.rstrip("/")):
                                is_supported = True
                                break
                        
                        if is_supported:
                            try:
                                att_bytes = await att.read()
                                parts.append(Part.from_bytes(data=att_bytes, mime_type=mime_type))
                            except Exception as e:
                                print(f"Failed to read attachment {att.filename}: {e}")
                                continue

                if cleaned:
                    parts.append(cleaned)

                resp = await asyncio.to_thread(chat.send_message, parts)

                # check for empty response
                if not resp.candidates:
                    await message.channel.send("Ok Bot didn't respond. Try again.")
                    return

                text_buffer = []
                for part in resp.candidates[0].content.parts:
                    if getattr(part, "text", None):
                        text_buffer.append(part.text)

                if text_buffer:
                    full_text = "\n".join(text_buffer).strip()
                    
                    if not full_text:
                        await message.channel.send("Ok Bot generated an empty response. Try again.")
                        return

                    def chunk_text(text: str, max_len: int = 2000):
                        # Try to chunk by paragraph (double newlines), then by single newlines,
                        # and finally by character slices if needed.
                        if not text:
                            return []
                        chunks = []
                        paragraphs = text.split("\n\n")
                        for para in paragraphs:
                            if not para:
                                # preserve blank paragraphs as a newline
                                if chunks and len(chunks[-1]) + 2 <= max_len:
                                    chunks[-1] += "\n\n"
                                else:
                                    chunks.append("\n\n")
                                continue

                            # If current paragraph is small enough, try to append to last chunk
                            if chunks and len(chunks[-1]) + 2 + len(para) <= max_len:
                                chunks[-1] = chunks[-1] + "\n\n" + para
                                continue

                            # Paragraph alone fits
                            if len(para) <= max_len:
                                chunks.append(para)
                                continue

                            # Paragraph too large: split by single newlines
                            lines = para.split("\n")
                            current = ""
                            for line in lines:
                                if not line:
                                    candidate = current + "\n"
                                else:
                                    candidate = current + ("\n" if current else "") + line

                                if len(candidate) <= max_len:
                                    current = candidate
                                else:
                                    if current:
                                        chunks.append(current)
                                    # line itself may be longer than max_len -> slice it
                                    if len(line) > max_len:
                                        start = 0
                                        while start < len(line):
                                            chunks.append(line[start:start + max_len])
                                            start += max_len
                                        current = ""
                                    else:
                                        current = line

                            if current:
                                chunks.append(current)

                        return chunks

                    for chunk in chunk_text(full_text, 2000):
                        if chunk.strip():
                            try:
                                await message.channel.send(chunk)
                            except discord.errors.HTTPException as e:
                                print(f"Failed to send chunk: {e}")
                                await message.channel.send("Failed to send message. Try again.")
                                raise

                # Save updated, trimmed history (including all system & model/user turns)
                new_hist = chat.get_history()
                chat_history[chan_id] = jsonpickle.encode({"history": new_hist, "timestamp": now}, True)
                await update_data("chathistory", chat_history)
            except genai.errors.ClientError as e:
                print(f"Gemini API error: {e}")
                if "400" in str(e):
                    await message.channel.send("Ok Bot has reached its quota limit. Please try again later.")
                elif "429" in str(e):
                    await message.channel.send("The file you attatched is too large or you exceeded Ok Bot's quota limit. Please Try again.")
                else:
                    await message.channel.send("API error occurred. Please try again later.")
            except Exception as e:
                print(f"Unexpected error in generate_response: {e}")
                if "503" in str(e) or "overloaded" in str(e).lower():
                    await message.channel.send("The model is overloaded. Please try again later.")
                else:
                    await message.channel.send("An unexpected error occurred. Please try again.")
            finally:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass
            await self.bot.process_commands(message)

        chan_id = str(message.channel.id)
        # Cancel any previous generation in this channel
        prev_task = self.generation_tasks.get(chan_id)
        if prev_task and not prev_task.done():
            prev_task.cancel()
        # Start new generation task
        task = asyncio.create_task(generate_response())
        self.generation_tasks[chan_id] = task
        
    @commands.slash_command(description="Stop Ok Bot's response in this channel",guild_ids=GUILD_IDS)
    async def stop(self, ctx):
        chan_id = str(ctx.channel.id)
        task = self.generation_tasks.get(chan_id)
        if task and not task.done():
            task.cancel()
            await ctx.respond("Ok Bot's response has been stopped.")
        else:
            await ctx.respond("No active response to stop in this channel.")

    @commands.slash_command(description="Clear chat history with Ok Bot")
    async def clear(self, ctx):
        import time
        chat_history = await get_data("chathistory")
        cid = str(ctx.channel.id)

        if cid in chat_history:
            # Clear history without reinserting system instruction or bot response
            chat_history[cid] = jsonpickle.encode({"history": [], "timestamp": time.time()}, True)
            await update_data("chathistory", chat_history)
            await ctx.respond("Chat history for this channel has been cleared.")
        else:
            await ctx.respond("No chat history found for this channel.")


def setup(bot):
    bot.add_cog(Fun(bot))
