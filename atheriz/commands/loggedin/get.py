from __future__ import annotations
from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.globals.node import Node


class GetCommand(Command):
    key = "get"
    desc = "Get an object."

    def setup_parser(self):
        self.parser.add_argument("args", nargs="*", help="object to get, optionally 'from <container>'")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        loc: Node | None = caller.location
        if not loc:
            caller.msg("No.")
            return

        obj_name: str | None = None
        source_name: str | None = None
        raw_args = getattr(args, "args", None)
        if isinstance(raw_args, (list, tuple)) and raw_args:
            tokens = list(raw_args)
            from_idx = None
            for i, tok in enumerate(tokens):
                if isinstance(tok, str) and tok.lower() == "from":
                    from_idx = i
                    break
            if from_idx is not None:
                obj_parts = tokens[:from_idx]
                source_parts = tokens[from_idx + 1 :]
            else:
                obj_parts = tokens
                source_parts = []
            if not obj_parts:
                caller.msg(self.print_help())
                return
            obj_name = " ".join(str(p) for p in obj_parts)
            source_name = " ".join(str(p) for p in source_parts) if source_parts else None
        else:
            legacy_obj = getattr(args, "object", None)
            if isinstance(legacy_obj, str):
                obj_name = legacy_obj.strip()
                source_raw = getattr(args, "source", None)
                if isinstance(source_raw, (list, tuple)):
                    # Legacy source may be [] or ["from","bag"] or ["bag"]
                    filtered = [str(p) for p in source_raw if isinstance(p, str)]
                    # Strip leading 'from' if present
                    if filtered and filtered[0].lower() == "from":
                        filtered = filtered[1:]
                    source_name = " ".join(filtered) if filtered else None
                elif isinstance(source_raw, str):
                    s = source_raw.strip()
                    if s.lower().startswith("from "):
                        s = s[5:].strip()
                    source_name = s if s else None
                else:
                    source_name = None
                if not obj_name:
                    caller.msg(self.print_help())
                    return
            else:
                # Fallback empty
                tokens = list(raw_args or [])
                from_idx = None
                for i, tok in enumerate(tokens):
                    if isinstance(tok, str) and tok.lower() == "from":
                        from_idx = i
                        break
                if from_idx is not None:
                    obj_parts = tokens[:from_idx]
                    source_parts = tokens[from_idx + 1 :]
                else:
                    obj_parts = tokens
                    source_parts = []
                if not obj_parts:
                    caller.msg(self.print_help())
                    return
                obj_name = " ".join(str(p) for p in obj_parts)
                source_name = " ".join(str(p) for p in source_parts) if source_parts else None

        if obj_name == "all":
            # Get all from a container or from the room
            if source_name:
                container = caller.search(source_name, looker=caller)
                if not container:
                    container = loc.search(source_name, looker=caller)
                if not container:
                    caller.msg(f"'{source_name}' not found.")
                    return
                source = container[0]
                if not source.access(caller, "get"):
                    caller.msg("You can't take anything from there.")
                    return
            else:
                if not loc.access(caller, "get"):
                    caller.msg("You can't get something from here!")
                    return
                source = loc

            for obj in list(source.contents):
                # Parity with the named path (view-filtered search): a hidden
                # item must not be swept up by `get all`.
                if (
                    not obj.at_pre_get(caller)
                    or obj.id == caller.id
                    or not obj.access(caller, "view")
                ):
                    continue
                if not obj.move_to(caller):
                    caller.msg(f"You can't get {obj.get_display_name(caller)}.")
                    continue
                loc.msg_contents(
                    "$You(giver) $conj(take) $obj(item).",
                    mapping={"giver": caller, "item": obj},
                    from_obj=caller,
                    exclude=caller,
                    msg_type="get",
                )
                caller.msg(f"You picked up: {obj.get_display_name(caller)}")
                obj.at_get(caller)
            return

        # Get specific object from a container or from the room
        if source_name:
            container = caller.search(source_name, looker=caller)
            if not container:
                container = loc.search(source_name, looker=caller)
            if not container:
                caller.msg(f"'{source_name}' not found.")
                return
            source = container[0]
            if not source.access(caller, "get"):
                caller.msg("You can't take anything from there.")
                return
            found = source.search(obj_name, looker=caller)
            if not found:
                caller.msg(f"'{obj_name}' not found in {source.name}.")
                return
        else:
            if not loc.access(caller, "get"):
                caller.msg("You can't get something from here!")
                return
            found = loc.search(obj_name, looker=caller)
            if not found:
                caller.msg("Object not found.")
                return

        for f in found:
            if not f.at_pre_get(caller):
                caller.msg(f"You can't get {f.get_display_name(caller)}.")
                continue
            if not f.move_to(caller):
                caller.msg(f"You can't get {f.get_display_name(caller)}.")
                continue
            loc.msg_contents(
                "$You(giver) $conj(take) $obj(item).",
                mapping={"giver": caller, "item": f},
                from_obj=caller,
                exclude=caller,
                msg_type="get",
            )
            caller.msg(f"You picked up: {f.get_display_name(caller)}")
            f.at_get(caller)
