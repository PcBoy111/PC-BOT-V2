""" Plugin for Russian Roulette

Commands:
    roulette
    hotpotato
"""

from datetime import datetime
from difflib import SequenceMatcher
from random import randint, choice
from threading import Timer

import asyncio
import discord

import plugins

client = plugins.client  # type: discord.Client

# List containing all channels playing a game
started = []


class Game:
    name = "Unnamed Game"
    minimum_participants = 1

    def __init__(self, message: discord.Message, num: int):
        self.message = message
        self.channel = message.channel
        self.member = message.guild.me

        self.num = num if num >= self.minimum_participants else self.minimum_participants
        self.participants = []

    async def on_start(self):
        """ Notify the channel that the game has been initialized. """
        m = "**{}** has started a game of {}! To participate, say `I`! **{} players needed.**".format(
            self.message.author.display_name, self.name, self.num)
        await client.say(self.message, m)

    async def get_participants(self):
        """ Wait for input and get all participants. """
        for i in range(self.num):

            def check(m):
                return m.channel == self.channel and m.content.lower().strip() == "i" and m.author not in self.participants

            # Wait with a timeout of 2 minutes and check each message with check(m)
            try:
                reply = await client.wait_for("message", timeout=120, check=check)
            except asyncio.TimeoutError:
                await client.say(self.message, "**The {} game failed to gather {} participants.**".format(
                    self.name, self.num))
                return

            if reply:  # A user replied with a valid check
                asyncio.ensure_future(
                    client.say(self.message,
                                   "{} has entered! `{}/{}`. Type `I` to join!".format(
                                       reply.author.mention, i + 1, self.num))
                )
                self.participants.append(reply.author)

                # Remove the message if bot has permissions
                if self.member.permissions_in(self.channel).manage_messages:
                    asyncio.ensure_future(client.delete_message(reply))
            else:
                # At this point we got no reply in time and thus, gathering participants failed
                await client.say(self.message, "**The {} game failed to gather {} participants.**".format(
                    self.name, self.num))
                started.pop(started.index(self.channel.id))

                return False

        return True

    async def prepare(self):
        """ Prepare anything needed before starting the game. """
        pass

    async def game(self):
        """ Start playing the game. """
        pass

    async def start(self):
        """ Run the entire game's cycle. """
        await self.on_start()
        valid = await self.get_participants()

        if valid:
            await asyncio.sleep(1)
            await self.prepare()
            await self.game()

            del started[started.index(self.channel.id)]


class Roulette(Game):
    """ A game of Roulette. """
    name = "Russian Roulette"

    def __init__(self, message: discord.Message, num: int):
        super().__init__(message, num)
        self.bullets = []

    async def prepare(self):
        """ Shuffle the bullets. """
        self.bullets = [0] * len(self.participants)
        self.bullets[randint(0, len(self.participants) - 1)] = 1

    async def game(self):
        """ Start playing. """
        for i, member in enumerate(self.participants):
            await client.send_message(
                self.channel,
                "{} is up next! Say `go` whenever you are ready.".format(member.mention)
            )

            def check(m):
                return m.channel == self.channel and m.author == member and "go" in m.content.lower()

            try:
                reply = await client.wait_for("message", timeout=15, check=check)
            except asyncio.TimeoutError:
                reply = None

            hit = ":dash:"

            if self.bullets[i] == 1 or reply is None:
                hit = ":boom:"

            if reply is None:
                await client.send_message(self.channel, "*fuck you*")

            await client.send_message(self.channel, "{} {} :gun: ".format(member.mention, hit))

            if self.bullets[i] == 1:
                break

        await client.send_message(self.channel, "**GAME OVER**")


class HotPotato(Game):
    name = "Hot Potato"
    minimum_participants = 3

    def __init__(self, message: discord.Message, num: int):
        super().__init__(message, num)
        self.time_remaining = 0

    def timer(self):
        """ I honestly don't remember how this function works. """
        self.time_remaining -= 1
        if self.time_remaining > 0:
            Timer(1, self.timer).start()

    async def game(self):
        """ Start the game. No comments because I was stupid and now I'm too
        lazy to comment everything in. """
        self.time_remaining = randint(
            int(pow(14 * len(self.participants), 0.8)),
            int(pow(30 * len(self.participants), 0.8))
        )

        member = choice(self.participants)
        Timer(1, self.timer).start()
        reply = True
        pass_to = []
        notify = randint(2, int(self.time_remaining / 2))

        while self.time_remaining > 0:
            if not pass_to:
                pass_from = list(self.participants)
                pass_from.pop(pass_from.index(member))
                pass_to = [choice(pass_from)]
                pass_from.pop(pass_from.index(pass_to[0]))
                pass_to.append(choice(pass_from))

            if reply is not None:
                await client.send_message(self.channel,
                                              "{} :bomb: got the bomb! Pass it to either {} or {}!".format(
                                                  member.mention, pass_to[0].mention, pass_to[1].mention))

            def check(m):
                return m.channel == self.channel and m.author == member and m.mentions[0] in pass_to

            wait = (self.time_remaining - notify) if (self.time_remaining >= notify) else self.time_remaining
            try:
                reply = await client.wait_for("message", timeout=wait, check=check)
            except asyncio.TimeoutError:
                reply = None

            if reply:
                member = reply.mentions[0]
                pass_to = []
                if self.member.permissions_in(self.channel).manage_messages:
                    asyncio.ensure_future(client.delete_message(reply))
            elif self.time_remaining == notify:
                asyncio.ensure_future(client.send_message(self.channel, ":bomb: :fire: **IT'S GONNA BLOW!**"))
                self.time_remaining -= 1

        await client.send_message(self.channel, "{0.mention} :fire: :boom: :boom: :fire:".format(member))
        await client.send_message(self.channel, "**GAME OVER**")


