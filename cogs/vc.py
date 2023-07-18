import asyncio

import discord
from discord import option
from discord.ext import commands
from discord.utils import basic_autocomplete

from jsonedit import get_data_once

GUILD_IDS = [1024196422637195315, 1099937674200105030]
owner_ids = [755525460267630612]


class VC(commands.Cog):
    def __init__(self, bot):
        self.bot = commands.Bot = bot

    @commands.Cog.listener()
    async def on_connect(self):
        print("VC commands loaded")

    sound_names = []
    sounds = get_data_once("soundboard")
    for name in sounds:
        sound_names.append(name)
    sound_names = sorted(sound_names)

    vc = discord.SlashCommandGroup("vc", "Group of voice channel commands")

    @vc.command(
        description="Tells the bot to join the voice channel", guild_ids=GUILD_IDS
    )
    async def join(self, ctx):
        voice = ctx.user.voice
        if not voice:
            await ctx.respond(f"{ctx.user.name} is not connected to a voice channel")
        else:
            try:
                await voice.channel.connect()
                await ctx.respond("Ok Bot has joined!")
            except discord.ClientException:
                await ctx.respond("Ok Bot is already in this channel.")

    @vc.command(
        description="Tells the bot to leave the voice channel", guild_ids=GUILD_IDS
    )
    async def leave(self, ctx):
        voice_client = ctx.guild.voice_client
        if voice_client.is_connected():
            await voice_client.disconnect()
            await ctx.respond("Ok Bot has left!")
        else:
            await ctx.respond("The bot is not connected to a voice channel.")

    @vc.command(description="Get a bunch of sounds to play lol", guild_ids=GUILD_IDS)
    @option(
        "sound",
        str,
        description="Sound to play",
        autocomplete=basic_autocomplete(sound_names),
    )
    async def soundboard(self, ctx, sound):
        vc = ctx.voice_client
        if not vc:  # check if the bot is not in a voice channel
            await ctx.respond("The bot is not connected to a voice channel.")

        elif (
            ctx.author.voice.channel.id != vc.channel.id
        ):  # check if the bot is not in the voice channel
            return await ctx.respond(
                "You must be in the same voice channel as the bot."
            )  # return an error message

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


def setup(bot):
    bot.add_cog(VC(bot))
