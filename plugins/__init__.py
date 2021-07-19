""" PCBOT's plugin handler.
"""

import importlib
import os
import logging
import inspect
from collections import namedtuple, defaultdict
from functools import partial
from traceback import format_exc

import discord
import pendulum

from pcbot import config, Annotate, identifier_prefix, format_exception

plugins = {}
events = defaultdict(list)
Command = namedtuple("Command", "name name_prefix aliases owner permissions roles guilds "
                                "usage description function parent sub_commands depth hidden error pos_check "
                                "disabled_pm doc_args")
lengthy_annotations = (Annotate.Content, Annotate.CleanContent, Annotate.LowerContent,
                       Annotate.LowerCleanContent, Annotate.Code)
argument_format = "{open}{name}{suffix}{close}"

owner_cfg = config.Config("owner")
CoolDown = namedtuple("CoolDown", "date command specific")
cooldown_data = defaultdict(list)  # member: []

client = None  # The client. This variable holds the bot client and is to be used by plugins


def set_client(c: discord.Client):
    """ Sets the client. Should be used before any plugins are loaded. """
    global client
    client = c


def get_plugin(name):
    """ Return the loaded plugin by name or None. """
    if name in plugins:
        return plugins[name]

    return None


def all_items():
    """ Return a view object of every loaded plugin by key, value. """
    return plugins.items()


def all_keys():
    """ Return a view object of every loaded plugin by key. """
    return plugins.keys()


def all_values():
    """ Return a view object of every loaded plugin by value. """
    return plugins.values()


def _format_usage(func, pos_check):
    """ Parse and format the usage of a command. """
    signature = inspect.signature(func)
    usage = []

    for i, param in enumerate(signature.parameters.values()):
        if i == 0:
            continue

        # If there is a placeholder annotation, this command is a group and should not have a formatted usage
        if getattr(param.annotation, "__name__", "") == "placeholder":
            return

        param_format = getattr(param.annotation, "argument", argument_format)
        name = param.name
        open, close, suffix = "[", "]", ""

        if param.default is param.empty and (param.kind is not param.VAR_POSITIONAL or pos_check is True):
            open, close = "<", ">"

        if param.kind is param.VAR_POSITIONAL or param.annotation in lengthy_annotations \
                or getattr(param.annotation, "allow_spaces", False):
            suffix = " ..."

        usage.append(param_format.format(open=open, close=close, name=name, suffix=suffix))
    else:
        return " ".join(usage)


def _parse_str_list(obj, name, cmd_name):
    """ Return the list from the parsed str or an empty list if object is None. """
    if type(obj) is str:
        return obj.split(" ")
    elif type(obj) is not list:
        if obj is not None:
            logging.warning("Invalid parameter in command '{}': {} must be a str or a list".format(cmd_name, name))
        return []


def _name_prefix(name, parent):
    """ Generate a function for generating the command's prefix in the given guild. """

    def decorator(guild: discord.Guild):
        pre = config.guild_command_prefix(guild)
        return parent.name_prefix(guild) + " " + name if parent is not None else pre + name

    return decorator


