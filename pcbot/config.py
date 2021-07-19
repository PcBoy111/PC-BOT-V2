""" Handle any bot specific configs.

This module includes the command syntax, github repo path,
setting the bot's version and a class for creating configs.
"""

import json
from os.path import exists
from os import mkdir, walk, path, rename

import discord

try:
    import aiofiles

    async_io = True
except ImportError:
    async_io = False

github_repo = "pckv/pcbot/"
default_command_prefix = "!"
default_case_sensitive_commands = True
help_arg = ("?", "help")
version = ""
name = "PCBOT"  # Placebo name, should be changed on_ready
owner_error = False  # Whether the bot owner should receive error messages in chat


def set_version(ver: str):
    """ Set the version of the API. This function should really only
    be used in bot.py.
    """
    global version
    version = ver
    return version


def migrate():
    directory = "config/"
    find = "server"
    replace = "guild"
    for root, dirs, filenames in walk(directory):
        dirs[:] = [d for d in dirs if d != '.git']  # skip .git dirs
        for filename in filenames:
            path1 = path.join(root, filename)
            # search and replace within files themselves
            filepath = path.join(root, filename)
            with open(filepath) as f:
                file_contents = json.load(f)
                if isinstance(file_contents, dict):
                    for keys in list(file_contents.keys()):
                        if find in keys:
                            with open(filepath, "w") as e:
                                file_contents[keys.replace(find, replace)] = file_contents[keys]
                                del file_contents[keys]
                                if "bot_meta" in filename or "blacklist" in filename or "osu" in filename or \
                                        "summary_options" in filename or "would_you-rather" in filename:
                                    json.dump(file_contents, e, sort_keys=True, indent=4)
                                else:
                                    json.dump(file_contents, e)

            # rename files (ignoring file extensions)
            filename_zero, extension = path.splitext(filename)
            if find in filename_zero:
                path2 = path.join(root, filename_zero.replace(find, replace) + extension)
                rename(path1, path2)


class Config:
    config_path = "config/"

    def __init__(self, filename: str, data=None, load: bool = True, pretty=False):
        """ Setup the config file if it does not exist.

        :param filename: usually a string representing the module name.
        :param data: default data setup, usually an empty/defaulted dictionary or list.
        :param load: should the config file load when initialized? Only loads when a config already exists.
        """
        self.filepath = "{}{}.json".format(self.config_path, filename)
        self.pretty = pretty

        if not exists(self.config_path):
            mkdir(self.config_path)

        loaded_data = self.load() if load else None

        if data is not None and not loaded_data:
            self.data = data
        elif loaded_data:
            # If the default data is a dict, compare and add missing keys
            updated = False
            if type(loaded_data) is dict:
                for k, v in data.items():
                    if k not in loaded_data:
                        loaded_data[k] = v
                        updated = True

            self.data = loaded_data

            if updated:
                self.save()
        else:
            self.data = None

        if not self.data == loaded_data:
            self.save()

    def save(self):
        """ Write the current config to file. """
        with open(self.filepath, "w") as f:
            if self.pretty:
                json.dump(self.data, f, sort_keys=True, indent=4)
            else:
                json.dump(self.data, f)

    async def asyncsave(self):
        """ Write the current config to file asynchronously. """
        if async_io:
            async with aiofiles.open(self.filepath, "w") as f:
                if self.pretty:
                    await f.write(json.dumps(self.data, sort_keys=True, indent=4))
                else:
                    await f.write(json.dumps(self.data))
        else:
            self.save()

    def load(self):
        """ Load the config from file if it exists.

        :return: config parsed from json or None
        """
        if exists(self.filepath):
            with open(self.filepath) as f:
                return json.load(f)

        return None


guild_config = Config("guild-config", data={})


async def set_guild_config(guild: discord.Guild, key: str, value):
    """ Set a guild config value. """
    if str(guild.id) not in guild_config.data:
        guild_config.data[str(guild.id)] = {}

    # Change the value or remove it from the list if the value is None
    if value is None:
        del guild_config.data[str(guild.id)][key]
    else:
        guild_config.data[str(guild.id)][key] = value

    await guild_config.asyncsave()


def guild_command_prefix(guild: discord.Guild):
    """ Get the guild's command prefix. """
    if guild is not None and str(guild.id) in guild_config.data:
        return guild_config.data[str(guild.id)].get("command_prefix", default_command_prefix)

    return default_command_prefix


def guild_case_sensitive_commands(guild: discord.Guild):
    """ Get the guild's case sensitivity settings. """
    if guild is not None and str(guild.id) in guild_config.data:
        return guild_config.data[str(guild.id)].get("case_sensitive_commands", default_case_sensitive_commands)

    return default_case_sensitive_commands
