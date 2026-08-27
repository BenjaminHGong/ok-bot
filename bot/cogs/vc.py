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
from utils import get_data_once
import wave

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

CHAT_MODEL = "gemini-2.5-flash-preview-tts"

GUILD_IDS = get_data_once("guilds")
NO_VOICE_CHANNEL = "The bot is not connected to a voice channel."


class VC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.join_messages = {}  # Store join messages: {guild_id: message}
        self._disconnect_tasks = []

    @commands.Cog.listener()
    async def on_connect(self):
        print("VC commands loaded")

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

    @vc.command(description="Make Ok Bot speak using Gemini TTS", guild_ids=GUILD_IDS)
    @option("text", str, description="What Ok Bot should say")
    async def say(self, ctx, text: str):
        vc = ctx.voice_client

        if not vc:
            return await ctx.respond(NO_VOICE_CHANNEL)
        if ctx.author.voice.channel.id != vc.channel.id:
            return await ctx.respond(
                "You must be in the same voice channel as the bot."
            )

        await ctx.respond("Generating voice...")

        # Generate TTS audio
        try:
            response = client.models.generate_content(
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
            data = response.candidates[0].content.parts[0].inline_data.data

            def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
                with wave.open(filename, "wb") as wf:
                    wf.setnchannels(channels)
                    wf.setsampwidth(sample_width)
                    wf.setframerate(rate)
                    wf.writeframes(pcm)

            # Create temporary file (will be auto-cleaned by tempfile)
            import tempfile

            fd, file_name = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            wave_file(file_name, data)
            wave_file(file_name, data)
            file_size = os.path.getsize(file_name)
            print(f"Wrote TTS file {file_name} ({file_size} bytes)")

            # Play the audio in the voice channel
            def cleanup_audio(error):
                try:
                    if os.path.exists(file_name):
                        os.remove(file_name)
                        print(f"Cleaned up TTS file {file_name}")
                except Exception as e:
                    print(f"Error cleaning up {file_name}: {e}")

            source = discord.FFmpegPCMAudio(
                executable="C:/ffmpeg/bin/ffmpeg.exe", source=file_name
            )

            if vc.is_playing():
                # Clean up if already playing
                cleanup_audio(None)
                return await ctx.edit(content="Wait until current sound finishes.")
            else:
                vc.play(source, after=cleanup_audio)
                await ctx.edit(content="Speaking!")

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
                    f"Quota limited exceeded! Try again {discord_timestamp_string}"
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
        vc = ctx.voice_client
        if not vc:
            await ctx.respond(NO_VOICE_CHANNEL)

        elif ctx.author.voice.channel.id != vc.channel.id:
            return await ctx.respond(
                "You must be in the same voice channel as the bot."
            )
        else:
            audio = discord.FFmpegPCMAudio(
                executable="C:/ffmpeg/bin/ffmpeg.exe", source=f"sounds/{sound}.mp3"
            )
            if vc.is_playing():
                await ctx.respond(
                    "Please wait until the current sound has finished.", ephemeral=True
                )
            else:
                vc.play(audio)
                await ctx.respond("Sound played!", ephemeral=True)

    def cog_unload(self):
        for vc in self.bot.voice_clients:
            task = asyncio.create_task(vc.disconnect())
            self._disconnect_tasks.append(task)


def setup(bot):
    bot.add_cog(VC(bot))
