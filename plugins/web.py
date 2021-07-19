""" Plugin for web commands

Commands:
    define
"""

import discord
from datetime import datetime

from pcbot import Annotate, utils
import plugins


client = plugins.client  # type: discord.Client


# Create exchange rate cache and keep track of when we last reset it
# exchange_rate_cache = dict(reset=client.time_started)


@plugins.command(aliases="def")
async def define(message: discord.Message, term: Annotate.LowerCleanContent):
    """ Defines a term using Urban Dictionary. """
    json = await utils.download_json("http://api.urbandictionary.com/v0/define", term=term)
    assert json["list"], "Could not define `{}`.".format(term)

    definitions = json["list"]
    msg = ""

    # Send any valid definition (length of message < 2000 characters)
    for definition in definitions:
        # Format example in code if there is one
        if definition.get("example"):
            definition["example"] = "```{}```".format(definition["example"])

        # Format definition
        msg = "**{word}**:\n{definition}{example}".format(**definition)

        # If this definition fits in a message, break the loop so that we can send it
        if len(msg) <= 2000:
            break

    # Cancel if the message is too long
    assert len(msg) <= 2000, "Defining this word would be a bad idea."

    await client.say(message, msg)

# async def get_exchange_rate(base: str, currency: str):
#    """ Returns the exchange rate between two currencies. """
#    # Return the cached result unless the last reset was yesterday or longer
#    if (base, currency) in exchange_rate_cache:
#        if (datetime.now() - exchange_rate_cache["reset"]).days >= 1:
#            exchange_rate_cache.clear()
#            exchange_rate_cache["reset"] = datetime.now()
#        else:
#            return exchange_rate_cache[(base, currency)]
#
#    data = await utils.download_json("https://api.fixer.io/latest", base=base, symbols=currency)
#
#    # Raise an error when the base is invalid
#    if "error" in data and data["error"].lower() == "invalid base":
#        raise ValueError("{} is not a valid currency".format(base))
#
#    # The API will not return errors on invalid symbols, so we check this manually
#    if not data["rates"]:
#        raise ValueError("{} is not a valid currency".format(currency))
#
#    rate = data["rates"][currency]

#    # Add both the exchange rate of the given order and the inverse to the cache
#    exchange_rate_cache[(base, currency)] = rate
#    exchange_rate_cache[(currency, base)] = 1 / rate

#    return rate


# @plugins.command(aliases="ge currency cur") async def convert(message: discord.Message, value: float,
# currency_from: str.upper, currency_to: str.upper): """ Converts currency using http://fixer.io/ """ try: rate =
# await get_exchange_rate(currency_from, currency_to) except ValueError as e: await client.say(message,
# e) else: flag = utils.text_to_emoji(currency_to[:2]) e = discord.Embed(description="{} {:,.2f} {}".format(flag,
# value * rate, currency_to), color=message.author.color) await client.send_message(message.channel, embed=e)


# async def on_reload(name):
#    """ Don't drop the cache. """
#    global exchange_rate_cache
#    local_cache = exchange_rate_cache
#
#    await plugins.reload(name)
#
#    exchange_rate_cache = local_cache
