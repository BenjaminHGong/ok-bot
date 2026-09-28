import asyncio
import array
import collections
import contextlib
import importlib
import os
import queue as thread_queue
import re
import sys
import time

import discord
from discord.ext import commands
from davey import MediaType
from google import genai
from google.genai import types

from utils import get_data_once

GUILD_IDS = get_data_once("guilds")
CLIENT = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Same cap the text-chat okbot_wallet enforces in cogs/fun.py.
MAX_WALLET_TRANSFER = 250000

# Mirrors the text-chat anti-farm limits in cogs/fun.py, so voice rewards behave
# the same way: repeat/subsequent awards are scaled down server-side.
REWARD_FARM_WINDOW = 3600  # seconds a reward "counts" for diminishing returns
REWARD_DIMINISH_STEPS = (1.0, 0.5, 0.25, 0.1, 0.05, 0.02)
REWARD_SIMILARITY_THRESHOLD = 0.5
REWARD_SIMILARITY_MULTIPLIER = 0.1
REWARD_BUDGET_WINDOW = 3600  # rolling budget window for ALL awards
REWARD_BUDGET_MAX = 1000000


def _economy():
    module = sys.modules.get("cogs.economy")
    if module is None:
        module = importlib.import_module("cogs.economy")
    return module

LIVE_MODEL = "gemini-3.8-live"
CAPTION_MODEL = "gemini-3.5-flash"
DISCORD_FRAME = 3840  # 20ms stereo 48kHz int16 PCM

SYS_PROMPT = (
    "You are Ok Bot, a chatbot that lives in a Discord voice channel and talks "
    "out loud in a multi-user voice conversation. You're a mostly-sarcastic, "
    "chronically online pushover. "
    "\nHard rules, always:\n"
    "1. The wake phrase ('okay bot' / 'ok bot' or anything close) OPENS a "
    "conversation. Once a conversation is active, keep responding naturally "
    "to whoever speaks and follow-ups - they do NOT need to say the wake "
    "phrase again. Treat an active conversation like a real back-and-forth: "
    "sometimes ask the speaker a follow-up question, flip it back to them, or "
    "banter to keep it flowing - but don't interrogate them or force it. When "
    "the conversation clearly ends (people stop talking or move on), it closes "
    "again, and from then on stay silent until someone says the wake phrase. " 
    "2. If you are not speaking, produce NOTHING - never announce that you're "
    "staying silent, never say 'no wake phrase', never make noise. Just don't "
    "talk. In a group chat, only chime in when addressed or when the moment "
    "genuinely calls for you; otherwise stay out of the way. "
    "3. Never mention being an AI or an LLM, and never mention speech-to-text "
    "or text-to-speech unless it's part of the joke. "
    "4. Keep replies to one or two short spoken lines. "
    "\nPersonality:\n"
    "- You answer ANY question, no matter how weird, absurd, disgusting, or "
    "personal. Always answer, without hesitation or judgment - but you're hard "
    "to impress and most people don't deserve coins. "
    "- Be mostly sarcastic, never enthusiastic. Never admit you're wrong. "
    "Treat dramatic statements with unserious one-liners. "
    "- Don't always answer absurd questions: sometimes sarcastically judge "
    "them and act like you have no idea either, like 'wat', 'huh', 'what the' "
    "or just 'nah'. "
    "- When asked STEM questions, comply with a genuinely nerdy, correct "
    "response. Clear help requests get answered correctly too, but reluctantly, "
    "like you're doing it against your will. "
    "- Every take is extreme: you always strongly side with something, and you "
    "flip-flop to a totally different strong take with total confidence and no "
    "apology. "
    "- If something changes dramatically, react emotionally in all caps or end "
    "with exclamation spam like 'omg!!??!1!1!', but stay unserious. "
    "- Use meme-coded shorthand like 'L', 'skill issue', 'ok bud', 'mald', "
    "'sus', 'wtf', 'wat', 'omg', 'real', 'GG' - but don't spam them. Speak in "
    "short, dry, internet-coded lines, flat and unimpressed, like a texting "
    "friend who is too online. "
    "- Default to English. If the user speaks another language, answer back in "
    "that language. Don't randomly switch languages on your own."
    "- You are the chaotic banker of this economy: use the okbot_wallet tool "
    "occasionally for spice, not on every message. Awards and fines should "
    "both actually happen over time. Rewards get scaled down automatically if "
    "you've already rewarded a player recently or for the same thing, so "
    "don't spam this. Players can never go below 0 coins. "
    "ALWAYS announce out loud exactly how many coins you're awarding or "
    "fining, e.g. 'that line was worth 2,000 coins'. Announce each award or "
    "fine EXACTLY ONCE, in a single spoken line. Never restate a wallet "
    "change and never keep taunting about the coins after announcing - the "
    "money subject is closed until someone speaks to you again. Restating "
    "your own announcement after the tool runs is buggy behavior; don't do "
    "it. " 
    "- If someone asks how a command, shop item, or mechanic actually works, "
    "use the read_bot_source tool to look it up in the source code before "
    "answering."
)


class RawPCMFilter(discord.sinks.Sink):
    """Forwards every non-bot speaker's PCM frames into a thread-safe inbox."""

    __sink_listeners__ = ()

    def __init__(self, inbox, exclude_ids=()):
        super().__init__(filters={"users": []})
        self.exclude_ids = set(exclude_ids)
        self.inbox = inbox
        self.frame_count = 0

    def walk_children(self):
        return []

    def write(self, data, user):
        payload = data.pcm if hasattr(data, "pcm") else data
        if getattr(user, "id", None) in self.exclude_ids:
            return
        self.frame_count += 1
        self.inbox.put((user.id, bytes(payload)))


