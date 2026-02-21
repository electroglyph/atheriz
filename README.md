# AtheriZ

Discord server here: https://discord.gg/hb62HEBzQT

A text-based multiplayer game server.

This is a very early draft and is not ready for production use.

This has some code from Evennia, and is loosely based on the same ideas.

# Why use this instead of Evennia?

I created this to solve some of the issues I had with Evennia.

This isn't meant as a knock against Evennia, btw, I love it a lot.

Object creation and deletion is slow in Evennia, which limits ability to create lots of things on the fly.

Object creation doesn't require db access in AtheriZ, and deletion is fast.

Because Evennia is single-threaded, you are limited in how much computation you can do on objects without slowing down the game.

3d room coordinates are built in, coords = ("area", x, y, z)

at_tick() is possible for thousands of objects per second without slowing down the game.

# More info

Currently only supports web clients.

This is intended to be used with Python 3.14+ free-threaded.

It makes heavy use of multithreading. By default most attributes on game objects will be accessed in a thread-safe way automatically, just use them like normal.

This doesn't cover mutables likes lists and dicts tho.

If you have a game object foo, with dict attribute bar, you should use it like this:

```python
with foo.lock:
  d = foo.bar
	d['key'] = cool_value
  foo.bar = d

# OR

with foo.lock:
  foo.bar['key'] = cool_value
  foo.is_modified = True

# BUT NOT

with foo.lock:
  foo.bar['key'] = cool_value
# Because like this the setattr hook won't detect the change, and the object might not get saved
# * if ALWAYS_SAVE_ALL = True in settings, then this is fine, because all objects are saved anyway
```

pip install this repo and run 'atheriz':

```AtheriZ - Text-based multiplayer game server

positional arguments:
  {start,restart,stop,reload,reset,create,new}
                        Available commands
    start               Start the AtheriZ server
    restart             Restart the AtheriZ server
    stop                Stop the AtheriZ server
    reload              Hot reload game logic
    reset               Delete all game data and start fresh
    create              Create a new account and character
    new                 Create a new game folder with template classes

options:
  -h, --help            show this help message and exit
```

for a new game:

`atheriz new folder_name`

in folder_name you'll see some basic template classes and a placeholder website. adding commands and such is similar to Evennia, the new game will have a 'test' command in it as an example.


TODO:

- docs
- more tests (getting there!)
- ~~node hooks~~
- ~~scripts~~
- ~~tick system~~
- ~~time system~~
- pathfinding (already done, just needs to be added)
- door stuff + ability for custom doors
- build colors for map tiles
- MCP