<img src="./AtheriZ.png" alt="AtheriZ Logo" height="150" />

# AtheriZ

Discord server here: https://discord.gg/hb62HEBzQT

A text-based multiplayer game server.

This is an early draft and is not ready for production use, but it's getting close!

This has some code from Evennia, and is loosely based on the same ideas.

# Why use this instead of Evennia?

I created this to solve some of the issues I had with Evennia.

This isn't meant as a knock against Evennia, btw, I love it a lot.

Object creation and deletion is slow in Evennia, which limits ability to create lots of things on the fly.

Object creation doesn't require db access in AtheriZ, and deletion is fast.

Because Evennia is single-threaded, you are limited in how much computation you can do on objects without slowing down the game.

3d room coordinates are built in, coords = ("area", x, y, z)

at_tick() is possible for thousands of objects per second without slowing down the game.

# Documentation

First version of the docs are up, view them here: [docs](docs/table_of_contents.md)


# TODO:

- ~~docs~~
- example game
- more tests (getting there!)
- ~~node hooks~~
- ~~scripts~~
- ~~tick system~~
- ~~time system~~
- ~~pathfinding~~
- ~~door stuff + ability for custom doors~~
- map tile highlight in game client
- telnet
- follow and group system
- room nouns