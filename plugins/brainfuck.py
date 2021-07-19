""" Plugin for compiling and executing brainfuck code. """
import asyncio

import discord

import plugins
from pcbot import Annotate, Config

client = plugins.client  # type: discord.Client

cfg = Config("brainfuck", data={})  # Keys are names and values are dict with author, code
max_iterations = 2 ** 17
brainfuck_chars = "+-><][.,"


class Loop:
    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.pointer = None

    def set_pointer(self, pointer):
        self.pointer = (pointer.cursor, pointer.value)

    def compare_pointer(self, pointer):
        if self.pointer is None:
            return False

        return self.pointer == (pointer.cursor, pointer.value)


class TooManyIterations(Exception):
    pass


class InfiniteLoop(Exception):
    pass


class Pointer:
    cells = 2 ** 15
    cell_size = 2 ** 8 - 1

    def __init__(self):
        self.array = [0] * self.cells
        self.cursor = 0

    @property
    def value(self):
        return self.array[self.cursor]

    @value.setter
    def value(self, value):
        self.array[self.cursor] = value

    def add(self):
        self.value += 1
        if self.value > self.cell_size:
            self.value = 0

    def sub(self):
        self.value -= 1
        if self.value < 0:
            self.value = self.cell_size

    def right(self):
        self.cursor += 1
        if self.cursor >= self.cells:
            self.cursor = 0

    def left(self):
        self.cursor -= 1
        if self.cursor < 0:
            self.cursor = self.cells - 1


def find_loop_end(code: str, start: int):
    nest = 1
    for i, c in enumerate(code):
        if c == "[":
            nest += 1
        elif c == "]":
            nest -= 1

        if nest == 0:
            return start + i

    raise SyntaxError("{}: Loop never ends!".format(start))


def run_brainfuck(code: str, for_input: str = ""):
    pointer = Pointer()
    input_pointer = Pointer()
    input_pointer.array[:len(for_input)] = list(ord(c) for c in for_input)
    loops = []

    i, iterations = 0, 0
    output = ""
    while True:
        char = code[i]

        if char == "+":
            pointer.add()
        elif char == "-":
            pointer.sub()
        elif char == ">":
            pointer.right()
        elif char == "<":
            pointer.left()
        elif char == ".":
            output += chr(pointer.value)
        elif char == ",":
            pointer.value = input_pointer.value
            input_pointer.right()
            if loops:
                loops[-1].pointer = None
        elif char == "[":
            end = find_loop_end(code[i + 1:], i)
            loops.append(Loop(start=i, end=end))
            if pointer.value == 0:
                i = end
        elif char == "]":
            if loops:
                if loops[-1].compare_pointer(pointer):
                    raise InfiniteLoop("{}: Pointer value unchanged.".format(loops[-1].start))

                if not pointer.value == 0:
                    i = loops[-1].start
                    loops[-1].set_pointer(pointer)
                else:
                    del loops[-1]

        i += 1
        if i >= len(code):
            return output or "Pointer value: {}".format(pointer.value)

        iterations += 1
        if iterations >= max_iterations:
            raise TooManyIterations("Program exceeded maximum number of iterations ({})".format(max_iterations))


async def brainfuck_in_channel(channel: discord.TextChannel, code, program_input):
    try:
        output = run_brainfuck(code, program_input)
    except Exception as e:
        await client.send_message(channel, "```\n{}: {}```".format(type(e).__name__, str(e)))
    else:
        assert len(output) <= 2000, "**The output was too long.**"
        await client.send_message(channel, "```\n{}```".format(output))


@plugins.command(aliases="bf")
async def brainfuck(message: discord.Message, code: Annotate.Code):
    """ Run the given brainfuck code and prompt for input if required.

    This interpretation of brainfuck always returns a value with the , command,
    which means that whenever there is no input to retrieve, a 0 would be inserted
    in the pointer cell. """
    program_input = ""
    if "," in code:
        await client.say(message, "**Input required, please type:**")

        def check(m):
            return m.author == message.author and m.channel == message.channel

        try:
            reply = await client.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            await client.say(message, "**You failed to reply.**")
            return

        program_input = reply.clean_content

    await brainfuck_in_channel(message.channel, code, program_input)


@plugins.argument()
def snippet_name(name: str):
    try:
        name = str(name).lower()
    except:
        return None

    return name.replace(" ", "")


def assert_exists(name: str):
    """ Check if the brainfuck entry exists. """
    assert name in cfg.data, "No saved entry with name `{}`.".format(name)


def assert_author(name: str, member: discord.Member):
    """ Make sure that whoever is modifying a brainfuck entry
    is the author of said entry. """
    author = cfg.data[name]["author"]
    assert author == str(member.id), "You are not the author of this entry. **({})**".format(author or "Unknown author")


@brainfuck.command(aliases="exec do load")
async def run(message: discord.Message, name: snippet_name, args: Annotate.CleanContent = ""):
    """ Run an entry of brainfuck code. Explore entries with `{pre}brainfuck list`."""
    assert_exists(name)

    code = cfg.data[name]["code"]
    await brainfuck_in_channel(message.channel, code, args)


@brainfuck.command(aliases="create set")
async def add(message: discord.Message, name: snippet_name, code: Annotate.Code):
    """ Adds a brainfuck snippet entry with the given code. This code can be executed
    with `{pre}brainfuck run`."""
    assert name not in cfg.data, "Entry `{}` already exists.".format(name)

    cfg.data[name] = dict(author=str(str(message.author.id)), code=code)
    await cfg.asyncsave()
    await client.say(message, "Entry `{}` created.".format(name))


@brainfuck.command(aliases="extend more")
async def append(message: discord.Message, name: snippet_name, code: Annotate.Code):
    """ Appends brainfuck to the specified entry. Only the creator of said entry
    can append to its code. """
    assert_exists(name)
    assert_author(name, message.author)

    cfg.data[name]["code"] += code
    await cfg.asyncsave()
    await client.say(message, "The given code was appended to `{}`.".format(name))


@brainfuck.command(aliases="delete")
async def remove(message: discord.Message, name: snippet_name):
    """ Remove one of your brainfuck entries. """
    assert_exists(name)
    assert_author(name, message.author)

    del cfg.data[name]
    await cfg.asyncsave()
    await client.say(message, "Removed entry with name `{}`.".format(name))


@brainfuck.command(name="list")
async def list_entries(message: discord.Message):
    """ Display a list of all brainfuck entries. """
    await client.say(message, "**Entries:**```\n{}```".format(", ".join(cfg.data.keys())))


@brainfuck.command(aliases="min reduce")
async def minimize(message: discord.Message, code: Annotate.Code):
    """ Minimize the given code by removing everything that is not recognized
    brainfuck code. """
    await client.say(message, "```\n{}```".format("".join(c for c in code if c in brainfuck_chars)))


@brainfuck.command(aliases="code")
async def source(message: discord.message, name: snippet_name):
    """ Display the source code of a brainfuck program. """
    assert_exists(name)
    code = cfg.data[name]["code"]

    m = "```{}```".format(code)
    if len(m) > 2000:
        await client.say(message, "The code for this entry exceeds 2000 characters.")
    else:
        await client.say(message, m)
