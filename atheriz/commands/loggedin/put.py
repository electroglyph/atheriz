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
        self.parser.add_argument("args", nargs="*", help="object to put, 'in <container>'")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        # Compatibility: support both new `args` list (multi-word) and legacy `object`/`destination` used by tests
        obj_name: str | None = None
        dest_name: str | None = None
        raw_args = getattr(args, "args", None)
        if isinstance(raw_args, (list, tuple)) and raw_args:
            tokens = list(raw_args)
            split_idx = None
            for i, tok in enumerate(tokens):
                if isinstance(tok, str) and tok.lower() in ("in", "into"):
                    split_idx = i
                    break
            if split_idx is None:
                caller.msg(self.print_help())
                return
            obj_parts = tokens[:split_idx]
            dest_parts = tokens[split_idx + 1 :]
            if not obj_parts or not dest_parts:
                caller.msg(self.print_help())
                return
            obj_name = " ".join(str(p) for p in obj_parts)
            dest_name = " ".join(str(p) for p in dest_parts)
        else:
            legacy_obj = getattr(args, "object", None)
            if isinstance(legacy_obj, str):
                obj_name = legacy_obj.strip()
                dest_raw = getattr(args, "destination", None)
                if isinstance(dest_raw, (list, tuple)):
                    # Filter stray 'in'/'into' if present (old tests pass already-filtered)
                    filtered = [str(p) for p in dest_raw if isinstance(p, str) and p.lower() not in ("in", "into")]
                    # Also handle case where destination list still contains keyword due to direct mock
                    dest_name = " ".join(filtered)
                elif isinstance(dest_raw, str):
                    dest_name = dest_raw.strip()
                else:
                    dest_name = ""
                if not obj_name or not dest_name:
                    caller.msg(self.print_help())
                    return
            else:
                # No recognizable args — show help
                # Fallback to token parsing if raw_args was empty list
                tokens = list(raw_args or [])
                split_idx = None
                for i, tok in enumerate(tokens):
                    if isinstance(tok, str) and tok.lower() in ("in", "into"):
                        split_idx = i
                        break
                if split_idx is None:
                    caller.msg(self.print_help())
                    return
                obj_parts = tokens[:split_idx]
                dest_parts = tokens[split_idx + 1 :]
                if not obj_parts or not dest_parts:
                    caller.msg(self.print_help())
                    return
                obj_name = " ".join(str(p) for p in obj_parts)
                dest_name = " ".join(str(p) for p in dest_parts)
        # At this point obj_name/dest_name are set

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
