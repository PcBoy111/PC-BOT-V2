""" Any utility functions.

This module holds the owner data along with a handful of
command specific functions and helpers.
"""

import re
import shlex
from enum import Enum
from functools import wraps
from io import BytesIO

import aiohttp
import discord
from asyncio import subprocess as sub

member_mention_pattern = re.compile(r"<@!?(?P<id>\d+)>")
channel_mention_pattern = re.compile(r"<#(?P<id>\d+)>")
markdown_code_pattern = re.compile(r"^(?P<capt>`*)(?:[a-z]+\n)?(?P<code>.+)(?P=capt)$", flags=re.DOTALL)
http_url_pattern = re.compile(r"(?P<protocol>https?://)(?P<host>[a-z0-9-]+\.[a-z0-9-.]+/?)(?P<sub>\S+)?",
                              flags=re.IGNORECASE)
identifier_prefix = re.compile(r"[a-zA-Z_]")

client = None  # Declare the Client. For python 3.6: client: discord.Client


def set_client(c: discord.Client):
    """ Assign the client to a variable. """
    global client
    client = c


class Annotate(Enum):
    """ Command annotation enum.
    Annotate a command argument with one of these to get the commented result.
    """
    Content = 1  # Return all the content after command and/or arguments with Message.content
    LowerContent = 2  # Same as above but returns the contents in lowercase
    CleanContent = 3  # Return all the content after command and/or arguments with Message.clean_content
    LowerCleanContent = 4  # Same as above but returns the contents in lowercase
    User = Member = 5  # Return a member (uses utils.find_member with steps=3)
    Channel = 6  # Return a channel (uses utils.find_channel with steps=3)
    VoiceChannel = 7  # Return a voice channel (uses utils.find_channel with steps=3 and channel_type="voice")
    Self = 8  # Used as a default for Member/Channel annotations and returns the message.author/message.channel
    Code = 9  # Get formatted code (like Content but extracts any code)


def int_range(f: int = None, t: int = None):
    """ Return a helper function for checking if a str converted to int is in the
    specified range, f (from) - t (to).

    :param f: From: where the range starts. -inf if omitted.
    :param t: To: where the range ends. +inf if omitted.
    """

    def wrapped(arg: str):
        # Convert to int and return None if unsuccessful
        try:
            num = int(arg)
        except ValueError:
            return None

        # Compare the lowest and highest numbers
        if (f and num < f) or (t and num > t):
            return None

        # The string given is converted to a number and fits the criteria
        return num

    return wrapped


def choice(*options: str, ignore_case: bool = True):
    """ Return a helper function for checking if the argument is either of the
    given options.

    :param options: Any number of strings to choose from.
    :param ignore_case: Do not compare case-sensitively.
    """

    def wrapped(arg: str):
        # Compare lowercased version
        if ignore_case:
            return arg if arg.lower() in [s.lower() for s in options] else None
        else:
            return arg if arg in options else None

    return wrapped


def placeholder(_: str):
    """ Return False. Using this as a command argument annotation will always fail
    the command. Useful for groups.
    """
    return False


async def confirm(message: discord.Message, text: str, timeout: int = 10):
    """ Have the message author confirm their action. """
    await client.send_message(message.channel,
                                  text + " [{}{}]".format(str(timeout) + "s " if timeout else "", "yes/no"))
    author = message.author
    channel = message.channel

    def new_check(m):
        return lambda n: m.content.lower() in ("y", "yes", "n", "no") and m.author == author and m.channel == channel

    reply = await client.wait_for("message", check=new_check, timeout=timeout)

    if reply and reply.content.lower() in ("y", "yes"):
        return True

    return False


def permission(*perms: str):
    """ Decorator that runs the command only if the author has the specified permissions.
    perms must be a string matching any property of discord.Permissions.

    NOTE: this function is deprecated. Use the command 'permissions' attribute instead.
    """

    def decorator(func):
        @wraps(func)
        async def wrapped(message: discord.Message, *args, **kwargs):
            member_perms = message.author.permissions_in(message.channel)

            if all(getattr(member_perms, perm, False) for perm in perms):
                await func(message, *args, **kwargs)

        return wrapped

    return decorator


