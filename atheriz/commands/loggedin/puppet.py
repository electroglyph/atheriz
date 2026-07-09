from __future__ import annotations
from atheriz.commands.base_cmd import Command
from atheriz.globals.objects import get
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


def _find_target(caller: "Object", query: str):
    """Resolve a puppet target: ``#id`` (global) or name/alias in the caller's
    inventory or room — the same lookup ``examine`` uses, via ``Object.search``.

    Returns (target, error_str). On success, error_str is None.
    """
    if query.startswith("#"):
        try:
            obj_id = int(query[1:])
        except ValueError:
            return None, "Invalid ID format. Use #<number>."
        results = get(obj_id)
        if not results:
            return None, f"No object found with ID {obj_id}."
        return results[0], None
    matches = caller.search(query)
    if not matches and getattr(caller, "location", None):
        matches = caller.location.search(query)
    if not matches:
        return None, f"No match found for '{query}'."
    if len(matches) > 1:
        names = ", ".join(f"#{m.id} {m.name}" for m in matches)
        return None, f"Multiple matches: {names}. Use #id to pick one."
    return matches[0], None


def _puppetable(target: "Object") -> str | None:
    """Return an error string if target cannot be puppeted, else None.

    Accounts, channels and nodes are framework meta-objects, not game objects,
    and puppeting them would corrupt state.
    """
    if (
        getattr(target, "is_account", False)
        or getattr(target, "is_channel", False)
        or getattr(target, "is_node", False)
    ):
        return f"You cannot puppet {target.name}."
    return None


class PuppetCommand(Command):
    """Take control of a game object.

    Temporarily makes the target a player character and raises its privilege
    level to yours. Use ``unpuppet`` to release it and return to your previous
    object.

    Usage:
      puppet <target>
      puppet #<id>
    """

    key = "puppet"
    desc = "Take control of an object, temporarily making it a player character."
    category = "Building"

    # pyrefly: ignore
    def access(self, caller: "Object") -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("target", help="Object to puppet (name or #id).")

    # pyrefly: ignore
    def run(self, caller: "Object", args):
        session = caller.session
        if session is None:
            caller.msg("You have no active session.")
            return
        target, err = _find_target(caller, args.target)
        if err:
            caller.msg(err)
            return
        if target is caller:
            caller.msg("You are already puppeting yourself.")
            return
        if bad := _puppetable(target):
            caller.msg(bad)
            return
        if target.session is not None and target.session is not session:
            caller.msg(f"{target.name} is already being puppeted.")
            return

        # state off pickled objects; chain-safe (A->B->C unwinds B then A).
        session.puppet_stack.append((caller, target, target.is_pc, target.privilege_level))

        caller_priv = caller.privilege_level
        caller.at_disconnect()

        target.is_pc = True
        target.privilege_level = caller_priv

        session.puppet = target
        target.session = session
        target.at_puppet(caller=caller)
        target.at_post_puppet()


class UnpuppetCommand(Command):
    """Release the object you are puppeting and return to your previous one.

    Usage:
      unpuppet
    """

    key = "unpuppet"
    desc = "Release the puppeted object and return to your previous one."
    category = "Building"
    use_parser = False

    # pyrefly: ignore
    def access(self, caller: "Object") -> bool:
        return caller.is_builder

    # pyrefly: ignore
    def run(self, caller: "Object", args):
        session = caller.session
        if session is None:
            caller.msg("You have no active session.")
            return
        if not session.puppet_stack:
            caller.msg("You are not puppeting anything.")
            return

        prev, target, orig_is_pc, orig_priv = session.puppet_stack.pop()
        target.at_unpuppet(caller=prev)
        # restore BEFORE at_disconnect so any autosave persists the original state
        target.is_pc = orig_is_pc
        target.privilege_level = orig_priv
        target.at_disconnect()

        session.puppet = prev
        prev.session = session
        prev.at_post_puppet()
