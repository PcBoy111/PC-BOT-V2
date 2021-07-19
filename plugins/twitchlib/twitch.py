""" API wrapper for twitch.tv. """

import re

import discord

from pcbot import utils, Config

twitch_config = Config("twitch-api", data=dict(ids={}, client_id=None))

# Define twitch API info
client_id = twitch_config.data["client_id"] or ""
api_url = "https://api.twitch.tv/kraken/"

url_pattern = re.compile(r"^https://www.twitch.tv/(?P<name>.+)$")


class RequestFailed(Exception):
    """ For when the api request fails. """
    pass


class UserNotResolved(Exception):
    """ For when a name isn't resolved. """
    pass


async def request(endpoint: str = None, **params):
    """ Perform a request using the twitch kraken v5 API.

    If the url key is not given, the request is sent to the root URL.

    :param endpoint: The endpoint to request from, e.g users would be /kraken/users.
    :param params: Any parameters to pass to the URL.
    :raises RequestFailed: Generic error when the request is refused.
    """
    headers = {"Client-ID": client_id, "Accept": "application/vnd.twitchtv.v5+json"}
    response = await utils.download_json(api_url + (endpoint or ""), headers=headers, **params)

    # Raise an Exception when the request was invalid
    if "error" in response:
        raise RequestFailed(response["message"])

    return response


async def get_id(member: discord.Member, name: str = None):
    """ Return a member's twitch user ID.

    If the name kwarg is omitted, the member should be connected to discord and
    already be streaming, so that member.activity.url can be used. When omitted and
    the member isn't streaming, a ValueError is raised.

    :param member: The member to return the ID for.
    :param name: Optionally specified twitch username of the member.
    :raises RequestFailed: Generic error when the request is refused.
    :raises UserNotResolved: Can't resolve member's twitch user.
    """
    # Return the cached id if this member has been checked before
    if str(member.id) in twitch_config.data["ids"]:
        return twitch_config.data["ids"][str(member.id)]

    # Try getting the name from the activity url if name is not specified
    if not name:
        # Raise NameResolveError if the name is unknown
        if not member.activity or not member.activity.url:
            raise UserNotResolved("Could not resolve twitch name of {}: they are not streaming.".format(member))

        # Attempt finding the twitch name using the Member.activity object url
        match = url_pattern.match(member.activity.url)
        if match is None:
            raise UserNotResolved("Could not resolve twitch name of {}: their url is broken.".format(member))
        name = match.group("name")

    # Make a request for the user found
    response = await request("users", login=name)
    if response["_total"] == 0:
        raise UserNotResolved(
            "Could not resolve twitch user account of {}: twitch user {} does not exist.".format(member, name))

    # Save and return the id
    twitch_id = response["users"][0]["_id"]
    twitch_config.data["ids"][str(member.id)] = twitch_id
    await twitch_config.asyncsave()
    return twitch_id
