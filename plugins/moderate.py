""" Plugin for guild moderation

The bot will perform different tasks when some settings are enabled in a guild:

_____________________________________NSFW Filter_____________________________________
    If enabled on the guild, spots any text containing the keyword nsfw and a link.
    Then tries to delete their message, and post a link to the dedicated nsfw channel.

Commands:
    moderate
    mute
    unmute
    timeout
    suspend
"""

from collections import defaultdict

import discord
import asyncio

from pcbot import Config, utils, Annotate
import plugins

client = plugins.client  # type: discord.Client

moderate = Config("moderate", data=defaultdict(dict))
default_config = {}  # Used by add_setting helper function


def setup_default_config(guild: discord.Guild):
    """ Setup default settings for a guild. """
    # Set to defaults if there is no config for the guild
    if str(guild.id) not in moderate.data:
        moderate.data[str(guild.id)] = default_config
        moderate.save()
        return

    # Set to defaults if guild's config is mis>asing values
    if not all(k in moderate.data[str(guild.id)].keys() for k in default_config):
        moderate.data[str(guild.id)] = default_config
        moderate.save()


@plugins.command(name="moderate", permissions="manage_messages")
async def moderate_(message, _: utils.placeholder):
    """ Change moderation settings. """
    pass


def add_setting(setting: str, default=True, name=None, permissions=None):
    """ Create a set of subcommands for the given setting (True or False).

    :param setting: display name for the setting.
    :param default: The default value for this setting.
    :param name: optionally set the name of the subcommand.
    :param permissions: what permissions are required to change this setting (list of str). """
    if not name:
        name = setting.lower().replace("\n", "").replace(" ", "")

    default_config[name] = default

    @moderate_.command(name=name, usage="[on | off]", permissions=permissions,
                       description="Display current {} setting or enable/disable it.".format(setting))
    async def display_setting(message: discord.Message):
        """ The command to display the current setting. """
        setup_default_config(message.guild)
        current = moderate.data[str(message.guild.id)][name]
        await client.say(message, "{} is **{}**.".format(setting, "enabled" if current else "disabled"))

    @display_setting.command(hidden=True, aliases="true set enable", permissions=permissions)
    async def on(message: discord.Message):
        """ The command to enable this setting. """
        moderate.data[str(message.guild.id)][name] = True
        await moderate.asyncsave()
        await client.say(message, "{} **enabled**.".format(setting))

    @display_setting.command(hidden=True, aliases="false unset disable", permissions=permissions)
    async def off(message: discord.Message):
        """ The command to enable this setting. """
        moderate.data[str(message.guild.id)][name] = False
        await moderate.asyncsave()
        await client.say(message, "{} **disabled**.".format(setting))


add_setting("NSFW filter", permissions=["manage_guild"])
add_setting("Changelog", permissions=["manage_guild"], default=False)


async def manage_mute(message: discord.Message, *members: discord.Member, mute=None):
    """ Add or remove Muted role for given members.

    :param mute: either member.add_roles or member.remove_roles
    :return: list of muted/unmuted members or None """
    # Manage Roles is required to add or remove the Muted role
    assert message.guild.me.permissions_in(message.channel).manage_roles, \
        "I need `Manage Roles` permission to use this command."

    muted_role = discord.utils.get(message.guild.roles, name="Muted")

    # The guild needs to properly manage the Muted role
    assert muted_role, "No role assigned for muting. Please create a `Muted` role."

    muted_members = []

    # Try giving members the Muted role
    for member in members:
        if member is message.guild.me:
            await client.say(message, "I refuse to mute myself!")
            continue

        while True:
            try:
                if mute:
                    await member.add_roles(muted_role)
                if not mute:
                    await member.remove_roles(muted_role)
            except discord.errors.Forbidden:
                await client.say(message, "I do not have permission to give members the `Muted` role.")
                return None
            except discord.errors.HTTPException:
                continue
            else:
                muted_members.append(member)
                break

    return muted_members or None


