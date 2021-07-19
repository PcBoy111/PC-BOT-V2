""" Plugin for playing music.

Some of the logic is very similar to the example at:
    https://github.com/Rapptz/discord.py/blob/master/examples/playlist.py

TUTORIAL:
    This module would require the bot to have ffmpeg installed and set in
    PATH, so that one could run `ffmpeg` in the shell.
    See: https://www.ffmpeg.org/

    The bot owner can link a music channel to any voice channel in a guild
    using the !music link <voice channel ...> command. After doing this, the
    bot should automatically join the linked channel whenever a member joins
    it. The members in the channel can then manage music playing.

ISSUES:
    The music player seems to randomly start skipping songs, or rather
    stopping them way too early. I have no solution to this issue and do not
    know why it happens, but apparently I'm not the only bot creator who has
    experienced said issue.

Commands:
    music
"""
import asyncio
import random
import re
from collections import namedtuple, deque
from traceback import print_exc
from typing import Dict

import discord
import youtube_dl

import plugins
from pcbot import utils, Annotate, Config

client = plugins.client  # type: discord.Client

music_channels = Config("music_channels", data=[])
voice_states = {}  # type: Dict[discord.Guild, VoiceState]
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'quiet': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_before_options = {
    "options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

max_songs_queued = 6  # How many songs each member are allowed in the queue at once
max_song_length = 10 * 60 * 60  # The maximum song length in seconds
default_volume = .6
song_playing = None
voiceclient = None

# if not discord.opus.is_loaded():
#    discord.opus.load_opus('libopus-0.x64.dll')

Song = namedtuple("Song", "channel player requester")

disposition_pattern = re.compile(r"filename=\"(?P<name>.+)\"")


async def on_reload(name: str):
    """ Preserve voice states. """
    global voice_states
    local_states = voice_states

    await plugins.reload(name)

    voice_states = local_states


def format_song(song: Song, url=True):
    """ Format a song request. """
    # The player duration is given in seconds; convert it to h:mm
    duration = ""
    if song.player.duration:
        duration = " / **{0}:{1:02}**".format(*divmod(int(song.player.duration), 60))

    return "**{0.title}** requested by **{1.display_name}**{2}".format(song.player, song.requester, duration) \
           + ("\n**URL**: <{0.url}>".format(song.player) if url else "")


class VoiceState:
    def __init__(self, voice):
        self.voice = voice
        self.queue = deque()  # The queue contains items of type Song
        self.skip_votes = set()


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.duration = data.get('duration')
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_before_options), data=data)


@plugins.command(aliases="m", disabled_pm=True)
async def music(message, _: utils.placeholder):
    """ Manage music. If a music channel is assigned, the bot will join
    whenever someone joins it. """
    pass


def get_guild_channel(guild: discord.Guild):
    """ Return the guild's music channel or None. """
    for channel in guild.channels:
        if str(channel.id) in music_channels.data:
            return channel

    return None


def client_connected(guild: discord.Guild):
    """ Returns True or False whether the bot is client_connected to the
    Music channel in this guild. """
    channel = get_guild_channel(guild)
    if guild.me.voice:
        return guild.me.voice.channel == channel and guild in voice_states
    else:
        return False


def format_playing(message):
    if message.guild.voice_client.is_playing():
        return format_song(song_playing, url=False)
    else:
        return "*Nothing.*"


async def play_next(message):
    """ Play the next song if there are any. """
    try:
        state = voice_states[message.guild]
    except:
        return
    state.skip_votes.clear()
    if not state.queue:
        await disconnect(message.guild)
        return
    source = state.queue.popleft()
    message.guild.voice_client.play(source.player,
                                    after=lambda e: asyncio.run_coroutine_threadsafe(play_next(message), client.loop))


def assert_connected(member: discord.Member, checkbot=True):
    """ Throws an AssertionError exception when neither the bot nor
    the member is connected to the music channel."""
    channel = get_guild_channel(member.guild)
    if member.voice:
        assert member.voice.channel is channel, "**You are not connected to the music channel.**"
    else:
        raise AssertionError("**You are not connected to the music channel.**")
    if checkbot:
        assert client_connected(member.guild), "**The bot is not connected to the music channel.**"


async def join(message: discord.Message):
    """Joins a voice channel"""
    global voiceclient
    guild = message.guild
    channel = get_guild_channel(message.guild)

    if guild.voice_client is not None:
        voiceclient = await guild.voice_client.move_to(channel)
        voice_states[guild] = VoiceState(voiceclient)
        return
    else:
        voiceclient = await channel.connect()
        voice_states[guild] = VoiceState(voiceclient)


async def disconnect(guild: discord.Guild):
    state = voice_states[guild]
    state.queue.clear()
    await guild.voice_client.disconnect()
    del voice_states[guild]


