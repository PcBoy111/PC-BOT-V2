""" Plugin for creating user based alias commands

Commands:
alias
"""
import discord

from pcbot import Config, Annotate, config, utils
import plugins

client = plugins.client  # type: discord.Client

alias_desc = \
    "Assign an alias command, where trigger is the command in it's entirety: `{pre}cmd` or `>cmd` or `cmd`.\n" \
    "Feel free to use spaces in a **trigger** by *enclosing it with quotes*, like so: `\"{pre}my cmd\"`.\n\n" \
    "**Options**:\n" \
    "`-anywhere` makes the alias trigger anywhere in a message, and not just the start of a message.\n" \
    "`-case-sensitive` ensures that you *need* to follow the same casing.\n" \
    "`-delete-message` removes the original message. This option can not be mixed with the `-anywhere` option.\n" \

aliases = Config("user_alias", data={})


@plugins.command(description=alias_desc, pos_check=lambda s: s.startswith("-"))
async def alias(message: discord.Message, *options: str.lower, trigger: str, text: Annotate.Content):
    """ Assign an alias. Description is defined in alias_desc. """
    anywhere = "-anywhere" in options
    case_sensitive = "-case-sensitive" in options
    delete_message = not anywhere and "-delete-message" in options

    if str(message.author.id) not in aliases.data:
        aliases.data[str(message.author.id)] = {}

    # Set options
    aliases.data[str(message.author.id)][trigger if case_sensitive else trigger.lower()] = dict(
        text=text,
        anywhere=anywhere,
        case_sensitive=case_sensitive,
        delete_message=delete_message
    )
    await aliases.asyncsave()

    m = "**Alias assigned.** Type `{}`{} to trigger the alias."
    await client.say(message, m.format(trigger, " anywhere in a message" if anywhere else ""))


@alias.command(name="list")
async def list_aliases(message: discord.Message, member: discord.Member = Annotate.Self):
    """ List all user's aliases. """
    assert str(message.author.id) in aliases.data, "**{} has no aliases.**".format(member.display_name)

    # The user is registered so they must have aliases and we display them
    format_aliases = ", ".join(aliases.data[str(member.id)].keys())
    await client.say(message, "**Aliases for {}:**```\n{}```\n".format(member.display_name, format_aliases))


@alias.command()
async def remove(message: discord.Message, trigger: Annotate.Content):
    """ Remove user alias with the specified trigger. Use `*` to delete all. """
    if trigger == "*":
        aliases.data[str(message.author.id)] = {}
        await aliases.asyncsave()
        await client.say(message, "**Removed all aliases.**")

    # Check if the trigger is in the would be list (basically checks if trigger is in [] if user is not registered)
    assert trigger in aliases.data.get(str(message.author.id), []), \
        "**Alias `{}` has never been set. Check `{}`.**".format(trigger, list_aliases.cmd.name_prefix(message.guild))

    # Trigger is an assigned alias, remove it
    aliases.data[str(message.author.id)].pop(trigger)
    await aliases.asyncsave()
    await client.say(message, "**Alias `{}` removed.**".format(trigger, message.author))


@plugins.event()
async def on_message(message: discord.Message):
    success = False

    # User alias check
    if str(message.author.id) in aliases.data:
        user_aliases = aliases.data[str(message.author.id)]

        # Check any aliases
        for name, command in user_aliases.items():
            execute = False
            msg = message.content
            args = utils.split(msg)

            if not command.get("case_sensitive", False):
                msg = msg.lower()

            if command.get("anywhere", False):
                if name in msg:
                    execute = True
            else:
                if name == args[0]:
                    execute = True

            if execute:
                if command.get("delete_message", False):
                    if message.guild.me.permissions_in(message.channel).manage_messages:
                        client.loop.create_task(client.delete_message(message))

                text = command["text"]
                pre = config.guild_command_prefix(message.guild)

                # Execute the command if it is one
                if text.startswith(pre):
                    await plugins.execute(utils.split(text)[0][len(pre):], message)
                else:
                    await client.say(message, text)
                success = True

    return success
