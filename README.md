# PCBOT

[![Documentation Status](https://readthedocs.org/projects/pcbot/badge/?version=latest)](http://pcbot.readthedocs.io/en/latest/?badge=latest)

WIP discord bot using [discord.py](https://github.com/Rapptz/discord.py).

**PCBOT is only supported by python version 3.6.0 and newer.**

## BotéMon
**For those who have arrived from BotéMon and wish to contribute/have 
a look/access the resources**, the libraries used are found in 
[`plugins/pokedex.py`](plugins/pokedex.py) and [`plugins/pokedexlib/`](plugins/pokedexlib)!

Currently, BotéMon is the only version of PCBOT I host for public use. 
**If you wish to add the bot to your server, check 
[its bots.discord.pw entry!](https://bots.discord.pw/bots/203868728884985857)**

## Installing
Before installing the bot, you must make sure you're running python 
3.6.0+

```
$ python -V
Python 3.6.0
```

The next step is installing [discord.py](https://github.com/Rapptz/discord.py) with voice support:

```
python -m pip install "discord.py[voice]"
```

To install the bot, one can clone the repo:

```
git clone --recursive https://github.com/pckv/pcbot.git
```

This is the best way to install as the bot is actively in development. 
If you want to update the bot using git, run `git pull` and either 
restart the bot or reload the updated plugins.

If you do not care about updates, you can 
[download the repo as ZIP](https://github.com/pckv/pcbot/archive/master.zip).

Several plugins require additional modules. These modules are not 
required unless you want a specific plugin to work. Some features and 
modules are only supported if you're using Linux. The bot will prompt 
errors when modules are missing, although modules as of now are:

| Module    | Notes                                                     |
| --------- | --------------------------------------------------------- |
| Pillow    | `pip install Pillow`                                      |
| pendulum  | `pip install pendulum==1.0.2`, might also need `pytz`     |
| cairosvg  | `pip install cairosvg`, only supported for Linux          |
| aiofiles  | `pip install aiofiles`, support async file operations in [`config.py`](pcbot/config.py)          |
| oppai-ng  | `pip install oppai`, used for pp calculation in [`pp.py`](plugins/osulib/pp.py) |
| ffmpeg    | Not a python module; see doc in [`music.py`](plugins/music.py)      |
| imageio   | `pip install imageio`, support gif in [`image.py`](plugins/image.py)|

## Running
Running the bot is simple. Go to the root directory 
and run bot.py:

```
python bot.py
```

You should get a prompt asking for your bot token. One can also use the
--token / -t argument, in for instance a bash script:

```sh
#!bin/sh
python bot.py -t TOKEN
```

For more command-line arguments, execute `python bot.py -h`.

## Configuration
### Changing the command prefix
The command prefix is **bot specific**, which means that servers can't
set a custom command prefix. To change the bot prefix, head over to 
[`config/bot-meta.json`](config/bot_meta.json). The prefix can be any number of characters.

### The info command
PCBOT has a dedicated info command, by default `!pcbot`, which 
displays info such as the name, owner, uptime, servers and the bot 
application description. To change the name of the command to suit 
your bot name, change the "name" key in [`config/bot-meta.json`](config/bot_meta.json). This 
name should avoid any non-alphanumeric characters, although you are
free to include spaces in the name. 

The info command will be named after this name, as lowercase and 
without any spaces.

### Assigning ownership
After running the bot for the first time, you want to make sure you're 
assigned the owner account. This process is very straight-forward and 
requires that you have access to the bot log, and can respond to the 
bot within 60 seconds of reading the log (By default, the log is 
printed to the terminal).

**The first step** is to send the command `!setowner` in a private 
message. The bot will wait for a response matching the 3-digit code 
logged to the console. The logged message looks something like this:

```
CRITICAL [bot] 2016-04-24 23:03:49,138: Owner code for assignment: 263
```

After sending the code in a private message, in this case `263`, 
your account will be registered as the bot owner.

### Plugins
PCBOT has a folder based plugin system. If you wish to make a plugin, 
check out [`pcbot/builtin.py`](pcbot/builtin.py). There are more features than showcased 
in the builtin plugin, however there is no documentation for them yet.

**To remove an unwanted plugin from the bot**, simply remove it from 
the [`plugins/`](plugins) folder. You are also free to remove any accompanying 
library folder. Keep in mind **they will be re-added** when updating 
the bot using git.

The owner can manage plugins with the `!plugin` command. See
`!help plugin` for more information.

## Licence
The MIT License (MIT)

Copyright (c) 2016 PC

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
