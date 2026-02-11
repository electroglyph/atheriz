# AtheriZ

A text-based multiplayer game server.

This is a very early draft and is not ready for production use.

This has some code from Evennia, and is loosely based on the same ideas.

Currently only supports web clients.

This is intended to be used with Python 3.14+ free-threaded.

It makes heavy use of multithreading. By default most attributes on game objects will be accessed in a thread-safe way automatically, just use them like normal.

This doesn't cover mutables likes lists and dicts tho.

If you have a game object foo, with dict attribute bar, you should use it like this:

```python
with foo.lock:
	foo.bar['key'] = cool_value

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
- more tests
- node hooks
- scripts
- funcparser cleanup
- tick system (already there, just need to activate it)
- time system (already done, just needs to be added)
- pathfinding (already done, just needs to be added)
- door stuff + ability for custom doors
- build command colors
- MCP