@music.command(aliases="p pl")
async def play(message: discord.Message, song: Annotate.Content):
    """ Play a song in the guild voice channel. The given song could either be a URL or keywords
    to lookup videos in youtube. """

    assert_connected(message.author, checkbot=False)

    # Connect to voice channel if not connected
    if message.guild.voice_client is None or not message.guild.me.voice.channel == get_guild_channel(message.guild):
        await join(message)

    state = voice_states[message.guild]

    # Check that the member hasn't already requested enough songs
    songs_queued = sum(1 for s in state.queue if s.requester == message.author)
    assert songs_queued < max_songs_queued, "**You have queued enough songs for now.**"

    # Strip any embed characters, spaces or code symbols.
    song = song.strip("< >`")

    try:
        player = await YTDLSource.from_url(song)
    except:
        await client.say(message, "**Could not add this song to the queue.**")
        return

    # Make sure the song isn't too long
    if player.duration:
        assert player.duration < max_song_length, "**The requested song is too long.**"

    url_match = utils.http_url_pattern.match(song)
    if url_match and player.title == url_match.group("sub"):
        # Try retrieving the filename as this is probably a file
        headers = await utils.retrieve_headers(song)
        if "Content-Disposition" in headers:
            name_match = disposition_pattern.search(headers["Content-Disposition"])
            if name_match:
                player.title = "".join(name_match.group("name").split(".")[:-1])

    global song_playing
    song_playing = Song(player=player, requester=message.author, channel=message.channel)
    await client.send_message(song_playing.channel, "Queued: " + format_song(song_playing, url=False))
    state.queue.append(song_playing)

    # Start the song when there are none
    if not message.guild.voice_client.is_playing():
        await play_next(message)


@music.command(aliases="s next")
async def skip(message: discord.Message):
    """ Skip the song currently playing. """
    assert_connected(message.author)
    state = voice_states[message.guild]
    assert message.guild.voice_client.is_playing(), "**There is no song currently playing.**"
    assert message.author not in state.skip_votes, "**You have already voted to skip this song.**"

    # We want to skip immediately when the requester skips their own song.
    if message.author == song_playing.requester:
        await client.say(message, "Skipped song on behalf of the requester.")
        message.guild.voice_client.stop()
        return

    state.skip_votes.add(message.author)

    # In order to skip, everyone but the requester and the bot must vote
    needed_to_skip = len(get_guild_channel(message.guild).members) - 2
    votes = len(state.skip_votes)
    if votes >= needed_to_skip:
        await client.say(message, "**Skipped song.**")
        message.guild.voice_client.stop()
    else:
        await client.say(message, "Voted to skip the current song. `{}/{}`".format(votes, needed_to_skip))


@music.command(aliases="u nvm fuck no")
async def undo(message: discord.Message):
    """ Undo your previously queued song. This will not *skip* the song if it's playing. """
    assert_connected(message.author)
    state = voice_states[message.guild]

    for song in reversed(state.queue):
        if song.requester == message.author:
            await client.say(message, "Removed previous request **{0.title}** from the queue.".format(song.player))
            state.queue.remove(song)
            return

    await client.say(message, "**You have nothing to undo.**")


@music.command()
async def clear(message: discord.Message):
    """ Remove all songs you have queued. """
    assert_connected(message.author)
    state = voice_states[message.guild]

    removed = False
    for song in list(state.queue):
        if song.requester == message.author:
            state.queue.remove(song)
            removed = True

    if removed:
        await client.say(message, "Removed all queued songs by **{0.display_name}**.".format(message.author))
    else:
        await client.say(message, "**You have no queued songs.**")


@music.command(roles="Shuffler")
async def shuffle(message: discord.Message):
    """ Shuffles the current queue. """
    assert_connected(message.author)
    state = voice_states[message.guild]

    random.shuffle(state.queue)
    await queue(message)


@music.command(aliases="v volume")
async def vol(message: discord.Message, volume: int):
    """ Set the volume of the player. Volume should be a number in percent. """
    assert_connected(message.author)
    message.guild.voice_client.source.volume = volume / 100
    await client.say(message, "Set the volume to **{:.00%}**.".format(volume / 100))


@music.command(aliases="np")
async def playing(message: discord.Message):
    """ Return the name and URL of the song currently playing. """
    assert_connected(message.author)
    await client.say(message, "Playing: " + format_playing(message))


@music.command(aliases="q l list")
async def queue(message: discord.Message):
    """ Return a list of the queued songs. """
    assert_connected(message.author)
    state = voice_states[message.guild]
    assert state.queue, "**There are no songs queued.**"

    await client.say(message, "```elm\n{}```".format(
        "\n".join(format_song(s, url=False).replace("**", "") for s in state.queue)))


@music.command(owner=True)
async def link(message: discord.Message, voice_channel: Annotate.VoiceChannel):
    """ Link the Music bot to a voice channel in a guild. """
    assert str(voice_channel.id) not in music_channels.data, "**This voice channel is already linked.**"
    assert get_guild_channel(message.guild) is None, "**A voice channel is already linked to this guild.**"

    # Link the channel
    music_channels.data.append(str(voice_channel.id))
    await music_channels.asyncsave()
    await client.say(message, "Voice channel **{0.name}** is now the music channel.".format(voice_channel))


@music.command(owner=True)
async def unlink(message: discord.Message):
    """ Unlink this guild's music channel. """
    channel = get_guild_channel(message.guild)
    assert channel, "**This guild has no voice channel linked.**"

    # Unlink the channel
    music_channels.data.remove(str(channel.id))
    await music_channels.asyncsave()
    await client.say(message, "This guild no longer has a music channel.")


@plugins.event()
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """ Handle joining and leaving channels. The bot will automatically
    join the guild's voice channel when a member joins. """
    guild = member.guild
    channel = get_guild_channel(member.guild)
    if channel is None:
        return

    count_members = sum(1 for m in channel.members if not m.bot)

    # Leave the voice channel we're client_connected to when the only one here is the bot
    if guild.me.voice is not None:
        if guild in voice_states and guild.me.voice.channel == channel:
            if count_members == 0:
                await disconnect(guild)