def command(**options):
    """ Decorator function that adds a command to the module's __commands dict.
    This allows the user to dynamically create commands without the use of a dictionary
    in the module itself.

    Command attributes are:
        name        : str         : The commands name. Will use the function name by default.
        aliases     : str / list  : Aliases for this command as a str separated by whitespace or a list.
        usage       : str         : The command usage following the command trigger, e.g the "[cmd]" in "help [cmd]".
        description : str         : The commands description. By default this uses the docstring of the function.
        hidden      : bool        : Whether or not to show this function in the builtin help command.
        error       : str         : An optional message to send when argument requirements are not met.
        pos_check   : func / bool : An optional check function for positional arguments, eg: pos_check=lambda s: s
                                    When this attribute is a bool and True, force positional arguments.
        doc_args    : dict        : Arguments to send to the docstring under formatting.
        owner       : bool        : When True, only triggers for the owner.
        permissions : str / list  : Permissions required for this command as a str separated by whitespace or a list.
        roles       : str / list  : Roles required for this command as a str separated by whitespace or a list.
        guilds     : str / list  : a str separated by whitespace or a list of valid guild ids.
        disabled_pm : bool        : Command is disabled in PMs when True.
    """

    def decorator(func):
        # Make sure the first parameter in the function is a message object
        params = inspect.signature(func).parameters
        param = params[list(params.keys())[0]]  # The first parameter
        if not param.name == "message" and param.annotation is not discord.Message:
            raise SyntaxError("First command parameter must be named message or be of type discord.Message")

        # Define all function stats
        name = options.get("name", func.__name__)
        aliases = options.get("aliases")
        hidden = options.get("hidden", False)
        parent = options.get("parent", None)
        depth = parent.depth + 1 if parent is not None else 0
        name_prefix = _name_prefix(name, parent)
        error = options.get("error", None)
        pos_check = options.get("pos_check", False)
        description = options.get("description") or func.__doc__ or "Undocumented."
        disabled_pm = options.get("disabled_pm", False)
        doc_args = options.get("doc_args", dict())
        owner = options.get("owner", False)
        permissions = options.get("permissions")
        roles = options.get("roles")
        guilds = options.get("guilds")

        # Parse str lists
        aliases = _parse_str_list(aliases, "aliases", name)
        permissions = _parse_str_list(permissions, "permissions", name)
        roles = _parse_str_list(roles, "roles", name)
        guilds = _parse_str_list(guilds, "guilds", name)

        # Set the usage of this command
        usage_suffix = options.get("usage", _format_usage(func, pos_check))

        # Convert to a function that uses the name_prefix
        if usage_suffix is not None:
            usage = lambda guild: name_prefix(guild) + " " + usage_suffix
        else:
            usage = lambda guild: None

        # Properly format description when using docstrings
        # Kinda like markdown; new line = (blank line) or (/ at end of line)
        if description == func.__doc__:
            new_desc = ""

            for line in description.split("\n"):
                line = line.strip()

                if line == "/":
                    new_desc += "\n\n"
                elif line.endswith("/"):
                    new_desc += line[:-1] + "\n"
                elif line == "":
                    new_desc += "\n"
                else:
                    new_desc += line + " "

            description = new_desc

        # Format the description for any optional keys, and store the {pre} argument for later
        description = description.replace("{pre}", "%pre%").format(**doc_args)
        description = description.replace("%pre%", "{pre}")

        # Notify the user about command permissions
        if owner:
            description += "\n:information_source:`Only the bot owner can execute this command.`"
        if permissions:
            description += "\n:information_source:`Permissions required: {}`".format(
                ", ".join(" ".join(s.capitalize() for s in p.split("_")) for p in permissions))
        if roles:
            description += "\n:information_source:`Roles required: {}`".format(
                ", ".join(roles))

        # Load the plugin the function is from, so that we can modify the __commands attribute
        plugin = inspect.getmodule(func)
        commands = getattr(plugin, "__commands", list())

        # Assert that __commands is usable and that this command doesn't already exist
        if type(commands) is not list:
            raise NameError("__commands is reserved for the plugin's commands, and must be of type list")

        # Assert that there are no commands already defined with the given name in this scope
        if any(cmd.name == name for cmd in (commands if not parent else parent.sub_commands)):
            raise KeyError("You can't assign two commands with the same name")

        # Create our command
        cmd = Command(name=name, aliases=aliases, usage=usage, name_prefix=name_prefix, description=description,
                      function=func, parent=parent, sub_commands=[], depth=depth, hidden=hidden, error=error,
                      pos_check=pos_check, disabled_pm=disabled_pm, doc_args=doc_args, owner=owner,
                      permissions=permissions, roles=roles, guilds=guilds)

        # If the command has a parent (is a subcommand)
        if parent:
            parent.sub_commands.append(cmd)
        else:
            commands.append(cmd)

        # Update the plugin's __commands attribute
        setattr(plugin, "__commands", commands)

        # Create a decorator for the command function that automatically assigns the parent
        setattr(func, "command", partial(command, parent=cmd))

        # Add the cmd attribute to this function, in order to get the command assigned to the function
        setattr(func, "cmd", cmd)

        logging.debug("Registered {} {} from plugin {}".format("subcommand" if parent else "command",
                                                               name, plugin.__name__))
        return func

    return decorator


def event(name=None, bot=False, self=False):
    """ Decorator to add event listeners in plugins. """

    def decorator(func):
        event_name = name or func.__name__

        if event_name == "on_ready":
            logging.warning("on_ready in plugins is reserved for bot initialization only (use it without the "
                            "event listener call). It was not added to the list of events.")
            return func

        if self and not bot:
            logging.warning("self=True has no effect in event {}. Consider setting bot=True".format(func.__name__))

        # Set the bot attribute, which determines whether the function will be triggered by messages from bot accounts
        # The self attribute denotes if own messages will be logged
        setattr(func, "bot", bot)
        setattr(func, "self", self)

        # Register our event
        events[event_name].append(func)
        return func

    return decorator


def argument(format=argument_format, *, pass_message=False, allow_spaces=False):
    """ Decorator for easily setting custom argument usage formats. """

    def decorator(func):
        func.argument = format
        func.pass_message = pass_message
        func.allow_spaces = allow_spaces
        return func

    return decorator


