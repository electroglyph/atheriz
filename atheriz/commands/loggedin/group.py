from atheriz.commands.base_cmd import Command
from atheriz.globals.objects import get
from typing import TYPE_CHECKING
from atheriz.objects.base_channel import Channel
import random

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
            if not caller.group_channel:
                caller.msg("You are not in a group.")
                return
            channel_list: list[Channel] = get(caller.group_channel)

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
            if not caller.group_channel:
                caller.msg("You are not in a group.")
                return
            channel_list: list[Channel] = get(caller.group_channel)
            if not channel_list:
                caller.msg("Error: Group channel not found.")
                return
            channel = channel_list[0]
            if channel.created_by != caller.id:
                caller.msg("You are not the leader of this group.")
                return
            target = args[1]
            matches = caller.search(target)
            if not matches:
                loc = caller.location
                if loc and loc.access(caller, "view"):
                    matches = loc.search(target)
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
            channel.msg(f"{caller.get_display_name()} kicked {target.get_display_name()} from the group.")
            channel.remove_listener(target)
            return
        if args[0].lower() == "leave":
            if not caller.group_channel:
                caller.msg("You are not in a group.")
                return
            channel_list = get(caller.group_channel)
            if not channel_list:
                caller.msg("Error: Group channel not found.")
                return
            channel = channel_list[0]
            channel.msg(f"{caller.get_display_name()} left the group.")
            channel.remove_listener(caller)
            caller.group_channel = None
            if len(channel.listeners) == 0:
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
                    matches = loc.search(target)
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
            with caller.lock:
                if target.id not in caller.followers:
                    caller.msg(f"{target.get_display_name()} is not following you.")
                    return
            if not caller.group_channel:
                try:
                    channel = Channel.create(f"{caller.name}'s group", caller)
                except ValueError:
                    channel = Channel.create(f"{caller.name}'s group {random.randint(0, 99)}", caller)
                channel.add_listener(caller)
                caller.group_channel = channel.id
            else:
                channel_list = get(caller.group_channel)
                if not channel_list:
                    caller.msg("Error: Group channel not found.")
                    return
                else:
                    channel = channel_list[0]
                if channel.created_by != caller.id:
                    caller.msg("You are not the leader of this group.")
                    return
            channel.add_listener(target)
            channel.msg(f"{caller.get_display_name()} added {target.get_display_name()} to the group.")
            target.group_channel = channel.id
            return
        message = " ".join(args)
        if not caller.group_channel:
            caller.msg("You are not in a group.")
            return
        channel_list = get(caller.group_channel)
        if not channel_list:
            caller.msg("Error: Group channel not found.")
            return
        channel = channel_list[0]
        channel.msg(message, caller)
        return