def role(*roles: str):
    """ Decorator that runs the command only if the author has the specified Roles.
    roles must be a string representing a role's name. 
    
    NOTE: this function is deprecated. Use the command 'roles' attribute instead.
    """

    def decorator(func):
        @wraps(func)
        async def wrapped(message: discord.Message, *args, **kwargs):
            member_roles = [r.name for r in message.author.roles[1:]]

            if any(r in member_roles for r in roles):
                await func(message, *args, **kwargs)

        return wrapped

    return decorator


async def subprocess(*args, pipe=None, carriage_return=False):
    """ Run a subprocess and return the output.

    :param args: Arguments to be passed to the subprocess
    :param pipe: Any optional input for the stdin.
    :param carriage_return: When True, carriage returns, \r, are not removed from the result.
    """
    process = await sub.create_subprocess_exec(*args, stdout=sub.PIPE, stdin=sub.PIPE, stderr=sub.PIPE)
    stdout, stderr = await process.communicate(input=bytes(pipe, encoding="utf-8") if pipe else None)

    stdout = stdout.decode("utf-8")
    stderr = stderr.decode("utf-8")

    # There were some problems with the carriage_return in windows, so by default they're removed
    if not carriage_return:
        stdout = stdout.replace("\r", "")
        stderr = stderr.replace("\r", "")

    if stderr:
        raise Exception(stderr)

    return stdout


async def retrieve_page(url: str, head=False, call=None, headers=None, **params):
    """ Download and return a website with aiohttp.

    :param url: Download url as str.
    :param head: Whether or not to head the function.
    :param call: Any attribute coroutine to call before returning. Eg: "text" would return await response.text().
                 This may also be a coroutine with the response as parameter.
    :param headers: A dict of any additional headers.
    :param params: Any additional url parameters.
    :return: The byte-like file OR whatever return value of the attribute set in call.
    """
    async with aiohttp.ClientSession(loop=client.loop) as session:
        coro = session.head if head else session.get

        async with coro(url, params=params, headers=headers or {}) as response:
            if call is not None:
                if type(call) is str:
                    attr = getattr(response, call)
                    return await attr()
                else:
                    return await call(response)
            else:
                return response


async def retrieve_headers(url: str, headers=None, **params):
    """ Retrieve the headers from a URL.

    :param url: URL as str.
    :param headers: A dict of any additional headers.
    :param params: Any additional url parameters.
    :return: Headers as a dict.
    """
    head = await retrieve_page(url, head=True, headers=headers, **params)
    return head.headers


async def retrieve_html(url: str, headers=None, **params):
    """ Retrieve the html from a URL.

    :param url: URL as str.
    :param headers: A dict of any additional headers.
    :param params: Any additional url parameters.
    :return: HTML as str.
    """
    return await retrieve_page(url, call="text", headers=headers, **params)


async def download_file(url: str, bytesio=False, headers=None, **params):
    """ Download and return a byte-like object of a file.

    :param url: Download url as str.
    :param bytesio: Convert this object to BytesIO before returning.
    :param headers: A dict of any additional headers.
    :param params: Any additional url parameters.
    :return: The byte-like file.
    """
    file_bytes = await retrieve_page(url, call="read", headers=headers, **params)
    return BytesIO(file_bytes) if bytesio else file_bytes


async def _convert_json(response):
    """ Converts the aiohttp ClientResponse object to JSON.

    :param response: The ClientResponse object.
    :raises: ValueError if the returned data was not of type application/json
    :returns: The parsed json of the response
    """
    if "Content-Type" in response.headers and "application/json" not in response.headers["Content-Type"]:
        raise ValueError("The response from {} does not have application/json mimetype".format(response.url))

    return await response.json()


async def download_json(url: str, headers=None, **params):
    """ Download and return a json file.

    :param url: Download url as str.
    :param headers: A dict of any additional headers.
    :param params: Any additional url parameters.
    :raises: ValueError if the returned data was not of type application/json
    :return: A JSON representation of the downloaded file.
    """
    return await retrieve_page(url, call=_convert_json, headers=headers, **params)


