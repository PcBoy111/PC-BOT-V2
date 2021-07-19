import json
import pathlib
import random
from datetime import datetime

import discord

from pcbot import Annotate, utils
import plugins

client = plugins.client

words_path = pathlib.Path("plugins/wordlib/")

with open(words_path / "SimpleWordlists" / "Wordlist-Nouns-Common-Audited-Len-3-6.txt") as f:
    nouns = f.read().split("\n")

with open(words_path / "SimpleWordlists" / "Wordlist-Nouns-All.txt") as f:
    all_nouns = f.read().split("\n")

with open(words_path / "SimpleWordlists" / "Wordlist-Adjectives-All.txt") as f:
    adjectives = f.read().split("\n")

with open(words_path / "SimpleWordlists" / "Wordlist-Adverbs-All.txt") as f:
    adverbs = f.read().split("\n")

with open(words_path / "verb.forms.dictionary" / "json" / "verbs-all.json", encoding="ISO-8859-1") as f:
    verbs_json = json.load(f)
    verbs = [verb[0] for verb in verbs_json]


def seed_for_member(member: discord.Member, date=None):
    """ Gets the seed for the given member. """
    date = date or datetime.now()
    return f"{member.id}{date.year}{date.month}{date.day}"


def random_noun():
    selected_nouns = all_nouns if random.randint(0, 5) == 0 else nouns

    if random.randint(0, 3) == 0:
        return random.choice(adjectives) + " " + random.choice(selected_nouns)

    return random.choice(selected_nouns)


def random_verb():
    if random.randint(0, 3) == 0:
        return random.choice(verbs) + " " + random.choice(adverbs)

    return random.choice(verbs)


def make_agenda():
    if random.randint(0, 15) > 1:
        return random_noun() if random.randint(0, 1) == 0 else random_verb()

    agenda = random.choice(verbs) + " " + random_noun()
    if random.randint(0, 3) > 1:
        return agenda

    return agenda + " " + random.choice(adverbs)


def _horoscope(member: discord.Member, date=None, title: str = None):
    date = date or datetime.now()
    random.seed(seed_for_member(member, date))

    dos = ["\u2022 " + make_agenda().capitalize() for _ in range(3)]
    donts = ["\u2022 " + make_agenda().capitalize() for _ in range(3)]

    embed = discord.Embed(color=member.color, title=title or date.strftime("%A"))
    embed.set_author(name=member.display_name, icon_url=member.avatar_url)
    embed.add_field(name="Do", value="\n".join(dos))
    embed.add_field(name="Don't", value="\n".join(donts))
    return embed


@plugins.command(aliases="horoskop")
async def horoscope(message: discord.Message, member: discord.Member = Annotate.Self):
    """ Shows your horoscope or the horoscope for the given member. """
    embed = _horoscope(member)
    await client.send_message(message.channel, embed=embed)


@horoscope.command()
async def year(message: discord.Message, member: discord.Member = Annotate.Self):
    """ Shows your horoscope or the horoscope for the given member for the year. """
    date = datetime.today().replace(day=1).replace(month=1)
    embed = _horoscope(member, date, title=date.strftime("%Y"))
    await client.send_message(message.channel, embed=embed)


@plugins.command()
async def meotey(message: discord.Message, member: discord.Member = Annotate.Self):
    """ Shows the daily emote for you or for the given member. """
    date = datetime.now()
    m = utils.find_member(message.guild, member.mention)
    if m is None:
        await client.send_message(message.channel, "**Found no such member.**")
        return
    random.seed(seed_for_member(member, date))
    await client.send_message(message.channel, "__**{}** emote of the day__".format(
        "Your" if m == message.author else "{}'s".format(m.display_name)))
    await client.send_message(message.channel, random.choice(client.emojis))


@plugins.command()
async def meoji(message: discord.Message, member: discord.Member = Annotate.Self):
    """ Shows the daily emoji for you or for the given member. """
    date = datetime.now()
    m = utils.find_member(message.guild, member.mention)
    if m is None:
        await client.send_message(message.channel, "**Found no such member.**")
        return
    random.seed(seed_for_member(member, date))
    await client.send_message(message.channel, "__**{}** emoji of the day__".format(
        "Your" if m == message.author else "{}'s".format(m.display_name)))
    await client.send_message(message.channel, chr(random.randint(128513, 128591)))
    random.seed()
