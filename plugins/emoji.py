""" This plugin has some emoji to PNG utilities!

Keep in mind that this library requires pycario, which I've found to be quite
difficult to install for windows.

Commands:
    greater
"""
import asyncio
import os
import random
import re
from io import BytesIO

import discord
import cairosvg
from PIL import Image

import plugins
from pcbot import Annotate, utils

# See if we can create gifs using imageio
try:
    import imageio
except ImportError:
    imageio = None
gif_support = imageio is not None

client = plugins.client  # type: discord.Client

emoji_path = "plugins/twemoji12lib/"
default_size = 1024
max_width = 2048
max_emoji = 64
emoji = {}

emote_regex = re.compile(r"<:(?P<name>\w+):(?P<id>\d+)>")
emote_cache = {}  # Cache for all custom emotes/emoji
emote_size = 112

svg_element_regex = re.compile(r"<(?!svg)[^/>]+/>")


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


def set_svg_size(emoji_bytes, size=default_size):
    size_bytes = bytes(str(size), encoding="utf-8")
    emoji_bytes = emoji_bytes.replace(b"<svg ",
                                      b"<svg width=\"" + size_bytes + b"px\" height=\"" + size_bytes + b"px\" ")
    return emoji_bytes


def get_emoji(char: str, size=default_size):
    """ Return the emoji with the specified character and optionally
    with the given size. """
    if char not in emoji:
        return None

    emoji_bytes = emoji[char]
    emoji_bytes = set_svg_size(emoji_bytes, size)

    return Image.open(BytesIO(cairosvg.svg2png(emoji_bytes)))


async def get_emote(emote_id: int):
    """ Return the image of a custom emote. """

    # Return the cached version if possible
    if emote_id in emote_cache:
        return Image.open(emote_cache[emote_id])

    # Otherwise, download the emote, store it in the cache and return
    # url = emote.url.replace("discordapp.com/api/", "cdn.discordapp.com/")  # legacy discord.py gives old url format
    emote_bytes = await utils.download_file(f'https://cdn.discordapp.com/emojis/{emote_id}.png', bytesio=True)
    emote_cache[emote_id] = emote_bytes
    return Image.open(emote_bytes)


def parse_emoji(chars: list):
    """ Go through and yield all emoji in the given list of characters
    (or Image objects). """
    # Convert all characters in the given list to hex format strings, and leave the Image objects alone
    chars = [hex(ord(c))[2:] if type(c) is str else c for c in chars]
    chars_remaining = length = len(chars)

    # Try the entire string backwards, and reduce the length by one character until there's a match
    while True:
        sliced_emoji = chars[:length]
        if not sliced_emoji:
            break

        # If this is a custom emote, yield it and progress
        if isinstance(sliced_emoji[0], Image.Image):
            yield sliced_emoji[0]

            chars = chars[1:]
            chars_remaining = length = len(chars)
            continue

        # If the emoji is in the list, update the index and reset the length, with the updated index
        emoji_str = "-".join(e for e in sliced_emoji if not isinstance(e, Image.Image))
        if emoji_str in emoji.keys():
            yield emoji_str

            chars = chars[length:]
            chars_remaining = length = len(chars)
            continue

        # When we don't find an emoji, reduce the length
        length -= 1

        # When the length is 0, but the amount of characters is greater than 1, remove the first one
        if length == 0 and chars_remaining > 1:
            chars = chars[1:]
            chars_remaining = length = len(chars)