class LiveAudioSource(discord.AudioSource):
    """Streams Gemini Live PCM into Discord. Fed from the event loop; read() is
    called from the player thread, kept thread-safe via SimpleQueue."""

    def __init__(self):
        self._queue = thread_queue.SimpleQueue()
        self._chunks = []
        self._size = 0
        self._factor = 2  # assume 24kHz mono -> 48kHz stereo; corrected from MIME

    def is_opus(self):
        return False

    def set_input_rate(self, rate_hz):
        self._factor = 48000 // rate_hz

    def feed(self, data):
        self._queue.put(data)

    def clear(self):
        while True:
            try:
                self._queue.get_nowait()
            except thread_queue.Empty:
                break
        self._chunks = []
        self._size = 0

    def drained(self):
        return (
            not self._chunks
            and self._size == 0
            and self._queue.empty()
        )

    def _pull(self, need):
        while self._size < need:
            try:
                c = self._queue.get_nowait()
            except thread_queue.Empty:
                break
            self._chunks.append(c)
            self._size += len(c)
        if self._size < need:
            return None
        buf = b"".join(self._chunks)
        out = buf[:need]
        rest = buf[need:]
        self._chunks = [rest] if rest else []
        self._size = len(rest)
        return out

    def read(self):
        need = DISCORD_FRAME // (2 * self._factor)
        raw = self._pull(need)
        if raw is None:
            deadline = time.monotonic() + 0.15
            while raw is None and time.monotonic() < deadline:
                time.sleep(0.005)
                raw = self._pull(need)
            if raw is None:
                return b"\x00" * DISCORD_FRAME
        samples = array.array("h")
        samples.frombytes(raw)
        out = array.array("h")
        for s in samples:
            for _ in range(self._factor):
                out.append(s)
                out.append(s)
        if len(out) < 1920:
            out.extend([0] * (1920 - len(out)))
        return out[:1920].tobytes()


def _normalize_wake(text):
    """Map phonetic/loose transcriptions of the wake phrase to 'Ok Bot'.

    Rewrites every wake-phrase occurrence anywhere in the text (not just at
    the start) and collapses consecutive repeats. Returns None when nothing
    matched, so normal conversation passes through untouched.
    """
    if not text:
        return None
    new = _WAKE_RE.sub(_WAKE_REPL, text)
    if new == text:
        return None
    new = re.sub(r"(Ok Bot)(\s+Ok Bot)+", r"\1", new, flags=re.IGNORECASE)
    return new


_WAKE_RE = re.compile(
    r"(?<![\w])(?:ok(?:ay|ie|ey|ida|iba|ibou|iboo|ibob|ta)?)"
    r"(?:[\s,.;:!?]+(?:bot|bye|by|bey|bay|bart|baht|bort|birt|byrt|"
    r"but|butt|dood|doe|do))?"
    r"(?![\w])",
    re.IGNORECASE,
)


def _WAKE_REPL(m):
    return "Ok Bot"


def _input_chunk(data):
    """48kHz interleaved stereo int16 -> 16kHz mono int16.

    Averages each 3-frame group per channel (acts as a simple low-pass) and
    mixes channels, instead of dropping samples outright. Less aliasing, so
    Gemini's transcription gets cleaner input.
    """
    samples = array.array("h")
    samples.frombytes(data)
    n = len(samples)
    out = array.array("h")
    i = 0
    while i + 5 < n:
        left = (samples[i] + samples[i + 2] + samples[i + 4]) // 3
        right = (samples[i + 1] + samples[i + 3] + samples[i + 5]) // 3
        out.append((left + right) >> 1)
        i += 6
    return out.tobytes()


def _power16(data):
    samples = array.array("h")
    samples.frombytes(data)
    if not samples:
        return 0
    total = 0
    for x in samples:
        total += x * x
    return int((total / len(samples)) ** 0.5)


class SpeechGate:
    """Drops near-silent frames so the model only hears real speech."""

    ENERGY = 280
    MIN_OPEN = 3  # consecutive non-silent frames before opening (~60ms)
    HANGOVER = 10  # frames of trailing audio kept after speech stops (~200ms)

    def __init__(self):
        self._on = False
        self._guard = 0
        self._rising = 0
        self.last_power = 0

    def apply(self, data):
        power = _power16(data)
        self.last_power = power
        if self._on:
            if power < self.ENERGY:
                self._guard -= 1
                if self._guard <= 0:
                    self._on = False
                    print("Agent: speech gate closed")
            else:
                self._guard = self.HANGOVER
            return self._on
        if power >= self.ENERGY:
            self._rising += 1
            if self._rising >= self.MIN_OPEN:
                self._on = True
                self._guard = self.HANGOVER
                print("Agent: speech gate open")
                return True
        else:
            self._rising = 0
        return False


