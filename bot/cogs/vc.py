import asyncio
import datetime
import discord
from discord import option
from discord.ext import commands
from discord.utils import basic_autocomplete
from google import genai
from google.genai import types
import os
import re
import time
from utils import get_data_once
import shutil
import wave
import httpx

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

FFMPEG_EXECUTABLE = shutil.which("ffmpeg") or "C:/ffmpeg/bin/ffmpeg.exe"

CHAT_MODEL = "gemini-2.5-flash-preview-tts"

GUILD_IDS = get_data_once("guilds")
NO_VOICE_CHANNEL = "The bot is not connected to a voice channel."


class VC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.join_messages = {}  # Store join messages: {guild_id: message}
        self._disconnect_tasks = []
        self.say_queues = {}  # guild_id -> queue of TTS file paths
        self.say_tasks = {}  # guild_id -> worker task
        self.play_files = {}  # guild_id -> currently playing TTS file path

    @commands.Cog.listener()
    async def on_connect(self):
        print("VC commands loaded")

    async def _stop_agent(self, guild_id, reason):
        """Shut down the live voice agent when the bot leaves the channel.

        The agent rides on this guild's shared voice client, so a disconnect
        orphans its Gemini Live socket and recorder. It deliberately repairs its
        own transient drops via _full_voice_reset, so this is only called on
        real departures - never from a generic voice_state hook.
        """
        agent = self.bot.get_cog("Agent")
        if agent is None:
            return
        try:
            await agent.stop_session(guild_id, reason=reason)
        except Exception as e:
            print(f"Failed to stop agent ({reason}): {type(e).__name__}: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Disconnect if bot is alone in voice channel"""
        voice_client = member.guild.voice_client
        if not voice_client or not voice_client.channel:
            return

        tracked_channel = voice_client.channel
        if tracked_channel not in (before.channel, after.channel):
            return

        if len(tracked_channel.members) != 1 or tracked_channel.members[0] != self.bot.user:
            return

        await self._stop_agent(member.guild.id, reason="channel emptied")
        await voice_client.disconnect()
        if member.guild.id in self.join_messages:
            try:
                message = self.join_messages[member.guild.id]
                await message.edit(
                    content=f"Ok Bot has left <#{tracked_channel.id}> as it was empty."
                )
                del self.join_messages[member.guild.id]
            except Exception as e:
                print(f"Failed to edit join message: {e}")

    sound_names = sorted(get_data_once("soundboard"))

    vc = discord.SlashCommandGroup(
        "vc", "Group of voice channel commands", guild_ids=GUILD_IDS
    )

    @staticmethod
    def _bot_voice_perms(guild: discord.Guild, channel: discord.abc.GuildChannel):
        me = guild.me if guild else None
        if not me:
            return None
        return channel.permissions_for(me)

    @vc.command(
        description="Tells the bot to join the voice channel", guild_ids=GUILD_IDS
    )
    async def join(self, ctx):
        voice = ctx.author.voice
        if not voice:
            await ctx.respond(f"{ctx.author.name} is not connected to a voice channel")
            return

        perms = self._bot_voice_perms(ctx.guild, voice.channel)
        if perms and (not perms.connect or not perms.speak):
            return await ctx.respond(
                "I need both Connect and Speak permissions in that voice channel."
            )

        voice_channel = voice.channel
        try:
            await voice_channel.connect()
            message = await ctx.respond(f"Joined {voice_channel.name}!")
            # Store the message for later editing on disconnect
            self.join_messages[ctx.guild.id] = message
        except discord.ClientException:
            await ctx.respond("I am already in a voice channel.")
        except Exception as e:
            await ctx.respond(f"An error occurred: {e}")

    @vc.command(
        description="Tells the bot to leave the voice channel", guild_ids=GUILD_IDS
    )
    async def leave(self, ctx):
        voice_client = ctx.guild.voice_client
        if voice_client and voice_client.is_connected():
            channel_name = voice_client.channel.name
            await self._stop_agent(ctx.guild.id, reason="bot left the channel")
            await voice_client.disconnect()

            # Edit the stored join message to indicate disconnect
            if ctx.guild.id in self.join_messages:
                try:
                    message = self.join_messages[ctx.guild.id]
                    await message.edit(content=f"Ok Bot has left {channel_name}!")
                    del self.join_messages[ctx.guild.id]
                except Exception as e:
                    print(f"Failed to edit join message: {e}")

            await ctx.respond("Ok Bot has left!")
        else:
            await ctx.respond(NO_VOICE_CHANNEL)

    @vc.command(description="Debug voice playback status", guild_ids=GUILD_IDS)
    async def debug(self, ctx):
        member_voice = ctx.author.voice.channel if ctx.author.voice else None
        bot_voice = ctx.guild.voice_client.channel if ctx.guild and ctx.guild.voice_client else None

        lines = [
            f"User channel: {member_voice.id if member_voice else 'None'}",
            f"Bot channel: {bot_voice.id if bot_voice else 'None'}",
        ]

        if member_voice:
            perms = self._bot_voice_perms(ctx.guild, member_voice)
            if perms:
                lines.append(f"Bot can connect: {perms.connect}")
                lines.append(f"Bot can speak: {perms.speak}")
                lines.append(f"Use voice activation: {perms.use_voice_activation}")

        player = ctx.voice_client
        if player:
            lines.append(f"Voice connected: {getattr(player, 'is_connected', lambda: False)() if callable(getattr(player, 'is_connected', None)) else bool(player)}")

        await ctx.respond("\n".join(lines), ephemeral=True)

    @staticmethod
    async def _fish_tts(api_key: str, text: str):
        body = {"text": text, "format": "mp3"}
        voice_id = os.getenv("FISH_VOICE_ID")
        if voice_id:
            body["reference_id"] = voice_id
        try:
            async with httpx.AsyncClient(timeout=60) as http:
                resp = await http.post(
                    "https://api.fish.audio/v1/tts",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "model": "s2.1-pro-free",
                    },
                    json=body,
                )
            if resp.status_code != 200:
                print(f"Fish TTS error {resp.status_code}: {resp.text}")
                return None, None
            print(f"Fish TTS generated {len(resp.content)} bytes")
            return resp.content, "mp3"
        except httpx.HTTPError as e:
            print(f"Fish TTS request error: {e}")
            return None, None

    @staticmethod
    def _pcm_to_wav(pcm, channels=1, rate=24000, sample_width=2):
        import io

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(pcm)
        return buffer.getvalue()

    def _cleanup_file(self, file_name):
        last_error = None
        for _ in range(5):
            try:
                if os.path.exists(file_name):
                    os.remove(file_name)
                    print(f"Cleaned up TTS file {file_name}")
                return
            except Exception as e:
                # Windows may still hold the file open (e.g. WinError 32)
                last_error = e
                time.sleep(0.5)
        print(f"Error cleaning up {file_name}: {last_error}")

    def _ensure_say_worker(self, guild_id):
        task = self.say_tasks.get(guild_id)
        if task and not task.done():
            return
        self.say_tasks[guild_id] = asyncio.create_task(self._say_player(guild_id))

    async def _say_player(self, guild_id):
        queue = self.say_queues.setdefault(guild_id, asyncio.Queue())
        while True:
            file_name = await queue.get()
            try:
                guild = self.bot.get_guild(guild_id)
                vc = guild.voice_client if guild else None
                if not vc or not vc.is_connected():
                    self._cleanup_file(file_name)
                    continue
                while vc.is_playing():
                    await asyncio.sleep(0.25)
                if not vc.is_connected():
                    self._cleanup_file(file_name)
                    continue
                source = discord.FFmpegPCMAudio(
                    executable=FFMPEG_EXECUTABLE, source=file_name
                )
                self.play_files[guild_id] = file_name
                vc.play(
                    source,
                    after=lambda _error, f=file_name: self._cleanup_file(f),
                )
            except Exception as e:
                print(f"Say player error: {e}")
                self._cleanup_file(file_name)
            finally:
                if self.play_files.get(guild_id) == file_name:
                    self.play_files.pop(guild_id, None)
                queue.task_done()

    @vc.command(description="Make Ok Bot speak", guild_ids=GUILD_IDS)
    @option("text", str, description="What Ok Bot should say")
    async def say(self, ctx, text: str):
        await ctx.defer()

        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            return await ctx.edit(content=NO_VOICE_CHANNEL)
        if ctx.author.voice.channel.id != vc.channel.id:
            return await ctx.edit(
                content="You must be in the same voice channel as the bot."
            )

        await ctx.edit(content="Generating voice...")

        # Generate TTS audio
        try:
            fish_key = os.getenv("FISH_API_KEY")
            if fish_key:
                audio_bytes, suffix = await self._fish_tts(fish_key, text)
                if audio_bytes is None:
                    return await ctx.edit(
                        content="TTS generation failed. Try again later"
                    )
            else:
                generated = await client.aio.models.generate_content(
                    model=CHAT_MODEL,
                    contents=f"Read like an underwhelmed teenager: {text}",
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name="Fenrir",
                                )
                            )
                        ),
                    ),
                )
                data = None
                if generated.candidates:
                    content = generated.candidates[0].content
                    if content and content.parts and content.parts[0].inline_data:
                        data = content.parts[0].inline_data.data
                if not data:
                    return await ctx.edit(
                        content="TTS replied without audio. Try again later."
                    )
                audio_bytes = self._pcm_to_wav(data)
                suffix = "wav"

            # Create temporary file (will be auto-cleaned by tempfile)
            import tempfile

            fd, file_name = tempfile.mkstemp(suffix=f".{suffix}")
            os.close(fd)
            with open(file_name, "wb") as f:
                f.write(audio_bytes)
            file_size = os.path.getsize(file_name)
            print(f"Wrote TTS file {file_name} ({file_size} bytes)")

            # Enqueue the audio so overlapping says play in order
            self.say_queues.setdefault(ctx.guild.id, asyncio.Queue()).put_nowait(
                file_name
            )
            self._ensure_say_worker(ctx.guild.id)

            position = self.say_queues[ctx.guild.id].qsize()
            if position == 1 and vc.is_connected() and not vc.is_playing():
                await ctx.edit(content="Speaking!")
            else:
                await ctx.edit(content=f"Queued at position {position}.")

        except genai.errors.ClientError as e:
            if "429" in str(e):
                retry_match = re.search(r"retry in ([0-9.]+)s", str(e))
                seconds = None
                if retry_match:
                    seconds = float(retry_match.group(1))
                future_time_utc = datetime.datetime.now(
                    datetime.timezone.utc
                ) + datetime.timedelta(seconds=seconds)
                unix_timestamp = int(future_time_utc.timestamp())
                discord_timestamp_string = f"<t:{unix_timestamp}:R>"
                await ctx.send(
                    f"Quota limit exceeded! Try again {discord_timestamp_string}"
                )
            else:
                print(f"TTS generation error: {e}")
                return await ctx.respond("TTS generation failed. Try again later")

    @vc.command(description="Get a bunch of sounds to play lol", guild_ids=GUILD_IDS)
    @option(
        "sound",
        str,
        description="Sound to play",
        autocomplete=basic_autocomplete(sound_names),
    )
    async def soundboard(self, ctx, sound):
        await ctx.defer(ephemeral=True)

        vc = ctx.voice_client
        if not vc or not vc.is_connected():
            await ctx.respond(NO_VOICE_CHANNEL, ephemeral=True)
            return

        elif ctx.author.voice.channel.id != vc.channel.id:
            return await ctx.respond(
                "You must be in the same voice channel as the bot.", ephemeral=True
            )
        else:
            audio = discord.FFmpegPCMAudio(
                executable=FFMPEG_EXECUTABLE, source=f"sounds/{sound}.mp3"
            )
            if vc.is_playing():
                await ctx.respond(
                    "Please wait until the current sound has finished.", ephemeral=True
                )
            else:
                vc.play(audio)
                await ctx.respond("Sound played!", ephemeral=True)

    @vc.command(
        description="Stop the current TTS and clear the queue", guild_ids=GUILD_IDS
    )
    async def stop(self, ctx):
        vc = ctx.voice_client
        if not vc or not vc.is_connected():
            return await ctx.respond(NO_VOICE_CHANNEL)
        if ctx.author.voice.channel.id != vc.channel.id:
            return await ctx.respond(
                "You must be in the same voice channel as the bot."
            )

        cleaned = 0
        vc.stop()
        playing = self.play_files.pop(ctx.guild.id, None)
        if playing:
            self._cleanup_file(playing)
            cleaned += 1

        queue = self.say_queues.get(ctx.guild.id)
        if queue:
            while not queue.empty():
                try:
                    file_name = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                queue.task_done()
                self._cleanup_file(file_name)
                cleaned += 1

        await ctx.respond(
            f"Stopped playback and cleared {cleaned} queued item(s)."
        )

    def cog_unload(self):
        for task in self.say_tasks.values():
            task.cancel()
        for vc in self.bot.voice_clients:
            task = asyncio.create_task(vc.disconnect())
            self._disconnect_tasks.append(task)


def setup(bot):
    bot.add_cog(VC(bot))