@plugins.command(pos_check=True, permissions="manage_messages")
async def mute(message: discord.Message, *members: discord.Member):
    """ Mute the specified members. """
    muted_members = await manage_mute(message, *members, mute=True)

    # Some members were muted, success!
    if muted_members:
        await client.say(message, "Muted {}".format(utils.format_objects(*muted_members, dec="`")))


@plugins.command(pos_check=True, permissions="manage_messages")
async def unmute(message: discord.Message, *members: discord.Member):
    """ Unmute the specified members. """
    muted_members = await manage_mute(message, *members, mute=False)

    # Some members were unmuted, success!
    if muted_members:
        await client.say(message, "Unmuted {}".format(utils.format_objects(*muted_members, dec="`")))


@plugins.command(permissions="manage_messages")
async def timeout(message: discord.Message, member: discord.Member, minutes: float, reason: Annotate.Content):
    """ Timeout a user in minutes (will accept decimal numbers), send them
    the reason for being timed out and post the reason in the guild's
    changelog if it has one. """
    client.loop.create_task(client.delete_message(message))
    muted_members = await manage_mute(message, member, mute=True)

    # Do not progress if the members were not successfully muted
    # At this point, manage_mute will have reported any errors
    if not muted_members:
        return

    changelog_channel = get_changelog_channel(message.guild)

    # Tell the member and post in the changelog
    m = "You were timed out from **{}** for **{} minutes**. \n**Reason:** {}".format(message.guild, minutes, reason)
    await client.send_message(member, m)

    if changelog_channel:
        await client.send_message(changelog_channel, "{} Timed out {} for **{} minutes**. **Reason:** {}".format(
            message.author.mention, member.mention, minutes, reason
        ))

    # Sleep for the given hours and unmute the member
    await asyncio.sleep(minutes * 60)  # Since asyncio.sleep takes seconds, multiply by 60^2
    await manage_mute(message, *muted_members, mute=False)


@plugins.command(aliases="muteall mute* unmuteall unmute*", permissions="manage_messages")
async def suspend(message: discord.Message, channel: discord.TextChannel = Annotate.Self):
    """ Suspends a channel by removing send permission for the guild's default role.
    This function acts like a toggle. """
    send = channel.overwrites_for(message.guild.default_role).send_messages
    print(send, False if send is None else not send)
    overwrite = discord.PermissionOverwrite(send_messages=False if send is None else not send)
    await channel.set_permissions(message.guild.default_role, overwrite=overwrite)

    try:
        if overwrite.send_messages:
            await client.say(message, "{} is no longer suspended.".format(channel.mention))
        else:
            await client.say(message, "Suspended {}.".format(channel.mention))
    except discord.Forbidden:  # ...
        await client.send_message(message.author, "You just removed my send permission in {}.".format(channel.mention))


@plugins.argument("{open}member/#channel {suffix}{close}", pass_message=True)
def members_and_channels(message: discord.Message, arg: str):
    """ Look for both members and channel mentions. """
    if utils.channel_mention_pattern.match(arg):
        return utils.find_channel(message.guild, arg)

    return utils.find_member(message.guild, arg)


@plugins.command(permissions="manage_messages")
async def purge(message: discord.Message, *instances: members_and_channels, num: utils.int_range(1, 100)):
    """ Purge the given amount of messages from the specified members or all.
    You may also specify a channel to delete from.

    `num` is a number from 1 to 100. """
    instances = list(instances)

    channel = message.channel
    for instance in instances:
        if type(instance) is discord.TextChannel:
            channel = instance
            instances.remove(instance)
            break

    assert not any(i for i in instances if type(i) is discord.TextChannel), "**I can only purge in one channel.**"
    to_delete = []

    async for m in channel.history(limit=100, before=message):
        if len(to_delete) >= num:
            break

        if not instances or m.author in instances:
            to_delete.append(m)

    deleted = len(to_delete)
    if deleted > 1:
        await client.delete_messages(message.channel, to_delete)
    elif deleted == 1:
        await client.delete_message(to_delete[0])

    m = await client.say(message, "Purged **{}** message{}.".format(deleted, "" if deleted == 1 else "s"))

    # Remove both the command message and the feedback after 5 seconds
    await asyncio.sleep(5)
    await client.delete_messages(message.channel, [m, message])


