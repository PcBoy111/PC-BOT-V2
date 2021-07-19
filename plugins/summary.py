""" Plugin for generating markov text, or a summary if you will. """

import logging
import random
import re
from collections import defaultdict, deque
from functools import partial

import asyncio
import discord

from pcbot import utils, Annotate, config, Config
import plugins

client = plugins.client  # type: discord.Client

try:
    import markovify
except ImportError:
    logging.warning("Markovify could not be imported and as such !summary +strict will not work.")

NEW_LINE_IDENTIFIER = " {{newline}} "

# The messages stored per session, where every key is a channel id
stored_messages = defaultdict(partial(deque, maxlen=10000))
logs_from_limit = 5000
max_summaries = 15
max_admin_summaries = 15
update_task = asyncio.Event()
update_task.set()

# Define some regexes for option checking in "summary" command
valid_num = re.compile(r"\*(?P<num>\d+)")
valid_member = utils.member_mention_pattern
valid_member_silent = re.compile(r"@\((?P<name>.+)\)")
valid_role = re.compile(r"<@&(?P<id>\d+)>")
valid_channel = utils.channel_mention_pattern
valid_options = ("+re", "+regex", "+case", "+tts", "+nobot", "+bot", "+coherent", "+loose")

on_no_messages = "**There were no messages to generate a summary from, {0.author.name}.**"
on_fail = "**I was unable to construct a summary, {0.author.name}.**"

summary_options = Config("summary_options", data=dict(no_bot=False, no_self=False, persistent_channels=[]), pretty=True)
summary_data = Config("summary_data", data=dict(channels={}))


def to_persistent(message: discord.Message):
    return dict(content=message.clean_content, author=str(message.author.id), bot=message.author.bot)


async def update_messages(channel: discord.TextChannel):
    """ Download messages. """
    messages = stored_messages[str(channel.id)]  # type: deque

    # We only want to log messages when there are none
    # Any messages after this logging will be logged in the on_message event
    if messages:
        return

    # Make sure not to download messages twice by setting this handy task
    update_task.clear()

    # Download logged messages
    try:
        async for m in channel.history(limit=logs_from_limit):
            if not m.content:
                continue

            # We have no messages, so insert each from the left, leaving us with the oldest at index -1
            messages.appendleft(to_persistent(m))
    except:  # When something goes wrong, clear the messages
        messages.clear()
    finally:  # Really have to make sure we clear this task in all cases
        update_task.set()


async def on_reload(name: str):
    """ Preserve the summary message cache when reloading. """
    global stored_messages
    local_messages = stored_messages

    await plugins.reload(name)

    stored_messages = local_messages


def indexes_of_word(words: list, word: str):
    """ Return a list of indexes with the given word. """
    return [i for i, s in enumerate(words) if s.lower() == word]


def random_with_bias(messages: list, word: str):
    """ Go through all the messages and try to choose the ones where the given word is
    not at the end of the string. """
    last_word_messages = []
    non_last_word_messages = []
    for m in messages:
        words = m.split()
        if words[-1].lower() == word:
            last_word_messages.append(m)
        else:
            non_last_word_messages.append(m)

    if not last_word_messages:
        return random.choice(non_last_word_messages)
    elif not non_last_word_messages:
        return random.choice(last_word_messages)
    else:
        return random.choice(last_word_messages if random.randint(0, 5) == 0 else non_last_word_messages)


