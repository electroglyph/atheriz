from __future__ import annotations
from atheriz.commands.base_cmd import Command
from atheriz.globals.objects import get
from typing import TYPE_CHECKING
from atheriz.objects.base_channel import Channel
import random
from contextlib import nullcontext

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node


class GroupCommand(Command):
    key = "group"
    desc = "Add a follower to your group."
    category = "Communication"
    extra_desc = "Use 'group add <name>' to add a follower to your group, 'group <message>' to talk to your group, 'group kick <name>' to remove a follower from your group, 'group leave' to leave your current group, or 'group list' to see your current group."

    # notes on group structure:
    # the membership list is stored in the channel object under listeners
    # the channel id is stored in the members' group_channel attribute (temporary, not saved)
    # the leader is the object that created the channel (created_by attribute)
    
    def setup_parser(self):
        import argparse
        self.parser.add_argument(
            "args", nargs=argparse.REMAINDER, help="Subcommand (add, kick, leave, list) or a message to group."
        )

    # pyrefly: ignore
    def run(self, caller: Object, args):
        args = args.args
        if not args:
            caller.msg(self.print_help())
            return
        if args[0].lower() == "list":
            _cl = getattr(caller, "lock", None)
            with (_cl if _cl is not None and hasattr(_cl, "__enter__") else nullcontext()):
                gc = caller.group_channel
            if not gc:
                caller.msg("You are not in a group.")
                return
            channel_list: list[Channel] = get(gc)

            if not channel_list:
                caller.msg("Error: Group channel not found.")
                return
            channel = channel_list[0]
            names = [x.get_display_name(caller) for x in channel.listeners.values()]
            caller.msg(f"Group members: {', '.join(names)}")
            return
        if args[0].lower() == "kick":
            if len(args) < 2:
                caller.msg("Usage: group kick <name>")
                return
            _cl = getattr(caller, "lock", None)
            with (_cl if _cl is not None and hasattr(_cl, "__enter__") else nullcontext()):
                if not caller.group_channel:
                    caller.msg("You are not in a group.")
                    return
                gc = caller.group_channel
            channel_list: list[Channel] = get(gc)
            if not channel_list:
                caller.msg("Error: Group channel not found.")
                return
            channel = channel_list[0]
            _cl = getattr(caller, "lock", None)
            with (_cl if _cl is not None and hasattr(_cl, "__enter__") else nullcontext()):
                _chl = getattr(channel, "lock", None)
                with (_chl if _chl is not None and hasattr(_chl, "__enter__") else nullcontext()):
                    if channel.created_by != caller.id:
                        caller.msg("You are not the leader of this group.")
                        return
            target = args[1]
            matches = caller.search(target)
            if not matches:
                loc = caller.location
                if loc and loc.access(caller, "view"):
                    matches = loc.search(target, looker=caller)
            if not matches:
                caller.msg(f"Could not find '{target}'.")
                return
            elif len(matches) > 1:
                caller.msg(f"Multiple matches found for '{target}'.")
                return
            target = matches[0]
            if target == caller:
                caller.msg("You can't kick yourself!")
                return
            _cl = getattr(caller, "lock", None)
            with (_cl if _cl is not None and hasattr(_cl, "__enter__") else nullcontext()):
                _chl = getattr(channel, "lock", None)
                with (_chl if _chl is not None and hasattr(_chl, "__enter__") else nullcontext()):
                    channel.msg(f"{caller.get_display_name()} kicked {target.get_display_name()} from the group.")
                    channel.remove_listener(target)
            _tl = getattr(target, "lock", None)
            with (_tl if _tl is not None and hasattr(_tl, "__enter__") else nullcontext()):
                target.group_channel = None
            return
        if args[0].lower() == "leave":
            _cl = getattr(caller, "lock", None)
            with (_cl if _cl is not None and hasattr(_cl, "__enter__") else nullcontext()):
                if not caller.group_channel:
                    caller.msg("You are not in a group.")
                    return
                gc = caller.group_channel
            channel_list = get(gc)
            if not channel_list:
                _cl = getattr(caller, "lock", None)
                with (_cl if _cl is not None and hasattr(_cl, "__enter__") else nullcontext()):
                    caller.group_channel = None
                caller.msg("Error: Group channel not found.")
                return
            channel = channel_list[0]
            should_delete = False
            _cl = getattr(caller, "lock", None)
            with (_cl if _cl is not None and hasattr(_cl, "__enter__") else nullcontext()):
                _chl = getattr(channel, "lock", None)
                with (_chl if _chl is not None and hasattr(_chl, "__enter__") else nullcontext()):
                    was_leader = channel.created_by == caller.id
                    channel.msg(f"{caller.get_display_name()} left the group.")
                    channel.remove_listener(caller)
                    remaining = list(channel.listeners.values())
                    if was_leader and remaining:
                        channel.created_by = remaining[0].id
                    should_delete = not remaining
                caller.group_channel = None
            if should_delete:
                channel.delete()
            return
        if args[0].lower() == "add":
            if len(args) < 2:
                caller.msg("Usage: group add <name>")
                return
            target = args[1]
            matches = caller.search(target)
            if not matches:
                loc = caller.location
                if loc and loc.access(caller, "view"):
                    matches = loc.search(target, looker=caller)
            if not matches:
                caller.msg(f"Could not find '{target}'.")
                return
            elif len(matches) > 1:
                caller.msg(f"Multiple matches found for '{target}'.")
                return
            target = matches[0]
            if target == caller:
                caller.msg("You can't add yourself!")
                return
            _cl = getattr(caller, "lock", None)
            with (_cl if _cl is not None and hasattr(_cl, "__enter__") else nullcontext()):
                if target.id not in caller.followers:
                    caller.msg(f"{target.get_display_name()} is not following you.")
                    return
                if not caller.group_channel:
                    try:
                        channel = Channel.create(f"{caller.name}'s group", caller)
                    except ValueError:
                        for _ in range(5):
                            try:
                                channel = Channel.create(f"{caller.name}'s group {random.randint(0, 99)}", caller)
                                break
                            except ValueError:
                                continue
                        else:
                            caller.msg("Could not create a group channel; try again.")
                            return
                    if caller.group_channel:
                        leaked = channel
                        existing = get(caller.group_channel)
                        if existing:
                            channel = existing[0]
                            try:
                                leaked.delete()
                            except Exception:
                                pass
                        else:
                            _chl = getattr(channel, "lock", None)
                            with (_chl if _chl is not None and hasattr(_chl, "__enter__") else nullcontext()):
                                channel.add_listener(caller)
                            caller.group_channel = channel.id
                    else:
                        _chl = getattr(channel, "lock", None)
                        with (_chl if _chl is not None and hasattr(_chl, "__enter__") else nullcontext()):
                            channel.add_listener(caller)
                        caller.group_channel = channel.id
                else:
                    channel_list = get(caller.group_channel)
                    if not channel_list:
                        caller.msg("Error: Group channel not found.")
                        return
                    else:
                        channel = channel_list[0]
                    _chl = getattr(channel, "lock", None)
                    with (_chl if _chl is not None and hasattr(_chl, "__enter__") else nullcontext()):
                        if channel.created_by != caller.id:
                            caller.msg("You are not the leader of this group.")
                            return
                _chl = getattr(channel, "lock", None)
                with (_chl if _chl is not None and hasattr(_chl, "__enter__") else nullcontext()):
                    channel.add_listener(target)
                    channel.msg(f"{caller.get_display_name()} added {target.get_display_name()} to the group.")
                _tl = getattr(target, "lock", None)
                with (_tl if _tl is not None and hasattr(_tl, "__enter__") else nullcontext()):
                    target.group_channel = channel.id
            return
        message = " ".join(args)
        _cl = getattr(caller, "lock", None)
        with (_cl if _cl is not None and hasattr(_cl, "__enter__") else nullcontext()):
            gc = caller.group_channel
        if not gc:
            caller.msg("You are not in a group.")
            return
        channel_list = get(gc)
        if not channel_list:
            caller.msg("Error: Group channel not found.")
            return
        channel = channel_list[0]
        channel.msg(message, caller)
        return
