from __future__ import annotations
from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.globals.node import Node


class PutCommand(Command):
    key = "put"
    desc = "Put an object somewhere."

    def setup_parser(self):
        self.parser.add_argument("object", type=str, help="object to put")
        self.parser.add_argument(
            "destination", type=str, nargs="*", help="destination to put the object in"
        )

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        obj_name = args.object
        dest_parts = [p for p in args.destination if p.lower() not in ["in", "into"]]
        if not dest_parts:
            caller.msg(self.print_help())
            return
        dest_name = " ".join(dest_parts)

        loc: Node | None = caller.location

        dest = caller.search(dest_name, looker=caller)
        if not dest and loc and loc.access(caller, "put"):
            dest = loc.search(dest_name, looker=caller)
        if not dest:
            caller.msg(f"'{dest_name}' not found.")
            return

        if not dest[0].is_container or not dest[0].access(caller, "put"):
            caller.msg(f"You can't put anything in {dest[0].name}!")
            return

        if obj_name == "all":
            for obj in list(caller.contents):
                if obj.id == dest[0].id:
                    caller.msg(f"You can't put {obj.name} in {dest[0].name} - it would create a containment loop.")
                    continue
                _cur = dest[0]
                _seen = set()
                _is_loop = False
                while _cur is not None and not getattr(_cur, "is_node", False):
                    if _cur is obj or getattr(_cur, "id", None) == obj.id:
                        _is_loop = True
                        break
                    if id(_cur) in _seen:
                        _is_loop = True
                        break
                    _seen.add(id(_cur))
                    _nxt = getattr(_cur, "location", None)
                    if _nxt is None or getattr(_nxt, "is_node", False):
                        break
                    _cur = _nxt
                if _is_loop:
                    caller.msg(f"You can't put {obj.name} in {dest[0].name} - it would create a containment loop.")
                    continue
                if not obj.at_pre_put(caller, dest[0]):
                    continue
                if not obj.move_to(dest[0]):
                    caller.msg(f"You can't put {obj.name} in {dest[0].name}.")
                    continue
                if loc:
                    loc.msg_contents(
                        f"{caller.name} put {obj.name} in {dest[0].name}.",
                        from_obj=caller,
                        exclude=caller,
                        msg_type="put",
                    )
                caller.msg(f"You put {obj.name} in {dest[0].name}.")
                obj.at_put(caller, dest[0])
            return

        found_obj = caller.search(obj_name)
        if not found_obj:
            caller.msg("Object not found.")
            return

        for obj in found_obj:
            if obj.id == dest[0].id:
                caller.msg(f"You can't put {obj.name} in {dest[0].name} - it would create a containment loop.")
                continue
            _cur = dest[0]
            _seen = set()
            _is_loop = False
            while _cur is not None and not getattr(_cur, "is_node", False):
                if _cur is obj or getattr(_cur, "id", None) == obj.id:
                    _is_loop = True
                    break
                if id(_cur) in _seen:
                    _is_loop = True
                    break
                _seen.add(id(_cur))
                _nxt = getattr(_cur, "location", None)
                if _nxt is None or getattr(_nxt, "is_node", False):
                    break
                _cur = _nxt
            if _is_loop:
                caller.msg(f"You can't put {obj.name} in {dest[0].name} - it would create a containment loop.")
                continue
            if not obj.at_pre_put(caller, dest[0]):
                caller.msg(f"You can't put {obj.name} in {dest[0].name}.")
                continue
            if not obj.move_to(dest[0]):
                caller.msg(f"You can't put {obj.name} in {dest[0].name}.")
                continue
            if loc:
                loc.msg_contents(
                    f"{caller.name} put {obj.name} in {dest[0].name}.",
                    from_obj=caller,
                    exclude=caller,
                    msg_type="put",
                )
            caller.msg(f"You put {obj.name} in {dest[0].name}.")
            obj.at_put(caller, dest[0])