def markov_messages(messages, coherent=False):
    """ Generate some kind of markov chain that somehow works with discord.
    I found this makes better results than markovify would. """
    imitated = []
    word = ""

    if all(True if s.startswith("@") or s.startswith("http") else False for s in messages):
        return "**The given phrase would crash the bot.**"

    # First word
    while True:
        m_split = random.choice(messages).split()
        if not m_split:
            continue

        # Choose the first word in the sentence to simulate a markov chain
        word = m_split[0]

        if not word.startswith("@") and not word.startswith("http"):
            break

    # Add the first word
    imitated.append(word)
    valid = []
    im = ""

    # Next words
    while True:
        # Set the last word and find all messages with the last word in it
        if not im == imitated[-1].lower():
            im = imitated[-1].lower()
            valid = [m for m in messages if im in m.lower().split()]

        # Add a word from the message found
        if valid:
            # # Choose one of the matched messages and split it into a list or words
            m = random_with_bias(valid, im).split()
            m_indexes = indexes_of_word(m, im)
            m_index = random.choice(m_indexes)  # Choose a random index
            m_from = m[m_index:]

            # Are there more than the matched word in the message (is it not the last word?)
            if len(m_from) > 1:
                imitated.append(m_from[1])  # Then we'll add the next word
                continue
            else:
                # Have the chance of breaking be 1/4 at start and 1/1 when imitated approaches 150 words
                # unless the entire summary should be coherent
                chance = 0 if coherent else int(-0.02 * len(imitated) + 4)
                chance = chance if chance >= 0 else 0

                if random.randint(0, chance) == 0:
                    break

        # Add a random word if all valid messages are one word or there are less than 2 messages
        if len(valid) <= 1 or all(len(m.split()) <= 1 for m in valid):
            seq = random.choice(messages).split()
            word = random.choice(seq)
            imitated.append(word)

    # Remove links after, because you know
    imitated = [s for s in imitated if "http://" not in s and "https://" not in s]

    return " ".join(imitated)


def filter_messages(message_content: list, phrase: str, regex: bool = False, case: bool = False):
    """ Filter messages by searching and yielding each message. """
    for content in message_content:
        if regex:
            try:
                if re.search(phrase, content, 0 if case else re.IGNORECASE):
                    yield content
            except:  # Return error message when regex does not work
                raise AssertionError("**Invalid regex.**")
        elif not regex and (phrase in content if case else phrase.lower() in content.lower()):
            yield content


def is_valid_option(arg: str):
    if valid_num.match(arg) or valid_member.match(arg) or valid_member_silent.match(arg) \
            or valid_channel.match(arg) or valid_role.match(arg):
        return True

    if arg.lower() in valid_options:
        return True

    return False


def filter_messages_by_arguments(messages, channel, member, bots):
    # Split the messages into content and filter member and phrase
    messages = (m for m in messages if not member or m["author"] in [str(mm.id) for mm in member])

    # Filter bot messages or own messages if the option is enabled in the config
    if not bots:
        messages = (m for m in messages if not m["bot"])
    elif summary_options.data["no_self"]:
        messages = (m for m in messages if not m["author"] == str(client.user.id))

    # Convert all messages to content
    return (m["content"] for m in messages)


def is_endswith(phrase):
    return phrase.endswith("...") and len(phrase.split()) in (1, 2)


@plugins.command(
    usage="([*<num>] [@<user/role> ...] [#<channel>] [+re(gex)] [+case] [+tts] [+(no)bot] [+coherent] [+loose]) "
          "[phrase ...]",
    pos_check=is_valid_option, aliases="markov")
