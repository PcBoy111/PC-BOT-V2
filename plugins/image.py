""" This plugin is designed for various image utility commands.

Commands:
    resize """
import random
import re
from functools import partial
from io import BytesIO

from PIL import Image, ImageSequence, ImageOps
import discord

import logging
import plugins
from pcbot import utils

url_only, gif_support = False, True

# See if we can convert emoji using the emoji.py plugin
try:
    from .emoji import get_emote, get_emoji, emote_regex
except:
    url_only = True

# See if we can create gifs using imageio
try:
    import imageio
except:
    gif_support = False

client = plugins.client  # type: discord.Client

extension_regex = re.compile(r"image/(?P<ext>\w+)(?:\s|$)")
mention_regex = re.compile(r"<@!?(?P<id>\d+)>")
max_bytes = 4096 ** 2  # 4 MB
max_gif_bytes = 1024 * 6000  # 128kB


def convert_image(image_object, mode, real_convert=True):
    """ Convert the image object to a specified mode. """
    if mode == "RGB" and image_object.mode == "RGBA" and real_convert:
        return to_rgb(image_object)

    return image_object.convert(mode)


def to_rgb(image_object):
    """ Convert to RGB using solution from http://stackoverflow.com/questions/9166400/ """
    image_object.load()
    background = Image.new("RGB", image_object.size, (0, 0, 0))
    background.paste(image_object, mask=image_object.split()[3])
    return background


def to_jpg(image_object, quality, real_convert=True):
    """ Save an image object as JPG and reopen it. """
    if image_object.mode != "RGB":
        image_object = convert_image(image_object, "RGB", real_convert)

    return Image.open(utils.convert_image_object(image_object, "JPEG", quality=quality))


class ImageArg:
    def __init__(self, image_object: Image.Image, format: str):
        self.object = image_object
        self.format = format
        self.extension = format.lower()
        self.clean_format()

        # Figure out if this is a gif by looking for the duration argument. Might only work for gifs
        self.gif = bool(self.object.info.get("duration"))
        self.gif_bytes = None  # For easier upload of gifs, store the bytes in memory

    def clean_format(self, real_convert=True):
        """ Return working options of JPG images. """
        if self.extension.lower() == "jpeg":
            self.extension = "jpg"
        if self.format.lower() == "jpg":
            self.format = "JPEG"

    def set_extension(self, ext: str, real_jpg=True):
        """ Change the extension of an image. """
        self.extension = self.format = ext

    def modify(self, function, *args, convert=None, **kwargs):
        """ Modify the image object using the given Image function.
        This function supplies sequence support. """
        if not gif_support or not self.gif:
            if convert:
                self.object = convert_image(self.object, convert)

            if type(function) is list:
                for func in function:
                    self.object = func(self.object, *args, **kwargs)
            else:
                self.object = function(self.object, *args, **kwargs)
        else:
            frames = []
            duration = self.object.info.get("duration") / 1000
            for frame in ImageSequence.Iterator(self.object):
                if convert:
                    frame = convert_image(frame, convert, real_convert=False)

                if type(function) is list:
                    for func in function:
                        frame = func(frame, *args, **kwargs)
                    frame_bytes = utils.convert_image_object(frame)
                else:
                    frame_bytes = utils.convert_image_object(function(frame, *args, **kwargs))
                frames.append(imageio.imread(frame_bytes, format="PNG"))

            # Save the image as bytes and recreate the image object
            image_bytes = imageio.mimwrite(imageio.RETURN_BYTES, frames, format=self.format, duration=duration)
            self.object = Image.open(BytesIO(image_bytes))
            self.gif_bytes = image_bytes


async def convert_attachment(attachment):
    """ Convert an attachment to an image argument.

    Returns None if the attachment is not an image.
    """
    url = attachment["url"]
    headers = await utils.retrieve_headers(url)
    match = extension_regex.search(headers["CONTENT-TYPE"])
    if not match:
        return None

    image_format = match.group("ext")
    image_bytes = await utils.download_file(url, bytesio=True)
    image_object = Image.open(image_bytes)
    return ImageArg(image_object, format=image_format)


async def find_prev_image(channel: discord.TextChannel, limit: int = 200):
    """ Look for the previous sent image. """
    async for message in channel.history(limit=limit):
        if message.attachments:
            # Try to convert the first attachment
            image_arg = await convert_attachment(message.attachments[0])
            if not image_arg:
                continue

            return image_arg

    return None


