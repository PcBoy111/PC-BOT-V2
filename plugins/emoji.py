""" This plugin has some emoji to PNG utilities!

Keep in mind that this library requires pycario, which I've found to be quite
difficult to install for windows.

Commands:
    greater
"""

import os
import re
from io import BytesIO

import discord
import cairosvg
from PIL import Image

import plugins
from pcbot import Annotate, utils


client = plugins.client  # type: discord.Client

emoji_path = "plugins/twemoji21lib/"
default_size = 1024
max_width = 2048
max_emoji = 64
emoji = {}

emote_regex = re.compile(r"<:(?P<name>\w+):(?P<id>\d+)>")
emote_cache = {}  # Cache for all custom emotes/emoji
emote_size = 112


def init_emoji():
    """ This will be a list of all emoji SVG files. Storing this in RAM is for
    easier access, considering the library of emojies only take up about 2.5MB
    (or 4MB in disk) as of now. If the library expands, the size should not
    increase drastically. """
    for file in os.listdir(emoji_path):
        with open(os.path.join(emoji_path, file), "rb") as f:
            emoji_name = file.split(".")[0]  # Strip the extension
            emoji_bytes = f.read()
            emoji[emoji_name] = emoji_bytes


def get_emoji(chars: str, size=default_size):
    """ Return the emoji with the specified character and optionally
    with the given size. """
    if chars not in emoji:
        return None

    emoji_bytes = emoji[chars]
    size_bytes = bytes(str(size), encoding="utf-8")
    emoji_bytes = emoji_bytes.replace(b"<svg ",
                                      b"<svg width=\"" + size_bytes + b"px\" height=\"" + size_bytes + b"px\" ")
    return Image.open(BytesIO(cairosvg.svg2png(emoji_bytes)))


async def get_emote(emote_id: str, server: discord.Server):
    """ Return the image of a custom emote. """
    emote = discord.Emoji(id=emote_id, server=server)

    # Return the cached version if possible
    if emote.id in emote_cache:
        return emote_cache[emote.id]

    # Otherwise, download the emote, store it in the cache and return
    emote_bytes = await utils.download_file(emote.url)
    emote_cache[emote.id] = emote_bytes
    return Image.open(BytesIO(emote_bytes))


def parse_emoji(chars: list, size):
    """ Go through and return all emoji in the given string. """
    # Convert all characters in the given list to hex format strings, and leave the Image objects alone
    chars = [hex(ord(c))[2:] if type(c) is str else c for c in chars]
    chars_remaining = length = len(chars)

    # Try the entire string backwards, and reduce the length by one character until there's a match
    while True:
        sliced_emoji = chars[:length]

        # If this is a custom emote, yield it and progress
        if type(sliced_emoji[0]) is Image.Image:
            yield sliced_emoji[0]

            chars = chars[length:]
            chars_remaining = length = len(chars)
            continue

        # If the emoji is in the list, update the index and reset the length, with the updated index
        if "-".join(sliced_emoji) in emoji.keys():
            yield get_emoji("-".join(sliced_emoji), size=size)

            chars = chars[length:]
            chars_remaining = length = len(chars)
            continue

        # When we don't find an emoji, reduce the length
        length -= 1

        # When the length is 0, but the amount of characters is greater than 1, remove the first one
        if length == 0 and chars_remaining > 1:
            chars = chars[1:]
            chars_remaining = length = len(chars)
        elif length < 1:
            break


async def format_emoji(text: str, server: discord.Server):
    """ Creates a list supporting both emoji and custom emotes. """
    char_and_emotes = []

    # Loop through each character and compare with custom emotes.
    # Add characters to list, along with emote byte-strings
    text_iter = iter(enumerate(text))
    has_custom = False
    for i, c in text_iter:
        match = emote_regex.match(text[i:])
        if match:
            char_and_emotes.append(await get_emote(match.group("id"), server))
            has_custom = True

            # Skip ahead in the iterator
            for _ in range(len(match.group(0) - 1)):
                next(text_iter)
        else:
            char_and_emotes.append(c)

    # Return the list of emoji, and set the respective size (should be managed manually if needed)
    return list(parse_emoji(char_and_emotes, default_size if has_custom else emote_size))


@plugins.command(aliases="huge")
async def greater(message: discord.Message, text: Annotate.CleanContent):
    """ Gives a **huge** version of emojies. """
    # Parse all unicode and load the emojies
    parsed_emoji = await format_emoji(text, message.server)
    assert parsed_emoji, "I couldn't find any emoji in that text of yours."

    # Combine multiple images if necessary, otherwise send just the one
    if len(parsed_emoji) == 1:
        image_fp = utils.convert_image_object(parsed_emoji[0])
        await client.send_file(message.channel, image_fp, filename="emoji.png")
        return

    # See if there's a need to rescale all images.
    size = default_size
    for e in parsed_emoji:
        width, height = e.size

        # Set the size to the lowest dimensions
        if width < size:
            size = width
        if height < size:
            size = height

    # When the size of all emoji next to each other is greater than the max width,
    # divide the size to properly fit the max_width at all times
    if size * len(parsed_emoji) > max_width:
        scale = 1 / ((size * len(parsed_emoji) - 1) // max_width + 1)
        size *= scale

    # Resize all emoji (so that the height == size) when one doesn't match any of the predetermined sizes
    total_width = 0
    if not size == default_size and not size == emote_size:
        for e in parsed_emoji:
            if e.height > size:
                width = round(size / e.height)
                total_width += width
                e.resize((width, e.height), Image.ANTIALIAS)

    # Stitch all the images together
    image = Image.new("RGBA", (total_width, size))
    x = 0
    for image_object in parsed_emoji:
        image.paste(image_object, box=(x, 0))
        x += image_object.width

    # Upload the stitched image
    image_fp = utils.convert_image_object(image)
    await client.send_file(message.channel, image_fp, filename="emojies.png")


init_emoji()