async def summary(message: discord.Message, *options, phrase: Annotate.Content = None):
    """ Run a markov chain through the past 5000 messages + up to another 5000
    messages after first use. This command needs some time after the plugin reloads
    as it downloads the past 5000 messages in the given channel. """
    # This dict stores all parsed options as keywords
    member, channel, num = [], None, None
    regex, case, tts, coherent, strict = False, False, False, False, True
    bots = not summary_options.data["no_bot"]

    async with message.channel.typing():
        for value in options:
            num_match = valid_num.match(value)
            if num_match:
                assert not num
                num = int(num_match.group("num"))
                continue

            member_match = valid_member.match(value)
            if member_match:
                member.append(message.guild.get_member(int(member_match.group("id"))))
                continue

            member_match = valid_member_silent.match(value)
            if member_match:
                member.append(utils.find_member(message.guild, member_match.group("name")))
                continue

            role_match = valid_role.match(value)
            if role_match:
                role = discord.utils.get(message.guild.roles, id=int(role_match.group("id")))
                member.extend(m for m in message.guild.members if role in m.roles)
                continue

            channel_match = valid_channel.match(value)
            if channel_match:
                assert not channel
                channel = utils.find_channel(message.guild, channel_match.group())
                continue

            if value in valid_options:
                if value == "+re" or value == "+regex":
                    regex = True
                if value == "+case":
                    case = True
                if value == "+tts":
                    tts = True
                if value == "+coherent":
                    coherent = True
                if value == "+loose":
                    strict = False

                bots = False if value == "+nobot" else True if value == "+bot" else bots

        # Assign defaults and number of summaries limit
        is_privileged = message.author.permissions_in(message.channel).manage_messages

        if num is None or num < 1:
            num = 1
        elif num > max_admin_summaries and is_privileged:
            num = max_admin_summaries
        elif num > max_summaries:
            num = max_summaries if not is_privileged else num

        if not channel:
            channel = message.channel

        # Check channel permissions after the given channel has been decided
        assert channel.permissions_for(message.guild.me).read_message_history, "**I can't see this channel.**"
        assert not tts or message.author.permissions_in(message.channel).send_tts_messages, \
            "**You don't have permissions to send tts messages in this channel.**"

        if str(channel.id) in summary_options.data["persistent_channels"]:
            messages = summary_data.data["channels"][str(channel.id)]
        else:
            await update_task.wait()
            await update_messages(channel)
            messages = stored_messages[str(channel.id)]

        message_content = filter_messages_by_arguments(messages, channel, member, bots)

        # Replace new lines with text to make them persist through splitting
        message_content = (s.replace("\n", NEW_LINE_IDENTIFIER) for s in message_content)

        # Filter looking for phrases if specified
        if phrase and not is_endswith(phrase):
            message_content = list(filter_messages(message_content, phrase, regex, case))

        command_prefix = config.guild_command_prefix(message.guild)
        # Clean up by removing all commands from the summaries
        if phrase is None or not phrase.startswith(command_prefix):
            message_content = [s for s in message_content if not s.startswith(command_prefix)]

        # Check if we even have any messages
        assert message_content, on_no_messages.format(message)

        markovify_model = None
        if strict:
            try:
                markovify_model = markovify.Text(message_content)
            except NameError:
                logging.warning("+strict was used but markovify is not imported")
                strict = False
            except KeyError:
                markovify_model = None

        # Generate the summary, or num summaries
        for i in range(num):
            if strict and markovify_model:
                if phrase and is_endswith(phrase):
                    try:
                        sentence = markovify_model.make_sentence_with_start(phrase[:-3])
                    except KeyError:
                        sentence = markovify_model.make_sentence(tries=1000)

                else:
                    sentence = markovify_model.make_sentence(tries=1000)
            else:
                sentence = markov_messages(message_content, coherent)

            if not sentence:
                sentence = markov_messages(message_content, coherent)

            assert sentence, on_fail.format(message)

            # Convert new line identifiers back to characters
            sentence = sentence.replace(NEW_LINE_IDENTIFIER.strip(" "), "\n")

            await client.send_message(message.channel, sentence, tts=tts)


@plugins.event(bot=True, self=True)
async def on_message(message: discord.Message):
    """ Whenever a message is sent, see if we can update in one of the channels. """
    if str(message.channel.id) in stored_messages and message.content:
        stored_messages[str(message.channel.id)].append(to_persistent(message))

    # Store to persistent if enabled for this channel
    if str(message.channel.id) in summary_options.data["persistent_channels"]:
        summary_data.data["channels"][str(message.channel.id)].append(to_persistent(message))
        await summary_data.asyncsave()


@summary.command(owner=True)
async def enable_persistent_messages(message: discord.Message):
    """ Stores every message in this channel in persistent storage. """
    if str(message.channel.id) in summary_options.data["persistent_channels"]:
        await client.say(message, "Persistent messages are already enabled and tracked in this channel")
        return

    summary_options.data["persistent_channels"].append(str(message.channel.id))
    await summary_options.asyncsave()

    await client.say(message, "Downloading messages. This may take a while.")

    # Create the persistent storage
    summary_data.data["channels"][str(message.channel.id)] = []

    # Download EVERY message in the channel
    async for m in message.channel.history(before=message, limit=None):
        if not m.content:
            continue

        # We have no messages, so insert each from the left, leaving us with the oldest at index -1
        summary_data.data["channels"][str(message.channel.id)].insert(0, to_persistent(m))

    await summary_data.asyncsave()
    await client.say(message,
                     "Downloaded {} messages!".format(len(summary_data.data["channels"][str(message.channel.id)])))