async def check_nsfw(message: discord.Message):
    """ Check if the message is NSFW (very rough check). """
    # Check if this guild has nsfwfilter enabled
    if not moderate.data[str(message.guild.id)]["nsfwfilter"]:
        return False

    # Do not check if the channel is designed for nsfw content
    if "nsfw" in message.channel.name or message.channel.is_nsfw():
        return False

    # Check if message includes keyword nsfw and a link
    msg = message.content.lower()
    if "nsfw" in msg and ("http://" in msg or "https://" in msg):
        if message.guild.me.permissions_in(message.channel).manage_messages:
            await client.delete_message(message)

        nsfw_channel = discord.utils.find(lambda c: "nsfw" in c.name, message.guild.channels)

        if nsfw_channel:
            await client.say(message, "{0.mention}: **Please post NSFW content in {1.mention}**".format(
                message.author, nsfw_channel))

        return True


@plugins.event()
async def on_message(message: discord.Message):
    """ Check plugin settings. """
    # Do not check in private messages
    if isinstance(message.channel, discord.abc.PrivateChannel):
        return False

    setup_default_config(message.guild)

    nsfw_success = await check_nsfw(message)
    if nsfw_success is True:
        return True


def get_changelog_channel(guild: discord.Guild):
    """ Return the changelog channel for a guild. """
    setup_default_config(guild)
    if not moderate.data[str(guild.id)]["changelog"]:
        return

    channel = discord.utils.get(guild.channels, name="changelog")
    if not channel:
        return

    permissions = channel.permissions_for(guild.me)
    if not permissions.send_messages or not permissions.read_messages:
        return

    return channel


async def log_change(channel: discord.TextChannel, message: str):
    embed = discord.Embed(description=message)
    await client.send_message(channel, embed=embed)


@plugins.event()
async def on_message_delete(message: discord.Message):
    """ Update the changelog with deleted messages. """
    changelog_channel = get_changelog_channel(message.guild)

    # Don't log any message the bot deleted
    for m in client.last_deleted_messages:
        if m.id == message.id:
            return

    if not changelog_channel:
        return

    if message.channel == changelog_channel:
        return

    if message.author == client.user:
        return
    if not message.attachments == []:
        attachments = ""
        for i in range(len(message.attachments)):
            attachments += message.attachments[i].filename + "\n"
        await log_change(
            changelog_channel,
            "{0.author.mention}'s message was deleted in {0.channel.mention}:\n{0.clean_content}\nAttachments:\n``{"
            "1}``".format(message, attachments)
        )
    else:
        await log_change(
            changelog_channel,
            "{0.author.mention}'s message was deleted in {0.channel.mention}:\n{0.clean_content}".format(message)
        )


@plugins.event()
async def on_guild_channel_create(channel: discord.TextChannel):
    """ Update the changelog with created channels. """
    if isinstance(channel, discord.abc.PrivateChannel):
        return

    changelog_channel = get_changelog_channel(channel.guild)
    if not changelog_channel:
        return

    # Differ between voice channels and text channels
    if channel.type == discord.ChannelType.text:
        await log_change(changelog_channel, "Channel {0.mention} was created.".format(channel))
    else:
        await log_change(changelog_channel, "Voice channel **{0.name}** was created.".format(channel))


