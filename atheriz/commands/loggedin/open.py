from atheriz.commands.base_cmd import Command
from atheriz.singletons.get import get_node_handler
from atheriz.objects.base_door import Door
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class OpenCommand(Command):
    key = "open"
    category = "General"
    desc = "Open doors."
    use_parser = True

    def setup_parser(self):
        self.parser.add_argument("-n", "--north", action="store_true", help="North")
        self.parser.add_argument("-s", "--south", action="store_true", help="South")
        self.parser.add_argument("-e", "--east", action="store_true", help="East")
        self.parser.add_argument("-w", "--west", action="store_true", help="West")
        self.parser.add_argument("-u", "--up", action="store_true", help="Up")
        self.parser.add_argument("-d", "--down", action="store_true", help="Down")
        self.parser.add_argument("args", nargs="*", help="Other args")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        loc = caller.location
        if not loc:
            caller.msg("You have an invalid location.")
            return

        args_lower = [str(a).lower() for a in args.args]
        n_flag = args.north or "n" in args_lower or "north" in args_lower
        s_flag = args.south or "s" in args_lower or "south" in args_lower
        e_flag = args.east or "e" in args_lower or "east" in args_lower
        w_flag = args.west or "w" in args_lower or "west" in args_lower
        u_flag = args.up or "u" in args_lower or "up" in args_lower
        d_flag = args.down or "d" in args_lower or "down" in args_lower

        if not (n_flag or s_flag or e_flag or w_flag or u_flag or d_flag):
            caller.msg("Open what?")
            return

        nh = get_node_handler()
        def get_door_by_names(names: list[str]) -> Door | None:
            doors = nh.get_doors(loc.coord)
            if not doors:
                return None
            for n in names:
                d = doors.get(n)
                if d:
                    return d
            return None

        if n_flag:
            door = get_door_by_names(["north", "n"])
            if door:
                door.try_open(caller)
            else:
                caller.msg("There is no door to the north.")
        if s_flag:
            door = get_door_by_names(["south", "s"])
            if door:
                door.try_open(caller)
            else:
                caller.msg("There is no door to the south.")
        if e_flag:
            door = get_door_by_names(["east", "e"])
            if door:
                door.try_open(caller)
            else:
                caller.msg("There is no door to the east.")
        if w_flag:
            door = get_door_by_names(["west", "w"])
            if door:
                door.try_open(caller)
            else:
                caller.msg("There is no door to the west.")
        if u_flag:
            door = get_door_by_names(["up", "u"])
            if door:
                door.try_open(caller)
            else:
                caller.msg("There is no door up.")
        if d_flag:
            door = get_door_by_names(["down", "d"])
            if door:
                door.try_open(caller)
            else:
                caller.msg("There is no door down.")
                
                
class CloseCommand(Command):
    key = "close"
    category = "General"
    desc = "Close doors."
    use_parser = True

    def setup_parser(self):
        self.parser.add_argument("-n", "--north", action="store_true", help="North")
        self.parser.add_argument("-s", "--south", action="store_true", help="South")
        self.parser.add_argument("-e", "--east", action="store_true", help="East")
        self.parser.add_argument("-w", "--west", action="store_true", help="West")
        self.parser.add_argument("-u", "--up", action="store_true", help="Up")
        self.parser.add_argument("-d", "--down", action="store_true", help="Down")
        self.parser.add_argument("args", nargs="*", help="Other args")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        loc = caller.location
        if not loc:
            caller.msg("You have an invalid location.")
            return

        args_lower = [str(a).lower() for a in args.args]
        n_flag = args.north or "n" in args_lower or "north" in args_lower
        s_flag = args.south or "s" in args_lower or "south" in args_lower
        e_flag = args.east or "e" in args_lower or "east" in args_lower
        w_flag = args.west or "w" in args_lower or "west" in args_lower
        u_flag = args.up or "u" in args_lower or "up" in args_lower
        d_flag = args.down or "d" in args_lower or "down" in args_lower

        if not (n_flag or s_flag or e_flag or w_flag or u_flag or d_flag):
            caller.msg("Close what?")
            return

        nh = get_node_handler()
        def get_door_by_names(names: list[str]) -> Door | None:
            doors = nh.get_doors(loc.coord)
            if not doors:
                return None
            for n in names:
                d = doors.get(n)
                if d:
                    return d
            return None

        if n_flag:
            door = get_door_by_names(["north", "n"])
            if door:
                door.try_close(caller)
            else:
                caller.msg("There is no door to the north.")
        if s_flag:
            door = get_door_by_names(["south", "s"])
            if door:
                door.try_close(caller)
            else:
                caller.msg("There is no door to the south.")
        if e_flag:
            door = get_door_by_names(["east", "e"])
            if door:
                door.try_close(caller)
            else:
                caller.msg("There is no door to the east.")
        if w_flag:
            door = get_door_by_names(["west", "w"])
            if door:
                door.try_close(caller)
            else:
                caller.msg("There is no door to the west.")
        if u_flag:
            door = get_door_by_names(["up", "u"])
            if door:
                door.try_close(caller)
            else:
                caller.msg("There is no door up.")
        if d_flag:
            door = get_door_by_names(["down", "d"])
            if door:
                door.try_close(caller)
            else:
                caller.msg("There is no door down.")
                