async def format_emoji(text: str):
    """ Creates a list supporting both emoji and custom emotes. """
    char_and_emotes = []

    # Loop through each character and compare with custom emotes.
    # Add characters to list, along with emote byte-strings
    text_iter = iter(enumerate(text))
    has_custom = False
    for i, c in text_iter:
        match = emote_regex.match(text[i:])
        if match:
            char_and_emotes.append(await get_emote(int(match.group("id"))))
            has_custom = True

            # Skip ahead in the iterator
            for _ in range(len(match.group(0)) - 1):
                next(text_iter)
        else:
            char_and_emotes.append(c)

    parsed_emoji = list(parse_emoji(char_and_emotes))

    # When the size of all emoji next to each other is greater than the max width,
    # divide the size to properly fit the max_width at all times
    size = default_size
    if has_custom:
        size = emote_size
    else:
        if size * len(parsed_emoji) > max_width:
            scale = 1 / ((size * len(parsed_emoji) - 1) // max_width + 1)
            size *= scale

    # Return the list of emoji, and set the respective size (should be managed manually if needed)
    return [e if isinstance(e, Image.Image) else get_emoji(e, size=size) for e in parsed_emoji], has_custom


async def convert_to_images(text: str):
    """ Converts any emoji in the given text to a list of images.

    :return: images: list, total_width: int, height: int
    """
    # Parse all unicode and load the emojies
    parsed_emoji, has_custom = await format_emoji(text)
    assert parsed_emoji, "I couldn't find any emoji in that text of yours."

    # Combine multiple images if necessary, otherwise send just the one
    if len(parsed_emoji) == 1:
        return parsed_emoji, parsed_emoji[0].width, parsed_emoji[0].height

    # See if there's a need to rescale all images.
    height = default_size
    for e in parsed_emoji:
        if e.height < height:
            height = e.height

    # Resize all emoji (so that the height == size) when one doesn't match any of the predetermined sizes
    total_width = 0
    if has_custom:
        for i, e in enumerate(parsed_emoji):
            if e.height > height:
                width = round(e.width * (height / e.height))
                total_width += width
                parsed_emoji[i] = e.resize((width, height), Image.ANTIALIAS)
            else:
                total_width += e.width
    else:
        total_width = len(parsed_emoji) * height

    return parsed_emoji, total_width, height


@plugins.command(aliases="huge bigger big larger large")
async def greater(message: discord.Message, text: Annotate.Content):
    """ Gives a **huge** version of emojies. """
    # Parse all unicode and load the emojies
    images, total_width, height = await convert_to_images(text)

    # Stitch all the images together
    image = Image.new("RGBA", (total_width, height))
    x = 0
    for image_object in images:
        image.paste(image_object, box=(x, 0))
        x += image_object.width

    # Upload the stitched image
    image_fp = utils.convert_image_object(image)
    await client.send_file(message.channel, image_fp, filename="emojies.png")


@plugins.command()
async def merge(message: discord.Message, text: Annotate.CleanContent):
    """ Randomly merge attributes from several emoji. Type 're' after the command to regenerate.  """
    contents = [str(emoji[char]) for char in parse_emoji(text)]

    assert contents, "Only emojies are supported."

    elements = []
    for svg in contents:
        elements.extend(svg_element_regex.findall(svg))

    replies = []
    while True:
        random.shuffle(elements)

        combined = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 36 36\">"
        combined += "".join(elements)
        combined += '</svg>'

        combined_bytes = bytes(combined, encoding="utf-8")
        combined_bytes = set_svg_size(combined_bytes, 256)

        image_bytes = BytesIO(cairosvg.svg2png(combined_bytes))

        msg = await client.send_file(message.channel, image_bytes, filename="combined.png")

        def check(m):
            return m.channel == message.channel and m.author == message.author and m.content.lower() == "re" or \
                   m.content.startswith("!merge")

        try:
            reply = await client.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            reply = None

        # If the user types this command, stop waiting for the "re" keyword
        if not reply or reply.content.startswith("!merge"):
            if replies and not message.channel.is_private:
                if len(replies) > 1:
                    await client.delete_messages(replies)
                else:
                    await client.delete_message(replies.pop())

            break

        # Otherwise, they must have typed the keyword
        replies.append(reply)
        await client.delete_message(msg)


async def gif(message: discord.Message, text: Annotate.CleanContent):
    """ Gives a **huge** version of emojies AS A GIF. """
    images, total_width, height = await convert_to_images(text)

    # Get optional duration
    duration = 0.15

    duration_arg = text.split(" ")[-1]
    if re.match(r"[0-9.]+", duration_arg):
        duration = float(duration_arg) / 10

    frames = []
    for image in images:
        frame_bytes = utils.convert_image_object(image, format="PNG")
        frames.append(imageio.imread(frame_bytes))

    # Make a gif
    image_bytes = imageio.mimwrite(imageio.RETURN_BYTES, frames, format="GIF", duration=duration)
    await client.send_file(message.channel, BytesIO(image_bytes), filename="emojies.gif")


if gif_support:
    plugins.command(aliases="gifter grifter")(gif)

init_emoji()
