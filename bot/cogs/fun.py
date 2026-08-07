import os
import base64
import contextlib

import discord
from discord.ext import commands

from google import genai
from google.genai import types
from utils import get_data_once, get_data, update_data

import asyncio
    
async def keep_typing(channel):
    while True:
        await channel.trigger_typing()
        await asyncio.sleep(4)  # re-trigger every 4 seconds


def chunk_text(text: str, max_len: int = 2000):
    if not text:
        return []

    chunks = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) <= max_len:
            current += line
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(line) <= max_len:
            current = line
            continue

        start = 0
        while start < len(line):
            chunks.append(line[start:start + max_len])
            start += max_len

    if current:
        chunks.append(current)

    return chunks

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

CHAT_MODEL = "gemini-3.5-flash-lite"

GUILD_IDS = get_data_once("guilds")

SUPPORTED_MIME_TYPES = {
    "image/png": "image",
    "image/jpeg": "image",
    "image/webp": "image",
    "application/pdf": "document",
    "text/plain": "document",
    "video/x-flv": "video",
    "video/quicktime": "video",
    "video/mpeg": "video",
    "video/mpegs": "video",
    "video/mpg": "video",
    "video/mp4": "video",
    "video/webm": "video",
    "video/wmv": "video",
    "video/3gpp": "video",
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


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.generation_tasks = {}  # channel_id -> asyncio.Task
        self.pending_messages = {}  # channel_id -> list[discord.Message]

    def _normalize_cleaned_text(self, message):
        cleaned = ""
        cleaned += f"{message.author.display_name}: {message.content}"
        cleaned = cleaned.replace(f"<@{self.bot.user.id}>", "Ok Bot").strip()
        for mentioned_user in message.mentions:
            cleaned = cleaned.replace(mentioned_user.mention, mentioned_user.display_name)
        return cleaned

    async def _attachment_to_interaction_item(self, attachment):
        if not attachment.content_type:
            return None

        mime_type = attachment.content_type.split(";")[0].strip()
        item_type = None
        for mime_prefix, mapped_type in SUPPORTED_MIME_TYPES.items():
            if mime_type == mime_prefix or mime_type.startswith(mime_prefix.rstrip("/")):
                item_type = mapped_type
                break

        if not item_type:
            return None

        try:
            att_bytes = await attachment.read()
        except Exception as e:
            print(f"Failed to read attachment {attachment.filename}: {e}")
            return None

        return {
            "type": item_type,
            "data": base64.b64encode(att_bytes).decode("utf-8"),
            "mime_type": mime_type,
        }

    async def _build_interaction_input(self, message, context_message, context_attachments):
        interaction_input = []

        for att in list(context_attachments) + list(message.attachments):
            interaction_item = await self._attachment_to_interaction_item(att)
            if interaction_item:
                interaction_input.append(interaction_item)

        if context_message:
            context_text = f"{context_message.author.display_name}: {context_message.content}".strip()
            if context_text:
                interaction_input.append({"type": "text", "text": context_text})

        cleaned = self._normalize_cleaned_text(message)
        if cleaned:
            interaction_input.append({"type": "text", "text": cleaned})

        return interaction_input

    async def _build_batched_interaction_input(self, messages):
        interaction_input = []

        for message in messages:
            context_message = None
            context_attachments = []
            if message.reference:
                context_message = await message.channel.fetch_message(message.reference.message_id)
                context_attachments = context_message.attachments

            interaction_input.extend(
                await self._build_interaction_input(message, context_message, context_attachments)
            )

        return interaction_input

    async def _load_interaction_state(self, message):
        import time

        chat_history = await get_data("chathistory")
        chan_id = str(message.channel.id)
        now = time.time()
        if chan_id not in chat_history:
            chat_history[chan_id] = {"interaction_id": None, "timestamp": now}

        hist_obj = chat_history[chan_id]
        if "timestamp" not in hist_obj or now - hist_obj.get("timestamp", 0) > 86400:
            hist_obj = {"interaction_id": None, "timestamp": now}

        context_message = None
        context_attachments = []
        if message.reference:
            context_message = await message.channel.fetch_message(message.reference.message_id)
            context_attachments = context_message.attachments

        return chat_history, chan_id, now, hist_obj, context_message, context_attachments

    def _build_interaction_kwargs(self, interaction_input, hist_obj):
        interaction_kwargs = {
            "model": CHAT_MODEL,
            "input": interaction_input,
            "system_instruction": (
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
                "• When asked any STEM-related questions, comply with their question with a nerdy response.\n"
                "• You can still answer the user’s request normally if they’re clearly asking for help, but do it with a reluctant, slightly sarcastic tone, like you’re doing it against your will.\n"
                "• Use meme-coded shorthand like 'L', 'skill issue', 'ok bud', 'mald', 'sus', 'wtf', 'wat', 'omg', 'real', 'GG', etc., but don’t spam them.\n"
                "• If something changes dramatically, you can respond emotionally in all caps or end with exclamation spam like 'omg!!??!1!1!', but keep being unserious.\n"
                "• If appropriate, make random typos similar to the user when they talk. Try to learn and use their humor and use it if it has been used enough.\n"
            ),
        }

        if hist_obj.get("interaction_id"):
            interaction_kwargs["previous_interaction_id"] = hist_obj["interaction_id"]

        return interaction_kwargs

    def _build_legacy_contents(self, interaction_input):
        contents = []
        text_parts = []
        multimodal_types = {"image", "document", "audio", "video"}

        for item in interaction_input:
            item_type = item.get("type")
            if item_type == "text":
                text_parts.append(item.get("text", ""))
                continue

            if item_type in multimodal_types:
                contents.append(types.Part.from_bytes(data=base64.b64decode(item["data"]), mime_type=item["mime_type"]))

        if text_parts:
            contents.append("\n".join(part for part in text_parts if part).strip())

        return contents

    def _extract_response_text_and_id(self, model_response):
        if hasattr(model_response, "output_text"):
            return (model_response.output_text or "").strip(), getattr(model_response, "id", None)

        return (getattr(model_response, "text", "") or "").strip(), None

    async def _create_model_response(self, interaction_input, hist_obj):
        if hasattr(client, "interactions"):
            interaction_kwargs = self._build_interaction_kwargs(interaction_input, hist_obj)
            return await asyncio.to_thread(client.interactions.create, **interaction_kwargs)

        legacy_contents = self._build_legacy_contents(interaction_input)
        legacy_kwargs = {
            "model": CHAT_MODEL,
            "contents": legacy_contents,
        }
        return await asyncio.to_thread(client.models.generate_content, **legacy_kwargs)

    async def _send_chunked_response(self, message, text):
        for chunk in chunk_text(text, 2000):
            if not chunk.strip():
                continue

            try:
                await message.channel.send(chunk)
            except discord.errors.HTTPException as e:
                print(f"Failed to send chunk: {e}")
                await message.channel.send("Failed to send message. Try again.")
                raise

    async def _save_interaction_state(self, chat_history, chan_id, interaction_id, now):
        chat_history[chan_id] = {"interaction_id": interaction_id, "timestamp": now}
        await update_data("chathistory", chat_history)

    async def _generate_response(self, messages):
        message = messages[0]
        typing_task = asyncio.create_task(keep_typing(message.channel))
        try:
            chat_history, chan_id, now, hist_obj, _, _ = await self._load_interaction_state(message)
            interaction_input = await self._build_batched_interaction_input(messages)
            model_response = await self._create_model_response(interaction_input, hist_obj)

            full_text, response_id = self._extract_response_text_and_id(model_response)

            if not full_text:
                await message.channel.send("Ok Bot generated an empty response. Try again.")
                return

            await self._send_chunked_response(message, full_text)
            if response_id:
                await self._save_interaction_state(chat_history, chan_id, response_id, now)
        except genai.errors.ClientError as e:
            print(f"Gemini API error: {e}")
            if "400" in str(e):
                await message.channel.send("Ok Bot has reached its quota limit. Please try again later.")
            elif "429" in str(e):
                await message.channel.send("The file you attached is too large or you exceeded Ok Bot's quota limit. Please try again.")
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
            with contextlib.suppress(asyncio.CancelledError):
                await typing_task

    async def _process_pending_messages(self, chan_id):
        try:
            while True:
                await asyncio.sleep(0.75)
                queued_messages = self.pending_messages.get(chan_id, [])
                if not queued_messages:
                    return

                self.pending_messages[chan_id] = []
                await self._generate_response(queued_messages)

        finally:
            self.generation_tasks.pop(chan_id, None)
            self.pending_messages.pop(chan_id, None)
    
    @commands.Cog.listener()
    async def on_connect(self):
        print("Fun commands loaded")
        
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not self.bot.user.mentioned_in(message):
            await self.bot.process_commands(message)
            return
        chan_id = str(message.channel.id)
        self.pending_messages.setdefault(chan_id, []).append(message)

        task = self.generation_tasks.get(chan_id)
        if not task or task.done():
            worker = asyncio.create_task(self._process_pending_messages(chan_id))
            self.generation_tasks[chan_id] = worker
        
    @commands.slash_command(description="Stop Ok Bot's response in this channel",guild_ids=GUILD_IDS)
    async def stop(self, ctx):
        chan_id = str(ctx.channel.id)
        task = self.generation_tasks.get(chan_id)
        if task and not task.done():
            task.cancel()
            self.pending_messages.pop(chan_id, None)
            await ctx.respond("Ok Bot's response has been stopped.")
        else:
            await ctx.respond("No active response to stop in this channel.")

    @commands.slash_command(description="Clear chat history with Ok Bot")
    async def clear(self, ctx):
        import time
        chat_history = await get_data("chathistory")
        cid = str(ctx.channel.id)

        task = self.generation_tasks.get(cid)
        if task and not task.done():
            task.cancel()

        self.pending_messages.pop(cid, None)

        chat_history[cid] = {"interaction_id": None, "timestamp": time.time()}
        await update_data("chathistory", chat_history)
        await ctx.respond("Chat history for this channel has been cleared.")


def setup(bot):
    bot.add_cog(Fun(bot))