class LockCommand(Command):
    key = "lock"
    category = "General"
    desc = "Lock doors."
    use_parser = True

    def setup_parser(self):
        self.parser.add_argument("-n", "--north", action="store_true", help="North")
        self.parser.add_argument("-s", "--south", action="store_true", help="South")
        self.parser.add_argument("-e", "--east", action="store_true", help="East")
        self.parser.add_argument("-w", "--west", action="store_true", help="West")
        self.parser.add_argument("-u", "--up", action="store_true", help="Up")
        self.parser.add_argument("-d", "--down", action="store_true", help="Down")
        self.parser.add_argument("args", nargs="*", help="Other args")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        loc = caller.location
        if not loc:
            caller.msg("You have an invalid location.")
            return

        args_lower = [str(a).lower() for a in args.args]
        n_flag = args.north or "n" in args_lower or "north" in args_lower
        s_flag = args.south or "s" in args_lower or "south" in args_lower
        e_flag = args.east or "e" in args_lower or "east" in args_lower
        w_flag = args.west or "w" in args_lower or "west" in args_lower
        u_flag = args.up or "u" in args_lower or "up" in args_lower
        d_flag = args.down or "d" in args_lower or "down" in args_lower

        if not (n_flag or s_flag or e_flag or w_flag or u_flag or d_flag):
            caller.msg("Close what?")
            return

        nh = get_node_handler()
        def get_door_by_names(names: list[str]) -> Door | None:
            doors = nh.get_doors(loc.coord)
            if not doors:
                return None
            for n in names:
                d = doors.get(n)
                if d:
                    return d
            return None

        if n_flag:
            door = get_door_by_names(["north", "n"])
            if door:
                door.try_lock(caller)
            else:
                caller.msg("There is no door to the north.")
        if s_flag:
            door = get_door_by_names(["south", "s"])
            if door:
                door.try_lock(caller)
            else:
                caller.msg("There is no door to the south.")
        if e_flag:
            door = get_door_by_names(["east", "e"])
            if door:
                door.try_lock(caller)
            else:
                caller.msg("There is no door to the east.")
        if w_flag:
            door = get_door_by_names(["west", "w"])
            if door:
                door.try_lock(caller)
            else:
                caller.msg("There is no door to the west.")
        if u_flag:
            door = get_door_by_names(["up", "u"])
            if door:
                door.try_lock(caller)
            else:
                caller.msg("There is no door up.")
        if d_flag:
            door = get_door_by_names(["down", "d"])
            if door:
                door.try_lock(caller)
            else:
                caller.msg("There is no door down.")
                
class UnlockCommand(Command):
    key = "unlock"
    category = "General"
    desc = "Unlock doors."
    use_parser = True

    def setup_parser(self):
        self.parser.add_argument("-n", "--north", action="store_true", help="North")
        self.parser.add_argument("-s", "--south", action="store_true", help="South")
        self.parser.add_argument("-e", "--east", action="store_true", help="East")
        self.parser.add_argument("-w", "--west", action="store_true", help="West")
        self.parser.add_argument("-u", "--up", action="store_true", help="Up")
        self.parser.add_argument("-d", "--down", action="store_true", help="Down")
        self.parser.add_argument("args", nargs="*", help="Other args")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        loc = caller.location
        if not loc:
            caller.msg("You have an invalid location.")
            return

        args_lower = [str(a).lower() for a in args.args]
        n_flag = args.north or "n" in args_lower or "north" in args_lower
        s_flag = args.south or "s" in args_lower or "south" in args_lower
        e_flag = args.east or "e" in args_lower or "east" in args_lower
        w_flag = args.west or "w" in args_lower or "west" in args_lower
        u_flag = args.up or "u" in args_lower or "up" in args_lower
        d_flag = args.down or "d" in args_lower or "down" in args_lower

        if not (n_flag or s_flag or e_flag or w_flag or u_flag or d_flag):
            caller.msg("Close what?")
            return

        nh = get_node_handler()
        def get_door_by_names(names: list[str]) -> Door | None:
            doors = nh.get_doors(loc.coord)
            if not doors:
                return None
            for n in names:
                d = doors.get(n)
                if d:
                    return d
            return None

        if n_flag:
            door = get_door_by_names(["north", "n"])
            if door:
                door.try_unlock(caller)
            else:
                caller.msg("There is no door to the north.")
        if s_flag:
            door = get_door_by_names(["south", "s"])
            if door:
                door.try_unlock(caller)
            else:
                caller.msg("There is no door to the south.")
        if e_flag:
            door = get_door_by_names(["east", "e"])
            if door:
                door.try_unlock(caller)
            else:
                caller.msg("There is no door to the east.")
        if w_flag:
            door = get_door_by_names(["west", "w"])
            if door:
                door.try_unlock(caller)
            else:
                caller.msg("There is no door to the west.")
        if u_flag:
            door = get_door_by_names(["up", "u"])
            if door:
                door.try_unlock(caller)
            else:
                caller.msg("There is no door up.")
        if d_flag:
            door = get_door_by_names(["down", "d"])
            if door:
                door.try_unlock(caller)
            else:
                caller.msg("There is no door down.")