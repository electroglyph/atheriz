from __future__ import annotations
import ast
from atheriz.commands.base_cmd import Command
from atheriz.globals.objects import get
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node

PROTECTED_ATTRIBUTES = frozenset(
    {
        "id",
        "session",
        "lock",
        "locks",
        "access",
        "internal_cmdset",
        "external_cmdset",
        "scripts",
        "hooks",
        "channels",
        "followers",
        "following",
        "is_pc",
        "is_npc",
        "is_item",
        "is_container",
        "is_mapable",
        "is_account",
        "is_channel",
        "is_node",
        "is_script",
        "is_connected",
        "is_deleted",
        "is_modified",
        "is_temporary",
        "is_tickable",
        "_is_tickable",
        "password",
        "logged_in",
        "characters",
        "privilege_level",
        "quelled",
        "is_banned",
        "ban_reason",
        "location",
        "home",
        "_contents",
        "group_channel",
        "contents",
        "tags",
        "name",
    }
)


def _privilege_denied(caller, target) -> bool:
    if target is caller:
        return False
    try:
        t_priv = object.__getattribute__(target, "privilege_level")
    except AttributeError:
        return False
    try:
        c_priv = object.__getattribute__(caller, "privilege_level")
    except AttributeError:
        return False
    try:
        return t_priv >= c_priv
    except Exception:
        return False


def _is_protected(attr: str) -> bool:
    return attr.startswith("_") or attr in PROTECTED_ATTRIBUTES


class SetCommand(Command):
    key = "set"
    category = "Building"
    desc = "Set an attribute on an object."
    use_parser = True

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("target", help="Object to modify (name, #id, 'me', or 'here').")
        self.parser.add_argument("attribute", help="Attribute name to set.")
        self.parser.add_argument("value", help="Value to set (evaluated with ast.literal_eval).")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        target_str = args.target

        if target_str == "me":
            target = caller
        elif target_str == "here":
            target = caller.location
        elif target_str.startswith("#"):
            try:
                obj_id = int(target_str[1:])
                results = get(obj_id)
                if not results:
                    caller.msg(f"No object found with ID {obj_id}.")
                    return
                target = results[0]
            except ValueError:
                caller.msg("Invalid ID format. Use #<number>.")
                return
        else:
            matches = caller.search(target_str)
            if not matches:
                loc: Node = caller.location
                if loc and loc.access(caller, "view"):
                    matches = loc.search(target_str, looker=caller)

            if not matches:
                caller.msg(f"No match found for '{target_str}'.")
                return
            elif len(matches) > 1:
                caller.msg(f"Multiple matches for '{target_str}':")
                for m in matches:
                    caller.msg(f"  #{m.id} {m.name}")
                return
            else:
                target = matches[0]

        if target is not None and _privilege_denied(caller, target):
            caller.msg("You cannot modify an object of equal or higher privilege.")
            return

        attr = args.attribute
        raw_value = args.value

        try:
            value = ast.literal_eval(raw_value)
        except (ValueError, SyntaxError):
            # If literal_eval fails, treat it as a plain string
            value = raw_value

        if not hasattr(target, attr):
            caller.msg(f"Warning: '{attr}' is a new attribute on {target.name}.")

        if not caller.is_superuser and _is_protected(attr):
            caller.msg(f"'{attr}' is protected and cannot be set.")
            return

        if attr in ("location", "home", "_contents", "group_channel", "contents"):
            caller.msg(f"'{attr}' cannot be set directly; use move/teleport instead.")
            return

        try:
            setattr(target, attr, value)
        except AttributeError:
            caller.msg(f"'{attr}' is a read-only attribute and cannot be set.")
            return
        caller.msg(f"Set {target.name}.{attr} = {repr(value)}")


class UnsetCommand(Command):
    key = "unset"
    category = "Building"
    desc = "Delete an attribute from an object."
    use_parser = True

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("target", help="Object to modify (name, #id, 'me', or 'here').")
        self.parser.add_argument("attribute", help="Attribute name to delete.")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        target_str = args.target

        if target_str == "me":
            target = caller
        elif target_str == "here":
            target = caller.location
        elif target_str.startswith("#"):
            try:
                obj_id = int(target_str[1:])
                results = get(obj_id)
                if not results:
                    caller.msg(f"No object found with ID {obj_id}.")
                    return
                target = results[0]
            except ValueError:
                caller.msg("Invalid ID format. Use #<number>.")
                return
        else:
            matches = caller.search(target_str)
            if not matches:
                loc: Node = caller.location
                if loc and loc.access(caller, "view"):
                    matches = loc.search(target_str, looker=caller)

            if not matches:
                caller.msg(f"No match found for '{target_str}'.")
                return
            elif len(matches) > 1:
                caller.msg(f"Multiple matches for '{target_str}':")
                for m in matches:
                    caller.msg(f"  #{m.id} {m.name}")
                return
            else:
                target = matches[0]

        if target is not None and _privilege_denied(caller, target):
            caller.msg("You cannot modify an object of equal or higher privilege.")
            return

        attr = args.attribute

        if not caller.is_superuser and _is_protected(attr):
            caller.msg(f"'{attr}' is protected and cannot be removed.")
            return

        if attr in ("location", "home", "_contents", "group_channel", "contents"):
            caller.msg(f"'{attr}' cannot be removed directly.")
            return

        if not hasattr(target, attr):
            caller.msg(f"{target.name} has no attribute '{attr}'.")
            return

        try:
            delattr(target, attr)
        except AttributeError:
            caller.msg(f"'{attr}' is a read-only attribute and cannot be removed.")
            return
        caller.msg(f"Deleted {target.name}.{attr}")