def convert_image_object(image, format: str = "PNG", **params):
    """ Saves a PIL.Image.Image object to BytesIO buffer. Effectively
    returns the byte-like object for sending through discord.Client.send_file.
    
    :param image: PIL.Image.Image: object to convert.
    :param format: The image format, defaults to PNG.
    :param params: Any additional parameters sent to the writer.
    :return: BytesIO: the image object in bytes.
    """
    buffer = BytesIO()
    image.save(buffer, format, **params)
    buffer.seek(0)
    return buffer


def find_member(guild: discord.Guild, name, steps=3, mention=True):
    """ Find any member by their name or a formatted mention.
    Steps define the depth at which to search. More steps equal
    less accurate checks.

    +--------+------------------+
    |  step  |     function     |
    +--------+------------------+
    |    0   | perform no check |
    |    1   |   name is equal  |
    |    2   | name starts with |
    |    3   |    name is in    |
    +--------+------------------+

    :param guild: discord.Guild to look through for members.
    :param name: display_name as a string or mention to find.
    :param steps: int from 0-3 to specify search depth.
    :param mention: bool, check for mentions.
    :return: discord.Member
    """
    member = None

    # Return a member from mention
    found_mention = member_mention_pattern.search(name)
    if found_mention and mention:
        member = guild.get_member(int(found_mention.group("id")))
        return member

    name = name.lower()

    # Steps to check, higher values equal more fuzzy checks
    checks = [lambda m: m.name.lower() == name or m.display_name.lower() == name,
              lambda m: m.name.lower().startswith(name) or m.display_name.lower().startswith(name),
              lambda m: name in m.display_name.lower() or name in m.name.lower()]

    for i in range(steps if steps <= len(checks) else len(checks)):
        member = discord.utils.find(checks[i], guild.members)

        if member:
            break

    # Return the found member or None
    return member


def find_channel(guild: discord.Guild, name, steps=3, mention=True, channel_type="text"):
    """ Find any channel by its name or a formatted mention.
    Steps define the depth at which to search. More steps equal
    less accurate checks.

    +--------+------------------+
    |  step  |     function     |
    +--------+------------------+
    |    0   | perform no check |
    |    1   |   name is equal  |
    |    2   | name starts with |
    |    3   |    name is in    |
    +--------+------------------+

    :param guild: discord.Guild to look through for channels.
    :param name: name as a string or mention to find.
    :param steps: int from 0-3 to specify search depth.
    :param mention: check for mentions.
    :param channel_type: what type of channel we're looking for. Can be str or discord.ChannelType.
    :return: discord.Channel
    """
    channel = None

    # We want to allow both str and discord.ChannelType, so try converting str and handle exceptions
    if type(channel_type) is str:
        try:
            channel_type = getattr(discord.ChannelType, channel_type)
        except AttributeError:
            raise TypeError("channel_type (str) must be an attribute of discord.ChannelType")
    elif type(channel_type) is not discord.ChannelType:
        raise TypeError("channel_type must be discord.ChannelType or a str of a discord.ChannelType attribute")

    # Return a member from mention
    found_mention = channel_mention_pattern.search(name)
    if found_mention and mention and channel_type is discord.ChannelType.text:
        channel = guild.get_channel(int(found_mention.group("id")))

    if not channel:
        # Steps to check, higher values equal more fuzzy checks
        checks = [lambda c: c.name.lower() == name.lower() and c.type is channel_type,
                  lambda c: c.name.lower().startswith(name.lower()) and c.type is channel_type,
                  lambda c: name.lower() in c.name.lower() and c.type is channel_type]

        for i in range(steps if steps <= len(checks) else len(checks)):
            channel = discord.utils.find(checks[i], guild.channels)

            if channel:
                break

    # Return the found channel or None
    return channel


def format_exception(e: Exception):
    """ Returns a formatted string as Exception: e """
    return type(e).__name__ + ": " + str(e)


def format_syntax_error(e: Exception):
    """ Returns a formatted string of a SyntaxError.
    Stolen from https://github.com/Rapptz/RoboDanny/blob/master/cogs/repl.py#L24-L25
    """
    return "{0.text}\n{1:>{0.offset}}\n{2}: {0}".format(e, "^", type(e).__name__).replace("\n\n", "\n")


