Blacklist
=========

.. toctree::

The blacklist plugin handles automatic deletion of messages with blacklisted words, phrases or regex patterns.
It's feature complete with custom responses, and configurations globally, per guild or per channel.

The blacklist configuration will be in ``config/blacklist.json`` after the plugin is loaded the first time.
To enable the blacklist feature, change ``"enabled": false`` to ``"enabled": true`` in the configuration file.

Configuration
~~~~~~~~~~~~~

In order to configure the blacklist, it is important to understand how the system works. When we want to tell
the plugin what to do, we need to write a set of data, or a dataset if you will. The dataset is a json formatted
dictionary of keys and values. All valid keys and their functions are documented in `Dataset`_.

Modifying the configuration by hand can however be tedious, and writing invalid json is likely. When the json
fails to decode, the blacklist plugin will crash intentionally, leaving an error message in the log. Check
the message at the bottom of the traceback for debugging. Additionally, invalid dataset keys are also logged
to the console as a warning, and are ignored by the compiler.

.. warning::

    The plugin compiles json for a specific channel at runtime *when* a message is sent to that channel. Invalid
    keywords will therefore **not** be logged when the plugin is loaded.

Categories
~~~~~~~~~~

Any written dataset can be assigned to the three following categories for further customization:

* *global*: the global configuration with only one dataset
* *guild*: a list of datasets specific to guilds
* *channel*: a list of datasets specific to channels

For instance, to blacklist the phrase ``raspberry`` in a guild with id ``314159265358979323``:

.. code-block:: json

    {
        "enabled": true,
        "global": {},
        "guild": [
            {
                "id": "314159265358979323",
                "match_patterns": [
                    "raspberry"
                ]
            }
        ],
        "channel": []
    }

.. note::

    The bot will automatically make it's definitive dataset for any given channel during runtime. The process starts
    with the global category, and moves down to the guild, and then the channel categories. Any given keywords in a
    channel config will override keywords in the global config.

.. note::

    Blacklist patterns in :data:`match_patterns` and :data:`regex_patterns` will be **appended** to the optional
    guild and global config. To change this behaviour, see the :data:`override` keyword.

Dataset
~~~~~~~

This section lists every keyword you need to create a complete dataset to be integrated in the hierarchy.
If you are unsure how to format json, I suggest reading a quick tutorial online.

Keep in mind that keywords all have a default value and can be omitted (with the exception of the id keyword).

---------------------------------

.. py:data:: id

`str` |-| channel or guild id.

**default**: ``null``

The id is **required** when creating a dataset for a guild or a channel. The id can be obtained in discord by
enabling developer mode in settings, and selecting **Copy** |_| **ID** in the right-click context menu of
the guild or channel.

.. code-block:: json

    {
        "id": "314159265358979323"
    }

.. py:data:: match_patterns

`list` |-| words or phrases as `str` to be blacklisted.

**default**: ``[]``

.. code-block:: json

    {
        "match_patterns": [
            "hello",
            "world",
            "don't ever say this sentence, please"
        ]
    }

.. py:data:: regex_patterns

`list` |-| special regex patterns as `str` to be blacklisted.

**default**: ``[]``

Read the `Python documentation`_ for supported syntax.

.. code-block:: json

    {
        "regex_patterns": [
            "kappa \\d+",
            "(ha){4,}",
            "https?://that-annoying-social-media-website\\.tv"
        ]
    }

.. note::

    Since json allows escaping characters using the ``\`` symbol, you need to use two backslashes, ``\\``, for these
    patterns.

.. py:data:: exclude

`list` |-| member ids as `str` to exclude from the blacklist.

**default**: ``[]``

.. code-block:: json

    {
        "exclude": [
            "271828182845904523"
        ]
    }

.. py:data:: response

`str` |-| an optional response when deleting a message.

**default**: ``null``

The response can include a limited number of substitutions. These are given in context with the message received,
which means they would all substitute properly regardless of the dataset's category.

Valid substitutions are:

* ``{pattern}`` |-| the blacklisted pattern
* ``{user}`` |-| display-name of the user
* ``{mention}`` |-| formatted mention of the user
* ``{guild}`` |-| the guild name
* ``{channel}`` |-| the channel mentioned

.. code-block:: json

    {
        "enable": true,
        "global": {
            "match_patterns": [
                "strawberry"
            ],
            "response": "{mention}, {guild} permits that word from being used."
        },
        "guild": [],
        "channel": [
            {
                "id": "314159265358979323",
                "match_patterns": [
                    "raspberry"
                ],
                "response": "We don't use that word around here, **{user}**."
            },
            {
                "id": "141421356237309504",
                "match_patterns": [
                    "blueberry"
                ],
                "response": null
            }
        ]
    }

.. note::

    As with any other keyword, you can disable responses in specific guilds or channels by overriding the response
    keyword with ``"response": null`` or ``"response": ""``. This is demonstrated in the example above.

.. py:data:: override

`bool` |-| when true, :data:`match_patterns` and :data:`regex_patterns` will be specific to their channel or guild.

**default**: ``false``

.. code-block:: json

    {
        "enabled": true,
        "global": {
            "match_patterns": [
                "strawberry"
            ]
        },
        "channel": [
            {
                "id": "314159265358979323",
                "match_patterns": [
                    "raspberry"
                ],
                "override": true
            }
        ]
    }

The configuration above would **only** blacklist the word ``raspberry`` in the given channel, whereas any other
channel blacklists the word ``strawberry``.

.. note::

    The override keyword has no effect in the global category, as the global category loads first during compilation.

.. py:data:: case_sensitive

`bool` |-| determines whether given :data:`match_patterns` and :data:`regex_patterns` should be case sensitive.

**default**: ``false``

Case sensitivity is applied to every word in both :data:`match_patterns` and :data:`regex_patterns`. However,
pattern specific case sensitivity can be controlled by using regex only for your patterns, and including
the syntax for regex' IGNORECASE, ``(?i)``:

.. code-block:: json

    {
        "case_sensitive": true,
        "regex_patterns": [
            "Raspberry Pi",
            "bad word(?i)",
            "[A-Z][a-z]+"
        ]
    }

The example above displays three cases:

* A case sensitive search that only matches when someone types ``Rasperry Pi`` by the letter
* A case insensitive search that would match both ``bad word``, ``BaD WorD`` and any other combination
* A pattern that matches any capitalized word

.. py:data:: bots

`bool` |-| determines if bot accounts should be included in the blacklist.

**default**: ``false``

.. py:data:: words

`bool` |-| when true, patterns in :data:`match_patterns` are searched word for word.

.. note::

    This is only valid for **words without spaces**. Any words with spaces will be treated as if this keyword was
    false.


.. urls and definitions

.. _Python documentation: https://docs.python.org/3/library/re.html

.. |_| unicode:: 0xA0
   :trim:

.. |-| unicode:: 0x2013