@plugins.event()
async def on_guild_channel_delete(channel: discord.TextChannel):
    """ Update the changelog with deleted channels. """
    if isinstance(channel, discord.abc.PrivateChannel):
        return

    changelog_channel = get_changelog_channel(channel.guild)
    if not changelog_channel:
        return

    # Differ between voice channels and text channels
    if channel.type == discord.ChannelType.text:
        await log_change(changelog_channel, "Channel **#{0.name}** was deleted.".format(channel))
    else:
        await log_change(changelog_channel, "Voice channel **{0.name}** was deleted.".format(channel))


@plugins.event()
async def on_guild_channel_update(before: discord.TextChannel, after: discord.TextChannel):
    """ Update the changelog when a channel changes name. """
    if isinstance(after, discord.abc.PrivateChannel):
        return

    changelog_channel = get_changelog_channel(after.guild)
    if not changelog_channel:
        return

    # We only want to update when a name change is performed
    if before.name == after.name:
        return

    # Differ between voice channels and text channels
    if after.type == discord.ChannelType.text:
        await log_change(
            changelog_channel, "Channel **#{0.name}** changed name to {1.mention}, **{1.name}**.".format(before, after))
    else:
        await log_change(
            changelog_channel, "Voice channel **{0.name}** changed name to **{1.name}**.".format(before, after))


@plugins.event()
async def on_member_join(member: discord.Member):
    """ Update the changelog with members joined. """
    changelog_channel = get_changelog_channel(member.guild)
    if not changelog_channel:
        return

    await log_change(changelog_channel, "{0.mention} joined the guild.".format(member))


@plugins.event()
async def on_member_remove(member: discord.Member):
    """ Update the changelog with deleted channels. """
    changelog_channel = get_changelog_channel(member.guild)
    if not changelog_channel:
        return

    await log_change(changelog_channel, "{0.mention} ({0.name}) left the guild.".format(member))


@plugins.event()
async def on_member_update(before: discord.Member, after: discord.Member):
    """ Update the changelog with any changed names and roles. """
    name_change = not before.name == after.name
    nick_change = not before.nick == after.nick
    role_change = not before.roles == after.roles

    changelog_channel = get_changelog_channel(after.guild)
    if not changelog_channel:
        return

    # Format the nickname or username changed
    if name_change:
        m = "{0.mention} (previously **{0.name}**) changed their username to **{1.name}**."
    elif nick_change:
        if not before.nick:
            m = "{0.mention} (previously **{0.name}**) got the nickname **{1.nick}**."
        elif not after.nick:
            m = "{0.mention} (previously **{0.nick}**) no longer has a nickname."
        else:
            m = "{0.mention} (previously **{0.nick}**) got the nickname **{1.nick}**."
    elif role_change:
        muted_role = discord.utils.get(after.guild.roles, name="Muted")

        if len(before.roles) > len(after.roles):
            role = [r for r in before.roles if r not in after.roles][0]
            if role == muted_role:
                return

            m = "{0.mention} lost the role **{1.name}**".format(after, role)
        else:
            role = [r for r in after.roles if r not in before.roles][0]
            if role == muted_role:
                return

            m = "{0.mention} received the role **{1.name}**".format(after, role)
    else:
        return

    if name_change or nick_change:
        await log_change(changelog_channel, m.format(before, after))
    else:
        await log_change(changelog_channel, m)


@plugins.event()
async def on_member_ban(guild: discord.Guild, member: discord.Member):
    """ Update the changelog with banned members. """
    changelog_channel = get_changelog_channel(guild)
    if not changelog_channel:
        return

    await log_change(changelog_channel,
                     "{0.mention} ({0.name}) was banned from the guild.".format(member))


@plugins.event()
async def on_member_unban(guild: discord.Guild, user: discord.Member):
    """ Update the changelog with unbanned members. """
    changelog_channel = get_changelog_channel(guild)
    if not changelog_channel:
        return

    await log_change(changelog_channel, "{0.mention} was unbanned from the guild.".format(user))