def format_objects(*objects, attr=None, dec: str = "", sep: str = None):
    """ Return a formatted string of objects (User, Member, Channel or Guild) using
    the given decorator and the given separator.

    :param objects: Any object with attributes, preferably User, Member, Channel or Guild.
    :param attr: The attribute to get from any object. Defaults to object names.
    :param dec: String to decorate around each object.
    :param sep: Separator between each argument.
    :return: str: the formatted objects.
    """
    if not objects:
        return

    first_object = objects[0]
    if attr is None:
        if isinstance(first_object, discord.Member):
            attr = "display_name"
        elif isinstance(first_object, discord.TextChannel) or isinstance(first_object, discord.Role):
            attr = "mention"
            sep = " "
        elif isinstance(first_object, discord.Guild):
            attr = "name"

    sep = sep if sep is not None else ", "

    return sep.join(dec + getattr(m, attr) + dec for m in objects)


def get_formatted_code(code: str):
    """ Format code from markdown format. This will filter out markdown code
    and give the executable python code, or raise an exception.

    :param code: Code formatted in markdown.
    :return: str: Code.
    """
    code = code.strip(" \n")
    match = markdown_code_pattern.match(code)

    if match:
        code = match.group("code")

        # Try finding the code via match, and make sure it wasn't somehow corrupt before returning
        if not code == "`":
            return code

    raise Exception("Could not format code.")


def format_code(code: str, language: str = None, *, simple: bool = False):
    """ Format markdown code.

    :param code: Code formatted in markdown.
    :param language: Optional syntax highlighting language.
    :param simple: Use single quotes, e.g `"Hello!"`
    :return: str of markdown code.
    """
    if simple:
        return "`{}`".format(code)
    else:
        return "```{}\n{}```".format(language or "", code)


async def convert_to_embed(text: str, *, author: discord.Member = None, **kwargs):
    """ Convert text to an embed, where urls will be embedded if the url is an image.

    :param text: str to convert.
    :param author: Additionally format an author.
    :param kwargs: Any kwargs to be passed to discord.Embed's init function.
    """
    embed = discord.Embed(**kwargs)
    url = embed.Empty

    # Find the first url or None
    for word in text.split():
        url_match = http_url_pattern.match(word)

        # Handle urls
        if url_match:
            url = url_match.group(0)
            headers = await retrieve_headers(url)

            # Remove the url from the text and use it as a description
            text = text.replace(url, "")
            embed.description = text or None

            # If the url is an image, embed it
            if "Content-Type" in headers and "image" in headers["Content-Type"]:
                embed.set_image(url=url)

            # If the embed isn't an image, we'll just use it as the embed url
            else:
                embed.url = url
            break
    else:
        embed.description = text

    # Set the author if given
    if author:
        embed.set_author(name=author.display_name, icon_url=author.avatar_url, url=url)

    return embed


def text_to_emoji(text: str):
    """ Convert text to a string of regional emoji.
    Text must only contain characters in the alphabet from A-Z.

    :param text: text of characters in the alphabet from A-Z.
    :return: str: formatted emoji unicode.
    """
    regional_offset = 127397  # This number + capital letter = regional letter
    return "".join(chr(ord(c) + regional_offset) for c in text.upper())


def split(text: str, maxsplit: int = -1):
    """ Split a string with shlex when possible, and add support for maxsplit.

    :param text: Text to split.
    :param maxsplit: Number of times to split. The rest is returned without splitting.
    :return: list: split text.
    """
    # Generate a shlex object for eventually splitting manually
    split_object = shlex.shlex(text, posix=True)
    split_object.quotes = '"`'
    split_object.whitespace_split = True
    split_object.commenters = ""

    # When the maxsplit is disabled, return the entire split object
    if maxsplit == -1:
        try:
            return list(split_object)
        except ValueError:  # If there is a problem with quotes, use the regular split method
            return text.split()

    # Create a list for the following split keywords
    maxsplit_object = []
    splits = 0

    # Split until we've reached the limit
    while splits < maxsplit:
        maxsplit_object.append(next(split_object))
        splits += 1

    # Add any following text without splitting
    maxsplit_object.append(split_object.instream.read())
    return maxsplit_object