class Typing(Game):
    name = "Typing"

    sentences = ["GID A ragte omg"]
    reply = "{member.mention} finished in **{time:.0f} seconds** / **{wpm:.0f}wpm** / **{accuracy:.02%}**"
    minimum_wpm = 40

    def __init__(self, message: discord.Message, num: int):
        super().__init__(message, num)
        self.sentence = ""

    async def prepare(self):
        """ Get the sentence to send. """
        self.sentence = choice(self.sentences)

    async def send_sentence(self):
        """ Generate the function for sending the sentence. """
        await client.send_message(self.channel, "**Type**: " + self.sentence)

    def total_estimated_words(self):
        """ Return the estimated words in our sentence. """
        return len(self.sentence) / 5

    def calculate_accuracy(self, content: str):
        """ Calculate the accuracy. """
        return SequenceMatcher(a=self.sentence, b=content).ratio()

    def calculate_wpm(self, delta_seconds: int):
        """ Calculate the gross WPM from the given timedelta. """
        minutes = delta_seconds / 60
        return self.total_estimated_words() / minutes

    def calculate_timeout(self):
        """ Calculate the timeout for this game. This is the same as calculate_wpm,
        however it uses the same formula to calculate the time needed. """
        return self.total_estimated_words() / self.minimum_wpm * 60

    def is_participant(self, message: discord.Message):
        """ Check when waiting for a message and remove them from our list. """
        if message.author in self.participants:
            self.participants.remove(message.author)
            return True

        return False

    async def game(self):
        """ Run the game. """
        await self.send_sentence()

        checkpoint = time_started = datetime.now()
        timeout = self.calculate_timeout()

        # We'll wait for a message from all of our participants
        for i in range(len(self.participants)):
            def check(m):
                return m.channel == self.channel and self.is_participant is True

            try:
                reply = await client.wait_for("message", timeout=timeout, check=check)
            except asyncio.TimeoutError:
                await client.send_message(self.channel, "**Time is up.**")
                return

            # Delete the member's reply in order to avoid cheating
            asyncio.ensure_future(client.delete_message(reply))
            now = datetime.now()

            # Calculate the time elapsed since the game started
            time_elapsed = (now - time_started).total_seconds()

            # Calculate the accuracy, wpm and send the message
            accuracy = self.calculate_accuracy(reply.clean_content)
            wpm = self.calculate_wpm(int(time_elapsed))
            m = self.reply.format(member=reply.author, time=time_elapsed, wpm=wpm, accuracy=accuracy)
            asyncio.ensure_future(client.send_message(self.channel, m))

            # Reduce the timeout by the current time elapsed and create a checkpoint for the next timeout calculation
            timeout -= int((now - checkpoint).total_seconds())
            checkpoint = now

        await asyncio.sleep(1)
        await client.send_message(self.channel, "**Everyone finished!**")


desc_template = "Starts a game of {game.name}. To participate, say `I` in the chat.\n\n" \
                "The optional `participants` argument sets a custom number of participants, where " \
                "`{game.minimum_participants}` is the minimum."


async def init_game(message: discord.Message, game, num: int):
    """ Initialize a game.

    :param game: A Game object.
    :param num: The specified participants
    """
    if num > message.guild.member_count:
        num = sum(1 for m in message.guild.members if not m.bot and m.status is not discord.Status.offline)

    # The channel should not be playing two games at once
    assert message.channel.id not in started, "**This channel is already playing.**"

    # Start the game
    started.append(message.channel.id)
    await game(message, num).start()


@plugins.command(description=desc_template.format(game=Roulette))
async def roulette(message: discord.Message, participants: int = 6):
    """ The roulette command. Description is defined using a template. """
    await init_game(message, Roulette, participants)


@plugins.command(description=desc_template.format(game=HotPotato))
async def hotpotato(message: discord.Message, participants: int = 4):
    """ The hotpotato command. Description is defined using a template. """
    await init_game(message, HotPotato, participants)


@plugins.command(description=desc_template.format(game=Typing))
async def typing(message: discord.Message, participants: int = 2):
    """ The typing command. Description is defined using a template. """
    await init_game(message, Typing, participants)


async def on_reload(name: str):
    """ Keep the list of current games when reloading. """
    global started
    local_started = started

    await plugins.reload(name)

    started = local_started
