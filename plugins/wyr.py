""" Would you rather? This plugin includes would you rather functionality
"""
import asyncio
import random
import re

import discord

import plugins
from pcbot import Config

client = plugins.client  # type: discord.Client

db = Config("would-you-rather", data=dict(timeout=10, responses=["**{name}** would **{choice}**!"], questions=[]),
            pretty=True)
command_pattern = re.compile(r"(.+)(?:\s+or|\s*,)\s+([^?]+)\?*")
sessions = set()  # All running would you rather's are in this set


@plugins.argument("{open}option ...{close} or/, {open}other option ...{close}[?]", allow_spaces=True)
async def options(arg):
    """ Command argument for receiving two options. """
    match = command_pattern.match(arg)
    assert match
    assert not match.group(1).lower() == match.group(2).lower(), "**The choices cannot be the same.**"

    return match.group(1), match.group(2)


def get_choice(choices: list, choice: str):
    """ Get the chosen option. This accept 1 and 2 as numbers. """
    if choice == "1":
        return 0

    if choice == "2":
        return 1

    choices = list(map(str.lower, choices))
    words = list(map(str.split, choices))

    # Go through all words in the given message, and find any words unique to a choice
    for word in choice.lower().split():
        if word in words[0] and word not in words[1]:
            return 0
        elif word in words[1] and word not in words[0]:
            return 1

    # Invalid choice
    return None


@plugins.command(aliases="wyr rather either")
async def wouldyourather(message: discord.Message, opt: options = None):
    """ Ask the bot if he would rather, or have the bot ask you.

    **Examples:**

    Registering a choice: `!wouldyourather lie or be lied to`

    Asking the bot: `!wouldyourather`"""
    # If there are no options, the bot will ask the questions (if there are any to choose from)
    if opt is None:
        assert message.channel.id not in sessions, "**A would you rather session is already in progress.**"
        sessions.add(message.channel.id)

        assert db.data["questions"], "**There are ZERO questions saved. Ask me one!**"

        question = random.choice(db.data["questions"])
        choices = question["choices"]
        await client.say(message, "Would you rather **{}** or **{}**?".format(*choices))

        timeout = db.data["timeout"]
        replied = []

        # Wait for replies from anyone in the channel
        while True:
            def check(m):
                return m.channel == message.channel and m.author not in replied

            try:
                reply = await client.wait_for("message", timeout=timeout, check=check)
            # Break on timeout
            except asyncio.TimeoutError:
                break

            # Check if the choice is valid
            choice = get_choice(choices, reply.content)
            if choice is None:
                continue

            # Register that this author has replied
            replied.append(reply.author)

            # Update the answers in the DB
            # We don't care about multiples, just the amount (yes it will probably be biased)
            question["answers"][choice] += 1

            name = reply.author.display_name
            response = random.choice(db.data["responses"]).format(name=name, NAME=name.upper(),
                                                                  choice=choices[choice])
            await client.say(message, response)

        # Say the total tallies
        await client.say(message, "A total of {0} would **{2}**, while {1} would **{3}**!".format(
            *question["answers"], *choices))
        await db.asyncsave()
        sessions.remove(message.channel.id)

    # Otherwise, the member asked a question to the bot
    else:
        db.data["questions"].append(dict(
            choices=list(opt),
            answers=[0, 0]
        ))
        await db.asyncsave()

        answer = random.choice(opt)
        await client.say(message, "**I would {}**!".format(answer))


@wouldyourather.command(aliases="delete", owner=True)
async def remove(message: discord.Message, opt: options):
    """ Remove a wouldyourather question with the given options. """
    for q in db.data["questions"]:
        if q["choices"][0] == opt[0] and q["choices"][1] == opt[1]:
            db.data["questions"].remove(q)
            await db.asyncsave()
            await client.say(message, "**Entry removed.**")
            break
    else:
        await client.say(message, "**Could not find the question.**")
