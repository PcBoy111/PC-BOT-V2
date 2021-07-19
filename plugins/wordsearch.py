""" Plugin for wordsearch

Commands:
    wordsearch
"""

from re import match
from random import choice

import discord
import asyncio
import aiohttp

import plugins

client = plugins.client  # type: discord.Client

wordsearch = []
wordsearch_words = []

tutorial = "Enter any word ending with `!` to guess the word!"
character_match = "[a-z0-9æøå]+"
word_list_url = "http://www.mieliestronk.com/corncob_lowercase.txt"


def valid_word(message: discord.Message):
    """ Check if the word only contains norwegian style letters or numbers. """
    if match("^" + character_match + "$", message.content.lower()):
        if len(message.content) < 32:
            return True

    return False


def valid_guess(message: discord.Message):
    """ Check if a message in this channel is a word guess. """
    if match("^" + character_match + "!$", message.content.lower()):
        return True

    return False


def format_hint(hint):
    """ Formats the hint string for our messages. """
    return "The word starts with `{0}`.".format(hint) if hint else ""


async def auto_word(count=1):
    global wordsearch_words

    word = ""
    if count < 1:
        count = 1
    elif count > 5:
        count = 5

    # Download a list of words if not stored in memory
    if not wordsearch_words:
        async with aiohttp.ClientSession() as session:
            async with session.get(word_list_url) as response:
                wordsearch_words = await response.text() if response.status == 200 else ""

        wordsearch_words = wordsearch_words.split("\n")

    for _ in range(count):
        word += choice(wordsearch_words).strip()

    return word.lower()


def stop_wordsearch(channel: discord.TextChannel):
    wordsearch.remove(channel.id)


async def start_wordsearch(channel: discord.TextChannel, host: discord.Member, word: str = None):
    if channel.id not in wordsearch:
        if not word:
            await client.send_message(channel, "Waiting for {0.mention} to choose a word!".format(host))
    else:
        await client.send_message(channel, "A wordsearch is already active in this channel!")
        return

    # Initialize the wordsearch
    wordsearch.append(channel.id)

    # Wait for the user to enter a word!wor
    if not word:
        await client.send_message(host, "**Please enter a word!**\n"
                                            "The word should be **maximum 32 characters long** and "
                                            "may **only** contain `letters A-Å` and *numbers*.")

        def check(m):
            return m.author == host and valid_word(m)

        try:
            reply = await client.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            reply = None

        # Stop the wordsearch if the user spent more than 30 seconds writing a valid word
        if not reply:
            stop_wordsearch(channel)
            await client.send_message(channel, "{0.mention} failed to enter a valid word.".format(host))
            return

        # Start the wordsearch
        word = reply.content.lower()
        await client.send_message(host, "Set the word to `{}`.".format(word))
        await client.send_message(channel, "{0.mention} has entered a word! {1}".format(host, tutorial))
    else:
        await client.send_message(channel, "{0.mention} made me set a word! {1}".format(host, tutorial))

    tries = 0
    hint = ""

    while channel.id in wordsearch:
        def check(m):
            return m.channel == channel and valid_guess(m)
        try:
            reply = await client.wait_for("message", timeout=60 * 30, check=check)
        except asyncio.TimeoutError:
            reply = None

        # Wordsearch expires after 30 minutes
        if not reply:
            stop_wordsearch(channel)
            await client.send_message(channel, "**The wordsearch was cancelled after 30 minutes of inactivity.**\n"
                                                   "The word was `{}`.".format(word))
            return

        guessed_word = reply.content.lower()[:-1]
        tries += 1

        # Update hint
        if guessed_word.startswith(hint):
            hint = ""
            for i, c in enumerate(guessed_word):
                if len(word) - 1 < i:
                    break

                if not c == word[i]:
                    break

                hint += c

        # Compare the words
        if guessed_word > word:
            m = "{0.mention} `{1}` is *after* in the dictionary. {2}".format(reply.author, guessed_word,
                                                                             format_hint(hint))
        elif guessed_word < word:
            m = "{0.mention} `{1}` is *before* in the dictionary. {2}".format(reply.author, guessed_word,
                                                                              format_hint(hint))
        else:
            m = ""

        if guessed_word.startswith(word):
            # User guessed the right word (kind of)
            m = "{0.mention} ***got it*** after **{tries}** tries! The word was `{word}`.".format(reply.author,
                                                                                                  tries=tries,
                                                                                                  word=word)
            stop_wordsearch(channel)

        asyncio.ensure_future(client.send_message(channel, m))


@plugins.command(name="wordsearch", aliases="ws")
async def wordsearch_(message: discord.Message):
    """ Start a wordsearch! Enter *any word* ending with `!` to guess the word! """
    client.loop.create_task(start_wordsearch(message.channel, message.author))


@wordsearch_.command(aliases="a")
async def auto(message: discord.Message, count: int = 1):
    """ Start an automatic wordsearch which sets a word for you. Default is one word,
    or enter up to 5 with `count`."""
    word = await auto_word(count)
    client.loop.create_task(start_wordsearch(message.channel, message.author, word))


async def on_reload(name: str):
    """ Keep the wordsearch games and auto words cache when reloading. """
    global wordsearch, wordsearch_words
    local_wordsearch, local_words = wordsearch, wordsearch_words

    await plugins.reload(name)

    wordsearch = local_wordsearch
    wordsearch_words = wordsearch_words