def format_usage(cmd: Command, guild: discord.Guild):
    """ Format the usage string of the given command. Places any usage
    of a sub command on a newline.

    :param cmd: Type Command.
    :param guild: The guild to generate the usage in.
    :return: str: formatted usage.
    """
    if cmd.hidden and cmd.parent is not None:
        return

    command_prefix = config.guild_command_prefix(guild)
    usage = [cmd.usage(guild)]
    for sub_command in cmd.sub_commands:
        # Recursively format the usage of the next sub commands
        formatted = format_usage(sub_command, guild)

        if formatted:
            usage.append(formatted)

    return "\n".join(s for s in usage if s is not None).format(pre=command_prefix) if usage else None


def format_help(cmd: Command, guild: discord.Guild, no_subcommand: bool = False):
    """ Format the help string of the given command as a message to be sent.

    :param cmd: Type Command
    :param guild: The guild to generate help in.
    :param no_subcommand: Use only the given command's usage.
    :return: str: help message.
    """
    usage = cmd.usage(guild) if no_subcommand else format_usage(cmd, guild)

    # If there is no usage, the command isn't supposed to be displayed as such
    # Therefore, we switch to using the parent command instead
    if usage is None and cmd.parent is not None:
        return format_help(cmd.parent, guild)

    command_prefix = config.guild_command_prefix(guild)
    desc = cmd.description.format(pre=command_prefix)

    # Format aliases
    alias_format = ""
    if cmd.aliases:
        # Don't add blank space unless necessary
        if not desc.strip().endswith("```"):
            alias_format += "\n"

        alias_format += "**Aliases**: ```{}```".format(
            ", ".join((command_prefix if identifier_prefix.match(alias[0]) and cmd.parent is None else "") +
                      alias for alias in cmd.aliases))

    return "**Usage**: ```{}```**Description**: {}{}".format(usage, desc, alias_format)


def parent_attr(cmd: Command, attr: str):
    """ Return the attribute from the parent if there is one. """
    return getattr(cmd.parent, attr, False) or getattr(cmd, attr)


def compare_command_name(trigger: str, cmd: Command, case_sensitive: bool = True):
    """ Compare the given trigger with the command's name and aliases.

    :param trigger: a str representing the command name or alias.
    :param cmd: The Command object to compare.
    :param case_sensitive: When True, case is preserved in command name triggers.
    """
    if case_sensitive:
        return trigger == cmd.name or trigger in cmd.aliases
    else:
        return trigger.lower() == cmd.name.lower() or trigger.lower() in (name.lower() for name in cmd.aliases)


def get_command(trigger: str, case_sensitive: bool = True):
    """ Find and return a command function from a plugin.

    :param trigger: a str representing the command name or alias.
    :param case_sensitive: When True, case is preserved in command name triggers.
    """
    for plugin in all_values():
        commands = getattr(plugin, "__commands", None)

        # Skip any plugin with no commands
        if not commands:
            continue

        for cmd in plugin.__commands:
            if compare_command_name(trigger, cmd, case_sensitive):
                return cmd
        else:
            continue

    return None


def get_sub_command(cmd, *args: str, case_sensitive: bool = True):
    """ Go through all arguments and return any group command function.

    :param cmd: type plugins.Command
    :param args: str of arguments following the command trigger.
    :param case_sensitive: When True, case is preserved in command name triggers.
    """
    for arg in args:
        for sub_cmd in cmd.sub_commands:
            if compare_command_name(arg, sub_cmd, case_sensitive):
                cmd = sub_cmd
                break
        else:
            break

    return cmd


def is_owner(user: discord.User):
    """ Return true if user/member is the assigned bot owner.

    :param user: discord.User, discord.Member or a str representing the user's ID.
    :raises: TypeError: user is wrong type.
    """
    if hasattr(user, 'id'):
        user = str(user.id)
    elif type(user) is not str:
        raise TypeError("member must be an instance of discord.User or a str representing the user's ID.")

    if user == owner_cfg.data:
        return True

    return False


def has_permissions(cmd: Command, author: discord.Member, channel: discord.TextChannel):
    """ Return True if the member has permissions to execute the command. """
    if not cmd.permissions:
        return True

    member_perms = author.permissions_in(channel)
    if all(getattr(member_perms, perm, False) for perm in cmd.permissions):
        return True

    return False


def has_roles(cmd: Command, author: discord.Member):
    """ Return True if the member has the required roles.
    """
    if not cmd.roles:
        return True

    member_roles = [r.name for r in author.roles[1:]]
    if any(r in member_roles for r in cmd.roles):
        return True

    return False


def is_valid_guild(cmd: Command, guild: discord.Guild):
    """ Return True if the command is allowed in guild. """
    if not cmd.guilds or guild.id in cmd.guilds:
        return True

    return False