@plugins.argument("{open}url/@user" + ("" if url_only else "/emoji") + "{suffix}{close}", pass_message=True)
async def image(message: discord.Message, url_or_emoji: str):
    """ Parse a url, emoji or user mention and return an ImageArg object. """
    # Check for local images
    if url_or_emoji == ".":
        # First see if there is an attachment to this message
        image_arg = None
        if message.attachments:
            image_arg = await convert_attachment(message.attachments[0])

        # If there is no attached image, look for an image posted previously
        if not image_arg:
            image_arg = await find_prev_image(message.channel)

        assert image_arg is not None, "Could not find any previously attached image."
        return image_arg

    # Remove <> if the link looks like a URL, to allow for embed escaped links.
    if "http://" in url_or_emoji or "https://" in url_or_emoji:
        url_or_emoji = url_or_emoji.strip("<>")

    try:  # Check if the given string is a url and save the headers for later
        headers = await utils.retrieve_headers(url_or_emoji)
    except ValueError:  # Not a valid url, let's see if it's a mention
        match = mention_regex.match(url_or_emoji)
        logging.info(url_or_emoji)
        if match:
            member = message.guild.get_member(int(match.group("id")))
            avatar_headers = await utils.retrieve_headers(str(member.avatar_url_as(static_format="png")))
            assert not avatar_headers["CONTENT-TYPE"].endswith("gif"), "**GIF avatars are currently unsupported.**"

            image_bytes = await utils.download_file(str(member.avatar_url_as(static_format="png")), bytesio=True)
            image_object = Image.open(image_bytes)
            return ImageArg(image_object, format="PNG")

        # Nope, not a mention. If we support emoji, we can progress further
        assert not url_only, "`{}` **is not a valid URL or user mention.**".format(url_or_emoji)

        # There was no image to get, so let's see if it's an emoji
        char = "-".join(hex(ord(c))[2:] for c in url_or_emoji)  # Convert to a hex string
        image_object = get_emoji(char, size=256)
        if image_object:
            return ImageArg(image_object, format="PNG")

        # Not an emoji, perhaps it's an emote
        match = emote_regex.match(url_or_emoji)
        if match:
            image_object = await get_emote(match.group("id"))
            if image_object:
                return ImageArg(image_object, format="PNG")

        # Alright, we're out of ideas
        raise AssertionError("`{}` **is neither a URL, a mention nor an emoji.**".format(url_or_emoji))

    # The URL was valid so let's make sure it's an image
    match = extension_regex.search(headers["CONTENT-TYPE"])
    assert match, "**The given URL is not an image.**"
    image_format = match.group("ext")

    # Make sure the image is not too big
    gif = image_format.lower() == "gif"
    if "CONTENT-LENGTH" in headers:
        size = headers["CONTENT-LENGTH"]
        max_size = max_gif_bytes if gif else max_bytes
        assert int(size) <= max_size, \
            "**This image exceeds the maximum size of `{}kB` for this format.**".format(max_size // 1024)
    elif gif:  # If there is no information on the size of the file, we'll refuse if the image is a gif
        raise AssertionError("**The size of this GIF is unknown and was therefore rejected.**")

    # Download the image and create the object
    image_bytes = await utils.download_file(url_or_emoji, bytesio=True)
    image_object = Image.open(image_bytes)
    return ImageArg(image_object, format=image_format)


@plugins.argument("({open}width{close}x{open}height{close} or *{open}scale{close})")
def parse_resolution(res: str):
    """ Parse a resolution string.

    If the y value is zero, the x value is the number to scale the image with. """
    # Check what type of input we're parsing
    if res.count("x") == 1:
        # Try parsing the numbers in the resolution
        x, y = res.split("x")
        try:
            x = int(x)
            y = int(y)
        except ValueError:
            raise AssertionError("**Width or height are not integers.**")

        # Assign a maximum and minimum size
        assert 1 <= x <= 3000 and 1 <= y <= 3000, "**Width and height must be between 1 and 3000.**"
        return x, y
    elif res.startswith("*"):
        try:
            scale = float(res[1:])
        except ValueError:
            raise AssertionError("**Characters following \* must be a number, not `{}`**".format(res[1:]))

        # Make sure the scale isn't less than 0. Whatever uses this argument will have to manually check for max size
        assert scale > 0, "**Scale must be greater than 0.**"
        return scale, 0
    else:
        return None


def clean_format(image_format: str, extension: str):
    """ Return working options of JPG images. """
    if extension.lower() == "jpeg":
        extension = "jpg"
    if image_format.lower() == "jpg":
        image_format = "JPEG"

    return image_format, extension


async def send_image(message: discord.Message, image_arg: ImageArg, **params):
    """ Send an image. """
    try:
        if image_arg.gif and gif_support:
            image_fp = BytesIO(image_arg.gif_bytes)
        else:
            image_fp = utils.convert_image_object(image_arg.object, image_arg.format, **params)
    except KeyError as e:
        await client.send_message(message.channel, "Image format `{}` is unsupported.".format(e))
    else:
        await client.send_file(message.channel, image_fp,
                               filename="{}.{}".format(message.author.display_name, image_arg.extension))


@plugins.command(pos_check=lambda s: s.startswith("-"))
async def resize(message: discord.Message, image_arg: image, resolution: parse_resolution, *options):
    """ Resize an image with the given resolution formatted as `<width>x<height>`
    or `*<scale>`. """
    # Generate a new image based on the scale
    if resolution[1] == 0:
        w, h = image_arg.object.size
        scale = resolution[0]
        assert w * scale < 3000 and h * scale < 3000, "**The result image must be less than 3000 pixels in each axis.**"
        resolution = (int(w * scale), int(h * scale))

    # Resize and upload the image
    image_arg.modify(Image.Image.resize, resolution, Image.NEAREST if "-nearest" in options else Image.ANTIALIAS,
                     convert="RGBA")
    await send_image(message, image_arg)


@plugins.command(pos_check=lambda s: s.startswith("-"), aliases="tilt")
async def rotate(message: discord.Message, image_arg: image, degrees: int, *options, extension: str.lower = None):
    """ Rotate an image clockwise using the given degrees. """
    if extension:
        image_arg.set_extension(extension)

    # Rotate and upload the image
    image_arg.modify(Image.Image.rotate, -degrees, Image.NEAREST if "-nearest" in options else Image.BICUBIC,
                     expand=True, convert="RGBA")
    await send_image(message, image_arg)


@plugins.command(name="convertimage")
async def convert(message: discord.Message, image_arg: image, extension: str.lower):
    """ Convert an image to a specified extension. """
    image_arg.set_extension(extension)
    await send_image(message, image_arg)


@plugins.command(aliases="jpg")
async def jpeg(message: discord.Message, image_arg: image, *effect: utils.choice("meme"),
               quality: utils.int_range(f=0, t=100) = 5):
    """ Give an image some proper jpeg artifacting.

    Valid effects are: `meme` """
    image_arg.modify(to_jpg, quality, real_convert=False if "meme" in effect else True)

    await send_image(message, image_arg)


@plugins.command(aliases="ff")
async def fuckify(message: discord.Message, image_arg: image, seed=None):
    """ destroy images """
    if seed:
        random.seed(seed)

    old_size = image_arg.object.size

    # Resize to small width and height values
    new_size = [random.randint(5, 40) for _ in range(2)]

    image_arg.modify([
        partial(Image.Image.resize, size=new_size, resample=Image.ANTIALIAS),
        partial(to_jpg, quality=random.randint(3, 30)),
        partial(Image.Image.resize, size=old_size, resample=Image.ANTIALIAS),
        partial(to_jpg, quality=random.randint(1, 20)),
    ], convert="RGBA")

    await send_image(message, image_arg)


@plugins.command()
async def invert(message: discord.Message, image_arg: image):
    """ Invert the colors of an image. """
    image_arg.modify(ImageOps.invert, convert="RGB")
    await send_image(message, image_arg, quality=100)


@plugins.command()
async def flip(message: discord.Message, image_arg: image, extension: str.lower = None):
    """ Flip an image in the y-axis. """
    if extension:
        image_arg.set_extension(extension)

    # Flip the image
    image_arg.modify(Image.Image.transpose, Image.FLIP_TOP_BOTTOM)
    try:
        await send_image(message, image_arg)
    except IOError:
        await client.say(message, "**The image format is not supported (must be L or RGB)**")


@plugins.command()
async def mirror(message: discord.Message, image_arg: image, extension: str.lower = None):
    """ Mirror an image along the x-axis. """
    if extension:
        image_arg.set_extension(extension)

    # Mirror the image
    image_arg.modify(Image.Image.transpose, Image.FLIP_LEFT_RIGHT)
    await send_image(message, image_arg)
