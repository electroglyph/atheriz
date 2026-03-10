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

Object creation doesn't require db access in AtheriZ (so it's really fast), and deletion is fast, too.

Because Evennia is single-threaded, you are limited in how much computation you can do on objects without slowing down the game.

AtheriZ is multi-threaded, with automatic thread-safety for immutable object attributes.

at_tick() is possible for thousands of objects per second without slowing down the game, while this pattern is not really possible in Evennia.

3d room coordinates are built in, coords = ("area", x, y, z)

The included client has built in support for optional ascii maps, and building rooms in-game can optionally auto-generate maps.

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
- ~~telnet~~
- follow and group system
- room nouns

https://github.com/user-attachments/assets/fbb712a6-5b65-469c-a20d-bb031e80a571

