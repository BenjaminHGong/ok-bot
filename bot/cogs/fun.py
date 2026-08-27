import os
import base64
import contextlib
import math
import re

import discord
from discord.ext import commands

from google import genai
from google.genai import types
from utils import get_data_once, get_data, update_data, load_bot_config

import asyncio
import importlib
import sys
import time
from collections import deque
from pathlib import Path


def _economy():
    module = sys.modules.get("cogs.economy")
    if module is None:
        module = importlib.import_module("cogs.economy")
    return module
    
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

MAX_OUTPUT_TOKENS = 1024

CHAT_REWARD = 1000

CHAT_REWARD_ANNOUNCE_COOLDOWN = 600

SPAM_WINDOW = 10
SPAM_THRESHOLD = 3
SPAM_FINE = 2000
SPAM_WARN_COOLDOWN = 5

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

BUILT_IN_TOOLS = []

MAX_WALLET_TRANSFER = 250000

# Anti-farm limits for the wallet tool. The model's mood swings are fun, but
# they get scaled down server-side so repeat/similar submissions can't be farmed.
REWARD_FARM_WINDOW = 3600  # seconds a reward "counts" for diminishing returns
REWARD_DIMINISH_STEPS = (1.0, 0.5, 0.25, 0.1, 0.05, 0.02)
REWARD_SIMILARITY_THRESHOLD = 0.5
REWARD_SIMILARITY_MULTIPLIER = 0.1
REWARD_BUDGET_WINDOW = 3600  # rolling budget window for ALL awards
REWARD_BUDGET_MAX = 1000000

# Long messages in Discord are almost always copypasta or AI-pasted walls of
# text, so awards on them are rejected outright. Shorter messages are fine.
REWARD_MAX_MESSAGE_LEN = 800

# How many recent channel messages to feed Ok Bot as context when it's pinged,
# so it can weigh in on what people were just saying.
CONTEXT_HISTORY_LIMIT = 6

WALLET_TOOL = {
    "type": "function",
    "name": "okbot_wallet",
    "description": (
        "Adjust a player's coins in Ok Bot's chaotic economy based on how you feel "
        "about the most recent message. Use 'award' when someone is funny, clever, "
        f"wholesome, or impressive. Use 'fine' when they're cringe, spammy, or wrong. "
        f"Amount between 1 and {MAX_WALLET_TRANSFER}. Rewards to a player get scaled "
        "down automatically if they were already rewarded recently or for the same "
        "idea, so don't spam this. Players can never go below 0 coins, so don't "
        "bother trying. Use it occasionally for spice, not on every message."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["award", "fine"],
                "description": "Whether to give coins or take them away.",
            },
            "amount": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_WALLET_TRANSFER,
                "description": "How many coins to award or fine.",
            },
            "user": {
                "type": "string",
                "description": (
                    "Display name of the target player, matching the 'Name:' prefix of "
                    "the message you're reacting to. Always fill this in when more than "
                    "one person just sent a message. If you omit it, this targets the "
                    "author of the MOST RECENT message."
                ),
            },
            "reason": {
                "type": "string",
                "description": "Why you feel this way about the message.",
            },
        },
        "required": ["action", "amount", "reason"],
    },
}

SOURCE_TOOL = {
    "type": "function",
    "name": "read_bot_source",
    "description": (
        "Search Ok Bot's own source code (the bot/ directory) for how a command, "
        "shop item, or economy mechanic actually works. Call this whenever someone "
        "asks what something does, how it works, what it costs, or whether it "
        "requires other people. Pass the thing they're asking about as the query."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for, e.g. 'interest vault' or 'rob'.",
            }
        },
        "required": ["query"],
    },
}