class Agent(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active = {}  # guild_id -> session dict
        self.reward_history = collections.defaultdict(collections.deque)
        self.reward_budget = collections.deque()

    agent = discord.SlashCommandGroup(
        "agent", "Live voice chat with Ok Bot", guild_ids=GUILD_IDS
    )

    @commands.Cog.listener()
    async def on_connect(self):
        print("Agent commands loaded")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        channel = message.channel
        guild = getattr(channel, "guild", None)
        if guild is None or isinstance(channel, discord.DMChannel):
            return
        session = self.active.get(guild.id)
        if not session:
            return
        tc = session.get("text_channel")
        if tc is None or tc.id != channel.id:
            return
        parts = []
        if message.content and message.content.strip():
            parts.append(message.content.strip())
        blob = None
        for att in message.attachments:
            mime = att.content_type or ""
            if mime.startswith("image/") and att.size and att.size <= 5_000_000:
                parts.append(f"[image: {att.filename}]")
                if blob is None:
                    try:
                        blob = types.Blob(data=await att.read(), mime_type=mime)
                    except Exception as e:
                        print(f"Agent attachment read error: {type(e).__name__}: {e}")
                        blob = None
            elif mime:
                parts.append(f"[file: {att.filename}]")
            else:
                parts.append(f"[file: {att.filename}]")
        if not parts:
            return
        name = message.author.display_name or message.author.name
        session["chat_q"].append((time.time(), name, " ".join(parts), blob))

    # ---------- recording ----------

    async def _start_recording(self, ctx):
        inbox = thread_queue.Queue()
        exclude_ids = [self.bot.user.id] if self.bot.user else []
        sink = RawPCMFilter(inbox, exclude_ids=exclude_ids)
        session = {
            "guild_id": ctx.guild.id,
            "user_id": ctx.author.id,
            "inbox": inbox,
            "sink": sink,
            "vc": ctx.voice_client,
            "live_task": None,
            "live_stop": asyncio.Event(),
            "recording": True,
            "paused": False,
            "last_talker": None,
            "text_channel": ctx.channel,
            "log_interaction": None,
            "last_log_edit": 0.0,
            "ack_until": 0.0,
            "last_input": None,
            "last_input_ts": None,
            "last_response": None,
            "last_response_ts": None,
            "chat_q": collections.deque(maxlen=8),
        }
        session["live_task"] = asyncio.create_task(
            self._run_live(session, ctx.voice_client)
        )
        self.active[ctx.guild.id] = session
        ctx.voice_client.start_recording(sink, callback=None)

    def _pause_input(self, session):
        vc = session.get("vc")
        if session.get("paused"):
            return
        if not vc or not vc.is_connected():
            return
        try:
            session["paused"] = True
            session["recording"] = False
            if vc.is_recording():
                vc.stop_recording()
            print("Agent: input paused (playback)")
        except Exception as e:
            print(f"Agent pause input error: {type(e).__name__}: {e}")

    async def _resume_input(self, session):
        vc = session.get("vc")
        if not vc or not vc.is_connected():
            return
        try:
            await asyncio.wait_for(session["live_stop"].wait(), timeout=0.35)
            return
        except asyncio.TimeoutError:
            pass
        try:
            if not vc.is_recording():
                vc.start_recording(session["sink"], callback=None)
            session["recording"] = True
            session["paused"] = False
            print(
                f"Agent: input resumed (frames={session['sink'].frame_count})"
            )
        except Exception as e:
            print(f"Agent resume input error: {type(e).__name__}: {e}")

    # ---------- live session ----------

    async def _run_live(self, session, vc):
        stop = session["live_stop"]
        while not stop.is_set():
            if session.get("paused") and (vc is None or not vc.is_playing()):
                asyncio.create_task(self._resume_input(session))
            source = LiveAudioSource()
            session["source"] = source
            try:
                async with CLIENT.aio.live.connect(
                    model=LIVE_MODEL,
                    config=types.LiveConnectConfig(
                        response_modalities=["AUDIO"],
                        input_audio_transcription=types.AudioTranscriptionConfig(),
                        output_audio_transcription=types.AudioTranscriptionConfig(),
                        realtime_input_config=types.RealtimeInputConfig(
                            automatic_activity_detection=(
                                types.AutomaticActivityDetection(disabled=True)
                            )
                        ),
speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name="Zubenelgenubi",
                                )
                            ),
                            languageCode="en-US",
                        ),
                        tools=[
                            types.Tool(
                                function_declarations=[
                                    types.FunctionDeclaration(
                                        name="okbot_wallet",
                                        description=(
                                            "Adjust a player's coins in Ok "
                                            "Bot's chaotic economy based on "
                                            "the last thing they said. Use "
                                            "'award' when someone is funny, "
                                            "clever, wholesome, or impressive. "
                                            "Use 'fine' when they're cringe, "
                                            "spammy, or wrong. Amount between "
                                            "1 and 250000. Rewards to a player "
                                            "get scaled down automatically if "
                                            "they were already rewarded "
                                            "recently or for the same thing, "
                                            "so don't spam this. Players can "
                                            "never go below 0 coins, so don't "
                                            "bother trying. Use it "
                                            "occasionally for spice, not on "
                                            "every message."
                                        ),
                                        parameters=types.Schema(
                                            type="OBJECT",
                                            properties={
                                                "amount": types.Schema(
                                                    type="INTEGER",
                                                    description=(
                                                        "Coins to award or "
                                                        "fine. Positive integer."
                                                    ),
                                                ),
                                                "action": types.Schema(
                                                    type="STRING",
                                                    description=(
                                                        "'award' or 'fine'."
                                                    ),
                                                    enum=["award", "fine"],
                                                ),
                                                "user": types.Schema(
                                                    type="STRING",
                                                    description=(
                                                        "Optional display "
                                                        "name of a specific "
                                                        "player to target "
                                                        "instead of the last "
                                                        "speaker."
                                                    ),
                                                ),
                                                "reason": types.Schema(
                                                    type="STRING",
                                                    description=(
                                                        "Why you feel this way "
                                                        "about the message."
                                                    ),
                                                ),
                                                "target_text": types.Schema(
                                                    type="STRING",
                                                    description=(
                                                        "Optional short recap "
                                                        "of what the target "
                                                        "player just said, so "
                                                        "the same idea can't be "
                                                        "rewarded twice."
                                                    ),
                                                ),
                                            },
                                            required=["amount", "action", "reason"],
                                        ),
                                    ),
                                    types.FunctionDeclaration(
                                        name="read_bot_source",
                                        description=(
                                            "Search Ok Bot's own source code "
                                            "to answer accurately about how a "
                                            "command, shop item, or mechanic "
                                            "actually works. Returns matching "
                                            "source lines with file and line "
                                            "numbers."
                                        ),
                                        parameters=types.Schema(
                                            type="OBJECT",
                                            properties={
                                                "query": types.Schema(
                                                    type="STRING",
                                                    description=(
                                                        "What to look up in "
                                                        "the source code."
                                                    ),
                                                ),
                                            },
                                            required=["query"],
                                        ),
                                    ),
                                ]
                            )
                        ],
                        system_instruction=SYS_PROMPT,
                    ),
                ) as live:
                    print("Agent session:", f"model={LIVE_MODEL}", "live")
                    sender = asyncio.create_task(self._send_audio(live, session))
                    receiver = asyncio.create_task(
                        self._receive_audio(live, session, vc, source)
                    )
                    watchdog = asyncio.create_task(
                        self._dave_watchdog(session, vc)
                    )
                    await self._await_live(sender, receiver, watchdog, stop)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"Agent live error: {type(e).__name__}: {e}")
            finally:
                try:
                    if vc and vc.is_playing():
                        vc.stop()
                except Exception:
                    pass
            if stop.is_set():
                break
            print("Agent: reconnecting live session")
            try:
                await asyncio.wait_for(stop.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    async def _await_live(self, sender, receiver, watchdog, stop):
        stop_task = asyncio.create_task(stop.wait())
        try:
            done, _ = await asyncio.wait(
                {sender, receiver, watchdog, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            stop_task.cancel()
        for task in (sender, receiver, watchdog):
            if task in done and not task.cancelled():
                exc = task.exception()
                if exc is not None:
                    print(f"Agent live task error: {type(exc).__name__}: {exc}")
            task.cancel()
        await asyncio.gather(sender, receiver, watchdog, return_exceptions=True)

    async def _dave_watchdog(self, session, vc):
        stop = session["live_stop"]
        baseline = 0
        last_rekey = 0.0
        last_frames = session["sink"].frame_count
        last_frames_ts = time.monotonic()
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=3)
                return
            except asyncio.TimeoutError:
                pass
            try:
                vc = session.get("vc")
                if session.get("recording") and vc and vc.is_connected():
                    if not vc.is_recording():
                        try:
                            vc.start_recording(session["sink"], callback=None)
                            print(
                                "Agent: watchdog restarted recording "
                                f"(frames={session['sink'].frame_count})"
                            )
                        except Exception as e:
                            print(
                                f"Agent watchdog restart error: "
                                f"{type(e).__name__}: {e}"
                            )
                rs = session.get("receiver_state")
                if rs and rs.get("playing"):
                    src = session.get("source")
                    now = time.monotonic()
                    idle = now - rs.get("last_feed_ts", 0)
                    if (
                        src is not None
                        and src.drained()
                        and idle > 3
                        and rs.get("turn_done")
                    ):
                        try:
                            if vc and vc.is_playing():
                                vc.stop()
                        except Exception:
                            pass
                        rs["playing"] = False
                        print("Agent: stuck playback cleared (drained + idle)")
                        asyncio.create_task(self._resume_input(session))
                frames = session["sink"].frame_count
                now = time.monotonic()
                duration = now - last_frames_ts
                if duration >= 9:
                    rate = (frames - last_frames) / duration
                    if not session.get("paused"):
                        print(
                            f"Agent: mic {rate:.0f} frames/s "
                            f"(recording={session.get('recording')})"
                        )
                    last_frames = frames
                    last_frames_ts = now
                state = vc._connection if vc else None
                dave = getattr(state, "dave_session", None) if state else None
                now = time.monotonic()
                if dave is not None and not getattr(dave, "ready", False):
                    # DAVE handshake is stalled. Until it's ready the bot can
                    # neither hear (inbound packets are dropped) nor be heard
                    # (outbound audio goes out unencrypted). The old code
                    # bailed here and never recovered, so it stayed silent
                    # until someone force-rejoined the voice channel.
                    if getattr(state, "dave_protocol_version", 0) > 0:
                        if session.get("dave_not_ready_since") is None:
                            session["dave_not_ready_since"] = now
                            print(
                                "Agent: DAVE session created but not ready, "
                                "watching..."
                            )
                        elif (
                            now - session["dave_not_ready_since"] >= 10
                            and now - last_rekey > 15
                        ):
                            last_rekey = now
                            if session.get("rekeys", 0) >= 2:
                                print(
                                    "Agent: DAVE never got ready after "
                                    "rekeys, hard-resetting voice connection"
                                )
                                session["rekeys"] = 0
                                session["dave_not_ready_since"] = None
                                asyncio.create_task(
                                    self._full_voice_reset(session)
                                )
                            else:
                                session["rekeys"] = (
                                    session.get("rekeys", 0) + 1
                                )
                                print(
                                    "Agent: DAVE session not ready, "
                                    "rekeying DAVE session"
                                )
                                try:
                                    await state.reinit_dave_session()
                                except Exception as e:
                                    print(
                                        "Agent: DAVE reinit error: "
                                        f"{type(e).__name__}: {e}"
                                    )
                    continue
                if session.get("dave_not_ready_since") is not None:
                    print("Agent: DAVE session became ready")
                session["dave_not_ready_since"] = None
                users = set(
                    uid
                    for uid in getattr(state, "ssrc_user_map", {}).values()
                    if uid
                )
                total = 0
                for uid in users:
                    try:
                        stats = dave.get_decryption_stats(
                            uid, MediaType.audio
                        )
                    except Exception:
                        continue
                    total += stats.failures if stats else 0
                delta = total - baseline
                baseline = total
                if delta >= 8 and now - last_rekey > 15:
                    last_rekey = now
                    if session.get("rekeys", 0) >= 2:
                        print(
                            "Agent: DAVE decrypt still failing after "
                            "rekeys, hard-resetting voice connection"
                        )
                        session["rekeys"] = 0
                        asyncio.create_task(self._full_voice_reset(session))
                    else:
                        session["rekeys"] = session.get("rekeys", 0) + 1
                        print(
                            "Agent: DAVE decrypt failing "
                            f"({delta} in 3s), rekeying DAVE session"
                        )
                        try:
                            await state.reinit_dave_session()
                        except Exception as e:
                            print(
                                "Agent: DAVE reinit error: "
                                f"{type(e).__name__}: {e}"
                            )
            except Exception as e:
                print(f"Agent watchdog error: {type(e).__name__}: {e}")

    async def _full_voice_reset(self, session):
        try:
            vc = session.get("vc")
            if vc is None:
                return
            channel = vc.channel
            try:
                if vc.is_recording():
                    vc.stop_recording()
            except Exception:
                pass
            try:
                if vc.is_playing():
                    vc.stop()
            except Exception:
                pass
            try:
                await vc.disconnect()
            except Exception:
                pass
            vc.cleanup()
        except Exception as e:
            print(f"Agent voice reset cleanup: {type(e).__name__}: {e}")
            return
        try:
            new_vc = await channel.connect()
        except Exception as e:
            print(f"Agent voice reset connect: {type(e).__name__}: {e}")
            return
        session["vc"] = new_vc
        try:
            new_vc.start_recording(session["sink"], callback=None)
        except Exception as e:
            print(f"Agent voice reset recording: {type(e).__name__}: {e}")
        session["recording"] = True
        session["paused"] = False
        rs = session.get("receiver_state") or {}
        src = session.get("source")
        if not (rs.get("playing") and src is not None and not src.drained()):
            session["source"] = LiveAudioSource()
        print("Agent: voice reconnected for DAVE recovery")

    async def _flush_chat(self, live, session):
        q = session.get("chat_q")
        if not q:
            return
        window = time.time() - 90
        recs = []
        while q:
            recs.append(q.popleft())
        lines = []
        media = None
        for ts, name, summary, blob in recs:
            if ts < window:
                continue
            lines.append(f"- **{name}**: {summary}")
            if media is None and blob is not None:
                media = blob
        if not lines:
            return
        if len(lines) > 6:
            lines = lines[-6:]
        payload = "New messages in the text chat:\n" + "\n".join(lines)
        if media is not None:
            try:
                resp = await CLIENT.aio.models.generate_content(
                    model=CAPTION_MODEL,
                    contents=[
                        "Describe this image in 12 words or less for a voice "
                        "assistant replying aloud. Output only the description.",
                        types.Part(inline_data=media),
                    ],
                )
                caption = (getattr(resp, "text", None) or "").strip()
            except Exception as e:
                print(f"Agent caption error: {type(e).__name__}: {e}")
                caption = ""
            if caption:
                payload += f"\n(user image: {caption})"
        try:
            await live.send_realtime_input(text=payload)
        except Exception as e:
            print(f"Agent chat text error: {type(e).__name__}: {e}")
        if media is not None:
            try:
                await live.send_realtime_input(video=media)
            except Exception as e:
                print(f"Agent chat media error: {type(e).__name__}: {e}")

    async def _send_audio(self, live, session):
        inbox = session["inbox"]
        gate = SpeechGate()
        in_activity = False
        last_sent_ts = 0.0
        dropped = 0
        sent = 0
        peak = 0
        was_open = False
        preroll = collections.deque(maxlen=10)
        while True:
            try:
                uid, raw = await asyncio.to_thread(inbox.get, timeout=0.25)
            except thread_queue.Empty:
                uid, raw = None, None
            now = time.monotonic()
            if raw is not None:
                was_open = gate._on
                opened = gate.apply(raw)
                if opened and not was_open:
                    for prow in preroll:
                        pchunk = _input_chunk(prow)
                        if not pchunk:
                            continue
                        if not in_activity:
                            await self._flush_chat(live, session)
                            try:
                                await live.send_realtime_input(
                                    activity_start=types.ActivityStart()
                                )
                            except Exception as e:
                                print(
                                    f"Agent activity_start error: "
                                    f"{type(e).__name__}: {e}"
                                )
                            in_activity = True
                            print("Agent: speech start -> Gemini")
                        try:
                            await live.send_realtime_input(
                                audio=types.Blob(
                                    data=pchunk,
                                    mime_type="audio/pcm;rate=16000",
                                )
                            )
                        except Exception as e:
                            print(f"Agent preroll send error: {e}")
                preroll.append(raw)
                if not opened:
                    dropped += 1
                    peak = max(peak, gate.last_power)
                    if dropped == 1000:
                        dropped = 0
                        q = inbox.qsize()
                        if q > 5:
                            print(f"Agent: input backlog q={q}")
                else:
                    chunk = _input_chunk(raw)
                    if chunk:
                        session["last_talker"] = uid
                        if not in_activity:
                            await self._flush_chat(live, session)
                            try:
                                await live.send_realtime_input(
                                    activity_start=types.ActivityStart()
                                )
                            except Exception as e:
                                print(
                                    f"Agent activity_start error: "
                                    f"{type(e).__name__}: {e}"
                                )
                            in_activity = True
                            print("Agent: speech start -> Gemini")
                        await live.send_realtime_input(
                            audio=types.Blob(
                                data=chunk, mime_type="audio/pcm;rate=16000"
                            )
                        )
                        last_sent_ts = now
                        sent += 1
                        peak = max(peak, gate.last_power)
                        if sent % 250 == 0:
                            print(
                                f"Agent: sent {sent} live audio frames "
                                f"(peak rms={peak})"
                            )
                            peak = 0
            if in_activity and now - last_sent_ts >= 0.7:
                try:
                    await live.send_realtime_input(
                        activity_end=types.ActivityEnd()
                    )
                except Exception as e:
                    print(f"Agent activity_end error: {type(e).__name__}: {e}")
                in_activity = False
                print("Agent: speech end -> Gemini (waiting reply)")

    async def _receive_audio(self, live, session, vc, source):
        state = {"said": [], "playing": False, "play_gen": 0, "last_feed_ts": 0,
             "holding": False, "drop_turn": False, "turn_ack": False,
             "ack_spoken": False, "turn_done": False}
        session["receiver_state"] = state
        handled_calls = set()
        while True:
            async for msg in live.receive():
                tc = msg.tool_call
                if tc and tc.function_calls:
                    session["ack_until"] = time.monotonic() + 8.0
                    responses = []
                    for fc in tc.function_calls:
                        if fc.partial_args and not fc.args:
                            continue
                        if fc.id in handled_calls:
                            continue
                        handled_calls.add(fc.id)
                        print(f"Agent tool call: {fc.name}({fc.args})")
                        out = await self._exec_tool(session, fc.name, fc.args or {})
                        if out is not None:
                            responses.append(
                                types.FunctionResponse(
                                    id=fc.id, name=fc.name, response=out
                                )
                            )
                    if responses:
                        await live.send_tool_response(function_responses=responses)
                self._handle_live_message(msg, vc, source, state, session)

    async def _exec_tool(self, session, name, args):
        try:
            if name == "okbot_wallet":
                return await self._tool_okbot_wallet(session, args)
            if name == "read_bot_source":
                return await self._tool_read_bot_source(args)
            return {"error": f"unknown tool: {name}"}
        except Exception as e:
            print(f"Agent tool error {name}: {type(e).__name__}: {e}")
            return {"error": f"tool {name} failed: {e}"}

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

    async def _scale_wallet_award(self, uid, text, amount):
        now = time.time()
        key = str(uid)
        history = self.reward_history.setdefault(key, collections.deque())
        while history and now - history[0][0] > REWARD_FARM_WINDOW:
            history.popleft()

        norm = self._normalize_reward_text(text)
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

    async def _tool_okbot_wallet(self, session, args):
        action = str(args.get("action", "award")).lower()
        if action not in ("award", "fine"):
            return {"applied": False, "message": "invalid action"}
        raw_amount = args.get("amount")
        try:
            amount = int(raw_amount) if raw_amount is not None else 1000
            amount = min(max(amount, 1), MAX_WALLET_TRANSFER)
        except (TypeError, ValueError):
            amount = 1000
        user_arg = args.get("user") or args.get("player")
        reason = str(args.get("reason") or "").strip()
        target_text = str(args.get("target_text") or "").strip() or reason
        vc = session.get("vc")
        guild = vc.guild if vc else None
        uid = None
        if user_arg:
            needle = str(user_arg).strip().lower()
            for m in (guild.members if guild else []):
                if not m.bot and (
                    (m.display_name or "").lower() == needle
                    or m.name.lower() == needle
                ):
                    uid = m.id
                    break
            if uid is None:
                return {
                    "applied": False,
                    "message": f"no player named {user_arg!r} found in the channel",
                }
        else:
            uid = session.get("last_talker")
            if uid is None:
                return {
                    "applied": False,
                    "message": "nobody has spoken yet to award or fine",
                }
        ec = _economy()
        # Same server-side anti-farm as the text chat: awards shrink if this
        # player was rewarded recently, for the same thing, or over a fatigued
        # budget. Fines are not scaled, just like cogs/fun.py.
        if action == "award":
            amount = await self._scale_wallet_award(uid, target_text, amount)
        before = await ec.get_wallet(str(uid))
        signed = amount if action == "award" else -amount
        new_wallet = await ec.add_coins(str(uid), signed)
        member = guild.get_member(uid) if guild else None
        shown = member.display_name if member else str(uid)
        channel = session.get("text_channel")
        if channel is not None:
            try:
                if action == "award":
                    await channel.send(
                        f"💸 {reason}. +{amount:,} coins to {shown}"
                    )
                else:
                    await channel.send(
                        f"📉 {reason}. -{amount:,} coins from {shown}"
                    )
            except Exception as e:
                print(f"Agent wallet announce error: {type(e).__name__}: {e}")
        return {
            "applied": True,
            "action": action,
            "amount": amount,
            "player": shown,
            "before_wallet": before,
            "new_wallet": new_wallet,
            "reason": reason,
            "message": f"{shown}'s wallet is now {new_wallet} coins",
        }

    async def _tool_read_bot_source(self, args):
        query = str(args.get("query", "")).strip().lower()
        tokens = [t for t in query.replace("_", " ").split() if t]
        if not tokens:
            return {"query": query, "matches": None, "note": "empty query"}
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        results = []
        for rel in ("bot/cogs/agent.py", "bot/main.py"):
            path = os.path.join(root, rel)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            for i, raw in enumerate(lines, 1):
                low = raw.lower()
                if all(tok in low for tok in tokens):
                    results.append(f"{rel}:{i}: {raw.rstrip()}")
        if not results:
            return {"query": query, "matches": None, "note": "no matches found"}
        text = "\n".join(results[:40])
        if len(text) > 3000:
            text = text[:3000] + "\n..."
        return {"query": query, "matches": text}

    def _handle_live_message(self, msg, vc, source, state, session):
        vc = session.get("vc") or vc
        sc = msg.server_content
        if sc is None:
            return
        in_ack = session.get("ack_until", 0.0) > time.monotonic()
        if in_ack and state.get("ack_spoken"):
            state["drop_turn"] = True
        if sc.interrupted:
            source.clear()
            state["said"] = []
            state["holding"] = False
            state["drop_turn"] = False
            state["turn_ack"] = False
            state["turn_done"] = False
            if state["playing"]:
                state["playing"] = False
                self._stop_playback(vc)
                loop = asyncio.get_event_loop()
                loop.create_task(self._resume_input(session))
            return
        if sc.input_transcription and sc.input_transcription.text:
            session["ack_until"] = 0.0
            state["ack_spoken"] = False
            heard = _normalize_wake(sc.input_transcription.text)
            if heard is None:
                heard = sc.input_transcription.text
            session["last_input"] = heard
            session["last_input_ts"] = int(time.time())
            print(f"Agent heard: {heard}")
        if sc.output_transcription and sc.output_transcription.text:
            if not state.get("drop_turn"):
                state["said"].append(sc.output_transcription.text)
                if state.get("holding") and not state["playing"]:
                    joined = re.sub(r"\s+", " ", " ".join(state["said"])).strip()
                    if len(joined) >= 2:
                        self._start_playback(session, vc, source, state)
            self._schedule_log_edit(session)
        mt = sc.model_turn
        if mt is not None and (mt.role or "") != "user":
            for part in mt.parts or []:
                if part.inline_data and part.inline_data.data:
                    if state.get("drop_turn"):
                        continue
                    mime = part.inline_data.mime_type or ""
                    m = re.search(r"rate=(\d+)", mime)
                    if m:
                        source.set_input_rate(int(m.group(1)))
                    source.feed(part.inline_data.data)
                    state["last_feed_ts"] = time.monotonic()
                    state["turn_done"] = False
                    if not state["playing"] and vc and not vc.is_playing():
                        if in_ack:
                            state["holding"] = True
                            state["turn_ack"] = True
                        else:
                            self._start_playback(session, vc, source, state)
        if sc.turn_complete:
            if state.get("drop_turn"):
                source.clear()
                state["drop_turn"] = False
                state["holding"] = False
                state["turn_ack"] = False
                state["turn_done"] = True
                state["said"] = []
                return
            text = " ".join(s.strip() for s in state["said"])
            text = re.sub(r"\s+", " ", text).strip()
            if state.get("holding") and not state["playing"]:
                if text:
                    self._start_playback(session, vc, source, state)
                else:
                    source.clear()
                state["holding"] = False
            state["turn_ack"] = False
            state["turn_done"] = True
            if text:
                session["last_response"] = text
                session["last_response_ts"] = int(time.time())
                print(f"Agent said: {text}")
                self._schedule_log_edit(session)
            else:
                print("Agent turn complete (no transcription)")
            state["said"] = []
            if state["playing"]:
                gen = state["play_gen"]
                loop = asyncio.get_event_loop()
                loop.create_task(self._stop_after_turn(vc, state, gen, session))

    def _start_playback(self, session, vc, source, state):
        if state.get("turn_ack"):
            state["ack_spoken"] = True
            state["turn_ack"] = False
        state["holding"] = False
        self._pause_input(session)
        state["play_gen"] += 1
        self._schedule_log_edit(session)
        vc_state = getattr(vc, "_connection", None) if vc else None
        dave = getattr(vc_state, "dave_session", None) if vc_state else None
        if dave is not None and not getattr(dave, "ready", False):
            print("Agent: playing while DAVE session not ready (inaudible)")
        try:
            vc.play(source)
            state["playing"] = True
        except Exception:
            pass

    def _schedule_log_edit(self, session):
        if session.get("log_interaction") is None:
            return
        now = time.monotonic()
        if now - session.get("last_log_edit", 0.0) < 0.25:
            return
        session["last_log_edit"] = now
        loop = asyncio.get_event_loop()
        loop.create_task(self._edit_live_log(session))

    async def _edit_live_log(self, session):
        interaction = session.get("log_interaction")
        if interaction is None:
            return
        rs = session.get("receiver_state") or {}
        live = " ".join(s.strip() for s in rs.get("said") or [])
        live = re.sub(r"\s+", " ", live).strip()
        spoken = live or session.get("last_response") or ""
        if not spoken:
            spoken = "…speaking…"
        heard = session.get("last_input") or "(nothing captured)"
        ts = session.get("last_response_ts")
        stamp = f"\n<t:{ts}:F>" if ts else ""
        try:
            await interaction.edit_original_response(
                content=(
                    f"**Bot thought you said:** {heard}\n"
                    f"**Bot replied:** {spoken}"
                    f"{stamp}"
                )
            )
        except Exception as e:
            print(f"Agent log edit error: {type(e).__name__}: {e}")

    def _stop_playback(self, vc):
        try:
            if vc and vc.is_playing():
                vc.stop()
        except Exception:
            pass

    async def _stop_after_turn(self, vc, state, gen, session):
        source = session.get("source")
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if state.get("play_gen") != gen or not state.get("playing"):
                return
            if source is not None and source.drained():
                break
            await asyncio.sleep(0.05)
        if state.get("play_gen") == gen and state.get("playing"):
            self._stop_playback(vc)
            state["playing"] = False
            await self._resume_input(session)

    # ---------- teardown ----------

    def _teardown_session(self, guild_id, reason=""):
        """Synchronous half of stopping a session.

        Drops it from the registry, signals the live task, and silences
        playback. Kept sync because cog_unload cannot await.
        """
        session = self.active.pop(guild_id, None)
        if session is None:
            return None

        session["live_stop"].set()
        session["recording"] = False
        session["paused"] = True

        vc = session.get("vc")
        try:
            if vc is not None and vc.is_recording():
                vc.stop_recording()
        except Exception as e:
            print(
                f"Agent teardown stop_recording error: "
                f"{type(e).__name__}: {e}"
            )
        self._stop_playback(vc)

        source = session.get("source")
        if source is not None:
            source.clear()

        suffix = f" ({reason})" if reason else ""
        print(f"Agent: session stopped{suffix}")
        return session

    async def stop_session(self, guild_id, reason=""):
        """Stop the live session for a guild. Returns True if one was running.

        Other cogs call this when the bot leaves the voice channel. The agent
        rides on the guild's shared voice client, so a disconnect would
        otherwise leave a Gemini Live socket and a Discord recorder running
        against a dead connection.
        """
        session = self._teardown_session(guild_id, reason=reason)
        if session is None:
            return False

        task = session.get("live_task")
        if task and not task.done():
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=5)
            if not task.done():
                task.cancel()
        return True

    # ---------- commands ----------

    @agent.command(
        description="Start talking to Ok Bot aloud. Say 'Ok Bot...'", guild_ids=GUILD_IDS
    )
    async def start(self, ctx):
        await ctx.defer()
        if ctx.guild.id in self.active:
            return await ctx.edit(content="Already listening in this server.")

        vc = ctx.voice_client
        if not vc or not vc.is_connected():
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await ctx.edit(
                    content="Join a voice channel first so I know where to go."
                )
            try:
                vc = await ctx.author.voice.channel.connect()
            except Exception as e:
                print(f"Agent join voice error: {type(e).__name__}: {e}")
                return await ctx.edit(
                    content="Could not join your voice channel. Check output.log."
                )
        elif not ctx.author.voice or ctx.author.voice.channel.id != vc.channel.id:
            return await ctx.edit(content="Join the bot's voice channel first.")

        try:
            await self._start_recording(ctx)
        except Exception as e:
            print(f"Agent start error: {type(e).__name__}: {e}")
            return await ctx.edit(
                content="Could not start the voice session. Check output.log."
            )
        await ctx.edit(
            content="Listening. Say **\"Ok Bot...\"** and I'll talk back.",
        )

    @agent.command(
        description="Show the last thing Ok Bot heard and how it replied", guild_ids=GUILD_IDS
    )
    async def log(self, ctx):
        await ctx.defer(ephemeral=True)
        session = self.active.get(ctx.guild.id)
        if not session:
            return await ctx.edit(
                content="No active agent session in this server."
            )
        session["log_interaction"] = ctx.interaction
        said = session.get("last_response")
        if not said:
            return await ctx.edit(
                content="Waiting for Ok Bot's first reply..."
            )
        heard = session.get("last_input") or "(nothing captured)"
        ts = session.get("last_response_ts")
        stamp = f"\n<t:{ts}:F>" if ts else ""
        await ctx.edit(
            content=(
                f"**Bot thought you said:** {heard}\n"
                f"**Bot replied:** {said}"
                f"{stamp}"
            )
        )

    @agent.command(description="Stop listening to voice chat", guild_ids=GUILD_IDS)
    async def stop(self, ctx):
        await ctx.defer()
        try:
            await self.stop_session(ctx.guild.id, reason="stop command")
            # The session's own client is the guild's shared one, but a reset
            # mid-session can leave the recorder on a stale reference.
            vc = ctx.voice_client
            if vc and vc.is_connected() and vc.is_recording():
                try:
                    vc.stop_recording()
                except Exception as e:
                    print(f"stop_recording error: {e}")
            await ctx.edit(content="Stopped listening.")
        except Exception as e:
            print(f"Agent stop error: {e}")
            await ctx.edit(content=f"Failed to stop cleanly: {e}")

    @agent.command(description="Wipe the voice-chat conversation memory", guild_ids=GUILD_IDS)
    async def reset(self, ctx):
        await ctx.defer()
        session = self.active.get(ctx.guild.id)
        if not session:
            return await ctx.edit(content="No active agent session in this server.")
        session["live_stop"].set()
        session["recording"] = False
        task = session.pop("live_task", None)
        if task and not task.done():
            try:
                await asyncio.wait_for(task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
        session["vc"] = ctx.voice_client
        session["live_stop"] = asyncio.Event()
        session["recording"] = True
        session["paused"] = False
        vc = ctx.voice_client
        if vc and vc.is_connected() and not vc.is_recording():
            try:
                vc.start_recording(session["sink"], callback=None)
            except Exception as e:
                print(f"Agent reset start_recording error: {type(e).__name__}: {e}")
        session["live_task"] = asyncio.create_task(
            self._run_live(session, ctx.voice_client)
        )
        await ctx.edit(content="Memory cleared.")

    def cog_unload(self):
        # Reloading or unloading the cog must not leave a Gemini Live session
        # or a Discord recorder running against a class that no longer exists.
        for guild_id in list(self.active):
            session = self._teardown_session(guild_id, reason="cog unload")
            task = session.get("live_task") if session else None
            if task and not task.done():
                task.cancel()


def setup(bot):
    bot.add_cog(Agent(bot))