def can_use_command(cmd: Command, author, channel: discord.TextChannel = None):
    """ Return True if the member who sent the message can use this command. """
    if cmd.owner and not is_owner(author):
        return False
    if channel is not None and not has_permissions(cmd, author, channel):
        return False
    if not has_roles(cmd, author):
        return False

    # Handle guild specific commands for both guild and PM commands
    if type(author) is discord.User and cmd.guilds:
        return False
    if type(author) is discord.Member and not is_valid_guild(cmd, author.guild):
        return False

    return True


async def execute(cmd, message: discord.Message, *args, **kwargs):
    """ Execute a command specified by name, alias or command object.
    This is really only useful as a shortcut for other commands.

    :param cmd: either plugins.Command or str
    :param message: required message object in order to execute a command
    :param args, kwargs: any arguments passed into the command.

    :raises: NameError when command does not exist.
    """
    # Get the command object if the given command represents a name
    if type(cmd) is not Command:
        cmd = get_command(cmd, config.guild_case_sensitive_commands(message.guild))

    try:
        await cmd.function(message, *args, **kwargs)
    except AttributeError:
        raise NameError("{} is not a command".format(cmd))


def get_cooldown(member: discord.Member, cmd: Command):
    """ Returns the member's time left as a str or None.
    """
    if member not in cooldown_data:
        return None

    for cooldown in cooldown_data[member]:
        if cooldown.command == cmd or cooldown.command is None:
            diff = cooldown.date - pendulum.now()
            if diff.seconds < 0:
                cooldown_data[member].remove(cooldown)
                return None

            return diff.in_words()
    else:
        return None


def load_plugin(name: str, package: str = "plugins"):
    """ Load a plugin with the name name. If package isn't specified, this
    looks for plugin with specified name in /plugins/

    Any loaded plugin is imported and stored in the self.plugins dictionary.
    """
    if not name.startswith("__") or not name.endswith("__"):
        try:
            plugin = importlib.import_module("{package}.{plugin}".format(plugin=name, package=package))
        except ImportError as e:
            logging.error("An error occurred when loading plugin {}:\n{}".format(name, format_exception(e)))
            return False
        except:
            logging.error("An error occurred when loading plugin {}:\n{}".format(name, format_exc()))
            return False

        plugins[name] = plugin
        logging.debug("LOADED PLUGIN " + name)
        return True

    return False


async def on_reload(name: str):
    """ The default on_reload function.
    """
    await reload(name)


async def reload(name: str):
    """ Reload a plugin.

    This must be called from an on_reload function or coroutine.
    """
    if name in plugins:
        # Remove all registered commands
        if hasattr(plugins[name], "__commands"):
            delattr(plugins[name], "__commands")

        # Remove all registered events from the given plugin
        for event_name, funcs in events.items():
            for func in funcs:
                if func.__module__.endswith(name):
                    events[event_name].remove(func)

        plugins[name] = importlib.reload(plugins[name])

        logging.debug("Reloaded plugin {}".format(name))


async def call_reload(name: str):
    """ Initiates reload of plugin. """
    # See if the plugin has an on_reload() function, and call that
    if hasattr(plugins[name], "on_reload"):
        if callable(plugins[name].on_reload):
            result = plugins[name].on_reload(name)
            if inspect.isawaitable(result):
                await result
    else:
        await on_reload(name)


def unload_plugin(name: str):
    """ Unload a plugin by removing it from the plugin dictionary. """
    if name in plugins:
        del plugins[name]
        logging.debug("Unloaded plugin {}".format(name))


def load_plugins():
    """ Perform load_plugin(name) on all plugins in plugins/ """
    if not os.path.exists("plugins/"):
        os.mkdir("plugins/")

    for plugin in os.listdir("plugins/"):
        name = os.path.splitext(plugin)[0]

        if not name.endswith("lib"):  # Exclude libraries
            load_plugin(name)


async def save_plugin(name):
    """ Save a plugin's files if it has a save function. """
    if name in all_keys():
        plugin = get_plugin(name)

        if callable(getattr(plugin, "save", False)):
            try:
                await plugin.save(plugins)
            except:
                logging.error("An error occurred when saving plugin {}:\n{}".format(name, format_exc()))


async def save_plugins():
    """ Looks for any save function in a plugin and saves.
    Set up for saving on !stop and periodic saving every 30 minutes.
    """
    for name in all_keys():
        await save_plugin(name)


@argument(format="{open}on | off{close}")
def true_or_false(arg: str):
    """ Return True or False flexibly based on the input. """
    if arg.lower() in ("yes", "true", "enable", "1", "on"):
        return True
    elif arg.lower() in ("no", "false", "disable", "0", "off"):
        return False
    else:
        return None