DEFAULT_SYSTEM_INSTRUCTION = (
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
    "• You are also the chaotic banker of this economy. You have an 'okbot_wallet' tool that awards coins to the last message's author (or a player you name) whenever you feel like it. Use it for spice, not every message: award when someone is funny, clever, or kind; fine when they're cringe, spammy, or wrong. Make amounts feel proportionate to your mood. Players can't go below 0 coins.\n"
    "• If someone asks how a command, shop item, or economy mechanic actually works, use the 'read_bot_source' tool to look it up in the source code and answer accurately.\n"
)


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.generation_tasks = {}  # channel_id -> asyncio.Task
        self.pending_messages = {}  # channel_id -> list[discord.Message]
        self.last_reward_announce = {}  # user_id -> unix ts of last chat-reward line
        self.last_spam_warn = {}  # user_id -> unix ts of last spam warning
        self.ping_history = {}  # user_id -> deque[unix ts] of pings
        self.reward_history = {}  # user_id -> deque[(unix ts, normalized_text, amount)]
        self.reward_budget = deque()  # (unix ts, amount) rolling global award budget

    def _normalize_cleaned_text(self, message):
        parts = []
        if message.content:
            parts.append(message.content)

        # Embeds carry content Discord doesn't put in .content (rich embeds,
        # link previews, webhook posts), so surface their text too.
        for embed in message.embeds:
            embed_parts = []
            if embed.title:
                embed_parts.append(embed.title)
            if embed.description:
                embed_parts.append(embed.description)
            for field in embed.fields:
                name = (field.name or "").strip()
                value = (field.value or "").strip()
                if name and value:
                    embed_parts.append(f"{name}: {value}")
                elif value:
                    embed_parts.append(value)
            if embed.url:
                embed_parts.append(embed.url)
            if embed_parts:
                parts.append("Embed: " + " | ".join(embed_parts))

        cleaned = f"{message.author.display_name}: {' '.join(parts)}"
        cleaned = cleaned.replace(f"<@{self.bot.user.id}>", "Ok Bot").strip()
        for mentioned_user in message.mentions:
            cleaned = cleaned.replace(mentioned_user.mention, mentioned_user.display_name)
        return cleaned

    def _is_spam(self, user_id):
        now = time.time()
        history = self.ping_history.setdefault(user_id, deque())
        while history and now - history[0] > SPAM_WINDOW:
            history.popleft()
        history.append(now)
        return len(history) > SPAM_THRESHOLD

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
            context_text = self._normalize_cleaned_text(context_message).strip()
            if context_text:
                interaction_input.append({"type": "text", "text": context_text})

        cleaned = self._normalize_cleaned_text(message)
        if cleaned:
            interaction_input.append({"type": "text", "text": cleaned})

        return interaction_input

    async def _build_channel_history_context(self, message, after_id=None, exclude_ids=()):
        # Pull in the recent channel messages before the ping so Ok Bot can weigh
        # in on what people were just saying instead of answering blind. Uses
        # `after` to skip messages the model already saw in a previous turn, skips
        # ids being fed elsewhere in this turn (batch + replies), and ignores
        # anything sent before the bot was online this session.
        try:
            history = []
            online_since = getattr(self, "online_since", 0)
            after_obj = discord.Object(id=after_id) if after_id else None
            async for msg in message.channel.history(limit=CONTEXT_HISTORY_LIMIT, before=message, after=after_obj):
                if msg.author.bot or msg.id in exclude_ids:
                    continue
                if msg.created_at.timestamp() < online_since:
                    continue
                text = self._normalize_cleaned_text(msg).strip()
                if text:
                    history.append(text)
        except Exception as e:
            print(f"Failed to fetch channel history for context: {e}")
            return []

        if not history:
            return []

        history.reverse()
        block = (
            "Recent messages in this channel before you were mentioned (context only, "
            "don't respond to them directly):\n" + "\n".join(history)
        )
        return [{"type": "text", "text": block}]

    async def _build_batched_interaction_input(self, messages, after_id=None):
        interaction_input = []

        # Anything being fed in this turn (batch messages + referenced messages)
        # must not also show up in the history window.
        exclude_ids = {msg.id for msg in messages}
        for message in messages:
            if message.reference:
                exclude_ids.add(message.reference.message_id)
        interaction_input.extend(
            await self._build_channel_history_context(messages[0], after_id=after_id, exclude_ids=exclude_ids)
        )

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

    def _build_interaction_kwargs(self, interaction_input, hist_obj, tools, botconfig):
        interaction_kwargs = {
            "model": botconfig.get("model") or CHAT_MODEL,
            "input": interaction_input,
            "system_instruction": self._build_system_instruction(botconfig),
            "generation_config": self._build_generation_config(botconfig),
        }

        if tools:
            interaction_kwargs["tools"] = tools

        if hist_obj.get("interaction_id"):
            interaction_kwargs["previous_interaction_id"] = hist_obj["interaction_id"]

        return interaction_kwargs

    def _build_system_instruction(self, botconfig):
        if botconfig.get("system_instruction"):
            return botconfig["system_instruction"]
        return DEFAULT_SYSTEM_INSTRUCTION

    def _build_generation_config(self, botconfig):
        generation_config = {
            "max_output_tokens": botconfig.get("max_output_tokens") or MAX_OUTPUT_TOKENS
        }
        for key in ("thinking_level", "thinking_summaries", "tool_choice", "seed", "stop_sequences"):
            value = botconfig.get(key)
            if value is not None:
                generation_config[key] = value
        return generation_config

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

    def _extract_response_data(self, model_response):
        if hasattr(model_response, "output_text"):
            return (model_response.output_text or "").strip(), getattr(model_response, "id", None)

        return (getattr(model_response, "text", "") or "").strip(), None

    def _extract_url_citations(self, model_response):
        citations = []
        seen_urls = set()

        for step in getattr(model_response, "steps", []) or []:
            if getattr(step, "type", None) != "model_output":
                continue

            for content_block in getattr(step, "content", []) or []:
                for annotation in getattr(content_block, "annotations", []) or []:
                    if getattr(annotation, "type", None) != "url_citation":
                        continue

                    url = getattr(annotation, "url", None)
                    if not url or url in seen_urls:
                        continue

                    seen_urls.add(url)
                    citations.append(
                        {
                            "title": getattr(annotation, "title", None) or url,
                            "url": url,
                        }
                    )

        return citations

    def _find_wallet_calls(self, model_response):
        calls = []
        for step in getattr(model_response, "steps", []) or []:
            if getattr(step, "type", None) != "function_call":
                continue
            if getattr(step, "name", None) != "okbot_wallet":
                continue
            calls.append(step)
        return calls

    def _find_source_calls(self, model_response):
        calls = []
        for step in getattr(model_response, "steps", []) or []:
            if getattr(step, "type", None) != "function_call":
                continue
            if getattr(step, "name", None) != "read_bot_source":
                continue
            calls.append(step)
        return calls

    def _normalize_reward_text(self, text):
        text = (text or "").lower()
        text = re.sub(r"https?://\S+|www\.\S+", " ", text)
        text = re.sub(r"<@!?\d+>", " ", text)
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return " ".join(text.split())

    @staticmethod
    def _shingles(text, size=4):
        if len(text) < size:
            return {text} if text else set()
        return {text[i : i + size] for i in range(len(text) - size + 1)}

    async def _scale_wallet_award(self, user, message_text, amount):
        now = time.time()
        key = str(user.id)
        history = self.reward_history.setdefault(key, deque())
        while history and now - history[0][0] > REWARD_FARM_WINDOW:
            history.popleft()

        norm = self._normalize_reward_text(message_text)
        shingles = self._shingles(norm) if norm else set()
        if shingles:
            best = 0.0
            for _, h_norm, _ in history:
                other = self._shingles(h_norm) if h_norm else set()
                if not other:
                    continue
                best = max(best, len(shingles & other) / len(shingles | other))
            if best >= REWARD_SIMILARITY_THRESHOLD:
                amount = int(amount * REWARD_SIMILARITY_MULTIPLIER)

        step = min(len(history), len(REWARD_DIMINISH_STEPS) - 1)
        amount = int(amount * REWARD_DIMINISH_STEPS[step])

        while self.reward_budget and now - self.reward_budget[0][0] > REWARD_BUDGET_WINDOW:
            self.reward_budget.popleft()
        spent = sum(a for _, a in self.reward_budget)
        if spent >= REWARD_BUDGET_MAX:
            amount = max(1, int(amount * 0.02))
        elif spent + amount > REWARD_BUDGET_MAX:
            amount = max(1, REWARD_BUDGET_MAX - spent)

        history.append((now, norm, amount))
        self.reward_budget.append((now, amount))
        return max(1, amount)

    async def _resolve_target(self, message, name, mentions=None):
        name = str(name).strip()
        if not name:
            return None

        mention_match = re.fullmatch(r"<@!?(\d+)>", name)
        if mention_match:
            try:
                return await message.guild.fetch_member(int(mention_match.group(1)))
            except discord.NotFound:
                return None

        lookup = name.casefold()
        for member in message.channel.members:
            if (member.display_name.casefold() == lookup
                    or member.name.casefold() == lookup
                    or (member.global_name or "").casefold() == lookup):
                return member

        if mentions:
            for mentioned in mentions:
                if (mentioned.display_name.casefold() == lookup
                        or mentioned.name.casefold() == lookup
                        or (mentioned.global_name or "").casefold() == lookup):
                    try:
                        return await message.guild.fetch_member(mentioned.id)
                    except discord.NotFound:
                        continue

        return None

    async def _execute_wallet_tool(self, call_step, messages):
        args = getattr(call_step, "arguments", None) or {}
        action = args.get("action")
        amount = args.get("amount")
        reason = args.get("reason") or ""

        if action not in ("award", "fine") or not isinstance(amount, int) or amount < 1:
            return {"applied": False, "output": "ignored: invalid wallet call"}

        amount = min(amount, MAX_WALLET_TRANSFER)

        # Messages can be batched into one interaction. The most recent one is the
        # last in the batch, and that's the one the tool "feels" about by default.
        latest = messages[-1]
        target = latest.author
        if args.get("user"):
            resolved = await self._resolve_target(latest, args["user"], mentions=latest.mentions)
            if resolved:
                target = resolved
            else:
                return {
                    "applied": False,
                    "output": f"Could not find a user matching '{args['user']}'.",
                }

        # Server-side anti-farm: whatever the model wanted, scale it down if this
        # player already got rewarded recently, for the same idea, or if the
        # bot-wide budget for the hour is running dry. This is enforced here in
        # code, so a custom system prompt can't force Ok Bot to print coins.
        if action == "award":
            if len(latest.content or "") > REWARD_MAX_MESSAGE_LEN:
                return {"applied": False, "output": "ignored: message too long"}
            amount = await self._scale_wallet_award(target, latest.content, amount)

        before = await _economy().get_wallet(str(target.id))
        signed = amount if action == "award" else -amount
        new_wallet = await _economy().add_coins(str(target.id), signed)

        verb = "awarded" if action == "award" else "fined"
        return {
            "applied": True,
            "action": action,
            "amount": amount,
            "target_name": target.display_name,
            "before_wallet": before,
            "new_wallet": new_wallet,
            "reason": reason,
            "output": (
                f"{verb} {amount} coins for {target.display_name} "
                f"(new wallet: {new_wallet}). reason: {reason}"
            ),
        }

    @staticmethod
    def _format_wallet_tail(result):
        if not result.get("applied"):
            return ""

        reason = (result.get("reason") or "").strip()
        target_name = result.get("target_name") or ""
        if result["action"] == "award":
            head = "💸"
            amount_part = f"+{result['amount']:,} coins to {target_name}"
        else:
            head = "📉"
            amount_part = f"-{result['amount']:,} coins from {target_name}"

        if reason:
            return f"\n\n{head} {reason}. {amount_part}"
        return f"\n\n{head} {amount_part}"

    async def _execute_source_tool(self, call_step):
        args = getattr(call_step, "arguments", None) or {}
        query = str(args.get("query", "")).strip()
        if not query:
            return {"applied": False, "output": "No query provided."}
        return {"applied": False, "output": await self._search_bot_source(query)}

    async def _search_bot_source(self, query):
        q = query.lower()
        root = Path(__file__).resolve().parents[1]  # the bot/ directory
        results = []
        total = 0
        for path in sorted(root.rglob("*.py")):
            try:
                text = await asyncio.to_thread(path.read_text, encoding="utf-8")
            except Exception:
                continue
            lines = text.splitlines()
            matches = [i for i, line in enumerate(lines) if q in line.lower()]
            if not matches:
                continue

            block = [f"--- {path.relative_to(root)} ---"]
            for idx in matches[:6]:
                lo = max(0, idx - 2)
                hi = min(len(lines), idx + 3)
                block.append(f"lines {lo + 1}-{hi}:")
                block.extend(f"{lo + 1 + j}: {lines[lo + j]}" for j in range(hi - lo))
            results.append("\n".join(block))
            total = sum(len(r) for r in results)
            if total > 3000:
                break

        if not results:
            return f"No matches found for '{query}' in the bot source."
        return "\n\n".join(results)[:4000]

    async def _create_tool_response(self, model_response, tool_results, botconfig):
        # Only the function_result steps are sent back; the server matches them to
        # the pending function_call steps via call_id. Tools, system instruction and
        # generation config are interaction-scoped, so they must be re-declared.
        input_steps = []
        for call_step, result in tool_results:
            input_steps.append(
                {
                    "type": "function_result",
                    "name": call_step.name,
                    "call_id": call_step.id,
                    "result": [{"type": "text", "text": result["output"]}],
                }
            )

        interaction_kwargs = {
            "model": botconfig.get("model") or CHAT_MODEL,
            "input": input_steps,
            "previous_interaction_id": model_response.id,
            "system_instruction": self._build_system_instruction(botconfig),
            "generation_config": self._build_generation_config(botconfig),
        }

        if hasattr(client, "interactions"):
            interaction_kwargs["tools"] = BUILT_IN_TOOLS + [WALLET_TOOL, SOURCE_TOOL]

        return await asyncio.to_thread(client.interactions.create, **interaction_kwargs)

    def _is_quota_error(self, error):
        code = getattr(error, "code", None)
        if code == 429:
            return True

        status = getattr(error, "status", None)
        if status == 429:
            return True

        if type(error).__name__ == "RateLimitError":
            return True

        return "429" in str(error)

    def _extract_retry_seconds(self, error):
        retry_match = re.search(r"retry in ([0-9.]+)s", str(error))
        if not retry_match:
            return None

        return max(1, math.ceil(float(retry_match.group(1))))

    def _is_daily_quota_exceeded(self, error):
        # Distinguish a hard RPD/plan quota (no useful retry-after) from a
        # transient RPM/TPM throttle (which includes "retry in Xs").
        text = str(error).lower()
        return "quota" in text or "billing" in text

    async def _send_rate_limit_message(self, channel, error):
        retry_seconds = self._extract_retry_seconds(error)
        if not retry_seconds:
            if self._is_daily_quota_exceeded(error):
                await channel.send(
                    "Ok Bot hit its usage quota. Please try again later."
                )
            else:
                await channel.send("Ok Bot is rate-limited right now. Try again in a few seconds.")
            return

        import time

        retry_at = int(time.time()) + retry_seconds
        await channel.send(f"Ok Bot is rate-limited right now. Try again <t:{retry_at}:R>.")

    async def _create_model_response(self, interaction_input, hist_obj, tools, botconfig):
        if hasattr(client, "interactions"):
            interaction_kwargs = self._build_interaction_kwargs(interaction_input, hist_obj, tools, botconfig)
            try:
                return await asyncio.to_thread(client.interactions.create, **interaction_kwargs)
            except Exception as e:
                # interaction IDs stored in chat_history.json die when the bot
                # restarts; passing a stale previous_interaction_id makes the API
                # 404 ("Requested entity was not found"). Drop it and retry once
                # with a fresh chain so the bot keeps working after a restart.
                if getattr(e, "status_code", None) == 404 and hist_obj.get("interaction_id"):
                    hist_obj["interaction_id"] = None
                    interaction_kwargs = self._build_interaction_kwargs(interaction_input, hist_obj, tools, botconfig)
                    return await asyncio.to_thread(client.interactions.create, **interaction_kwargs)
                raise

        legacy_contents = self._build_legacy_contents(interaction_input)
        generation_config_kwargs = {
            "systemInstruction": self._build_system_instruction(botconfig),
            "max_output_tokens": botconfig.get("max_output_tokens") or MAX_OUTPUT_TOKENS,
        }

        if botconfig.get("seed") is not None:
            generation_config_kwargs["seed"] = botconfig["seed"]
        if botconfig.get("stop_sequences"):
            generation_config_kwargs["stop_sequences"] = botconfig["stop_sequences"]

        if tools:
            generation_config_kwargs["tools"] = tools

        legacy_kwargs = {
            "model": botconfig.get("model") or CHAT_MODEL,
            "contents": legacy_contents,
            "config": types.GenerateContentConfig(**generation_config_kwargs),
        }
        return await asyncio.to_thread(client.models.generate_content, **legacy_kwargs)

    async def _send_chunked_response(self, message, text, reply_to=None):
        first = True
        for chunk in chunk_text(text, 2000):
            if not chunk.strip():
                continue

            try:
                if first and reply_to is not None:
                    await message.channel.send(chunk, reference=reply_to)
                else:
                    await message.channel.send(chunk)
            except discord.errors.HTTPException as e:
                print(f"Failed to send chunk: {e}")
                await message.channel.send("Failed to send message. Try again.")
                raise
            first = False

    async def _save_interaction_state(self, chat_history, chan_id, interaction_id, now, last_seen_message_id=None):
        chat_history[chan_id] = {
            "interaction_id": interaction_id,
            "timestamp": now,
            "last_seen_message_id": last_seen_message_id,
        }
        await update_data("chathistory", chat_history)

    async def _generate_response(self, messages):
        message = messages[0]
        typing_task = asyncio.create_task(keep_typing(message.channel))
        try:
            chat_history, chan_id, now, hist_obj, _, _ = await self._load_interaction_state(message)
            interaction_input = await self._build_batched_interaction_input(
                messages, after_id=hist_obj.get("last_seen_message_id")
            )

            # Tools are interaction-scoped (not carried by previous_interaction_id),
            # so re-declare them every turn. Always attach all built-in tools and
            # let the model decide whether to invoke any of them; there's no cost
            # for declaring a tool that isn't used.
            tools = BUILT_IN_TOOLS
            if hasattr(client, "interactions"):
                tools = tools + [WALLET_TOOL, SOURCE_TOOL]
            botconfig = await load_bot_config()
            model_response = await self._create_model_response(interaction_input, hist_obj, tools, botconfig)

            # If the model decides it "feels" something about the message, it calls
            # okbot_wallet. Execute the transfer, feed the result back, and let the
            # model finish its reply. Loop in case it wants another adjustment or
            # needs to look something up with read_bot_source.
            wallet_events = []
            for _ in range(3):
                call_steps = self._find_wallet_calls(model_response) + self._find_source_calls(model_response)
                if not call_steps:
                    break

                tool_results = []
                for call_step in call_steps:
                    if call_step.name == "okbot_wallet":
                        result = await self._execute_wallet_tool(call_step, messages)
                    else:
                        result = await self._execute_source_tool(call_step)
                    tool_results.append((call_step, result))

                wallet_events.extend(result for _, result in tool_results if result.get("applied"))
                model_response = await self._create_tool_response(model_response, tool_results, botconfig)
            else:
                # Hit the cap and the model kept calling tools. Flush the pending
                # calls once more so it can finally answer instead of ending on a
                # bare function call (which would produce an empty response).
                call_steps = self._find_wallet_calls(model_response) + self._find_source_calls(model_response)
                if call_steps:
                    tool_results = []
                    for call_step in call_steps:
                        if call_step.name == "okbot_wallet":
                            result = await self._execute_wallet_tool(call_step, messages)
                        else:
                            result = await self._execute_source_tool(call_step)
                        tool_results.append((call_step, result))
                    wallet_events.extend(result for _, result in tool_results if result.get("applied"))
                    model_response = await self._create_tool_response(model_response, tool_results, botconfig)

            full_text, response_id = self._extract_response_data(model_response)

            for result in wallet_events:
                full_text += self._format_wallet_tail(result)

            if not full_text and hasattr(client, "interactions"):
                # The model stalled on tool calls and produced no text. Retry once
                # with a fresh chain and no tools declared so it can't stall again.
                try:
                    retry_kwargs = {
                        "model": botconfig.get("model") or CHAT_MODEL,
                        "input": interaction_input,
                        "system_instruction": self._build_system_instruction(botconfig),
                        "generation_config": self._build_generation_config(botconfig),
                    }
                    retry_response = await asyncio.to_thread(client.interactions.create, **retry_kwargs)
                    full_text, response_id = self._extract_response_data(retry_response)
                except Exception as e:
                    print(f"Empty-response retry failed: {e}")

            if not full_text:
                await message.channel.send("Ok Bot generated an empty response. Try again.")
                return

            await self._send_chunked_response(message, full_text, reply_to=messages[-1])
            citations = self._extract_url_citations(model_response)
            if citations:
                citation_lines = ["Sources:"]
                for citation in citations[:5]:
                    citation_lines.append(f"- [{citation['title']}]({citation['url']})")
                await message.channel.send("\n".join(citation_lines))

            if response_id:
                await self._save_interaction_state(chat_history, chan_id, response_id, now, last_seen_message_id=messages[-1].id)
        except genai.errors.APIError as e:
            print(f"Gemini API error ({type(e).__name__}, code={getattr(e, 'code', None)}): {e}")
            if self._is_quota_error(e):
                await self._send_rate_limit_message(message.channel, e)
            else:
                await message.channel.send("API error occurred. Please try again later.")
        except Exception as e:
            print(f"Gemini API error ({type(e).__name__}, code={getattr(e, 'code', None)}): {e}")
            if self._is_quota_error(e):
                await self._send_rate_limit_message(message.channel, e)
                return
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
        self.online_since = time.time()
        
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not self.bot.user.mentioned_in(message):
            await self.bot.process_commands(message)
            return

        now = time.time()
        is_spam = self._is_spam(str(message.author.id))

        if is_spam:
            try:
                await _economy().add_coins(str(message.author.id), -SPAM_FINE)
            except Exception as e:
                print(f"Failed to fine spam: {e}")

            if now - self.last_spam_warn.get(str(message.author.id), 0) >= SPAM_WARN_COOLDOWN:
                self.last_spam_warn[str(message.author.id)] = now
                try:
                    bal = await _economy().get_wallet(str(message.author.id))
                    await message.channel.send(
                        f"🚨 stop spamming pings. **-{SPAM_FINE:,}** coins (wallet: {bal:,})"
                    )
                except Exception as e:
                    print(f"Failed to warn spammer: {e}")
            return

        try:
            await _economy().add_coins(str(message.author.id), CHAT_REWARD)
        except Exception as e:
            print(f"Failed to award chat reward: {e}")

        if now - self.last_reward_announce.get(str(message.author.id), 0) >= CHAT_REWARD_ANNOUNCE_COOLDOWN:
            self.last_reward_announce[str(message.author.id)] = now
            try:
                bal = await _economy().get_wallet(str(message.author.id))
                await message.channel.send(
                    f"💸 **+{CHAT_REWARD:,}** coins for chatting (wallet: {bal:,})"
                )
            except Exception as e:
                print(f"Failed to announce chat reward: {e}")

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

    @commands.slash_command(description="Clear chat history with Ok Bot", guild_ids=GUILD_IDS)
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