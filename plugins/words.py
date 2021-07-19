from difflib import get_close_matches

import discord

from pcbot import Annotate
import plugins

client = plugins.client


def load_wordlist(filename: str):
    with open("plugins/wordlib/SimpleWordlists/Thesaurus-" + filename + ".txt") as f:
        return {k: v.split(",") for k, v in [line.split("|") for line in f.readlines()]}


antonyms = load_wordlist("Antonyms-All")
synonyms = load_wordlist("Synonyms-All")


@plugins.command()
async def antonym(message: discord.Message, phrase: Annotate.CleanContent):
    phrase = phrase.lower()

    if phrase not in antonyms:
        matches = get_close_matches(phrase, antonyms.keys(), n=5, cutoff=0.6)
        await client.say(message, "Found no antonyms for {}. Did you mean {}".format(phrase, ", ".join(
            "`" + match + "`" for match in matches)))
        return

    await client.say(message, ", ".join(s.strip(" \n") for s in antonyms[phrase]))


@plugins.command()
async def synonym(message: discord.Message, phrase: Annotate.CleanContent):
    phrase = phrase.lower()

    if phrase not in synonyms:
        matches = get_close_matches(phrase, synonyms.keys(), n=5, cutoff=0.6)
        await client.say(message, "Found no synonym for {}. Did you mean {}".format(phrase, ", ".join(
            "`" + match + "`" for match in matches)))
        return

    await client.say(message, ", ".join(s.strip(" \n") for s in synonyms[phrase]))


@plugins.command()
async def homonym(message: discord.Message, phrase: Annotate.CleanContent):
    await client.say(message, phrase)

