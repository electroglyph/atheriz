from atheriz.commands.base_cmd import Command
from atheriz.globals.objects import get
from atheriz.globals.get import get_node_handler
from atheriz.objects.base_obj import Object
from threading import RLock
import ast
import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node


def _resolve_obj_name(id: int) -> str | None:
    results = get(id)
    if results:
        return results[0].name
    return None


def _lambda_source(fn) -> str:
    """Return a clean, single-line source string for a lambda/function.

    Uses inspect + ast to pull the callable's source and strip the surrounding
    assignment, leaving `lambda x: ...` or `def name(...): ...`.
    Falls back to a short generic label if source isn't available.
    """
    try:
        src = inspect.getsource(fn).strip()
    except (OSError, TypeError):
        qualname = getattr(fn, "__qualname__", None) or "<callable>"
        return f"<{qualname}>"
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    for node in ast.walk(tree):
        if isinstance(node, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)):
            return ast.unparse(node)
    return src


def _format_value(val, hint_name: str | None = None):
    """Render an attribute value for examine output.

    Returns either a ``str`` (single-line) or a ``list[str]`` where the first
    element is the inline header value and the remaining elements are
    continuation lines indented beneath it. The main loop handles both shapes.
    """

    def expand_id(id: int) -> str:
        results = get(id)
        if results:
            obj = results[0]
            return f"#{id} ({obj.name})"
        return f"#{id}"

    def fmt(v) -> str:
        if isinstance(v, list):
            return "[" + ", ".join(fmt(x) for x in v) + "]"
        if isinstance(v, tuple):
            # NamedTuples (like Coord) carry their own __str__ via __repr__;
            # fall through to str() so we don't flatten them to (a, b, c).
            if hasattr(v, "_fields"):
                try:
                    return str(v)
                except Exception:
                    pass
            return "(" + ", ".join(fmt(x) for x in v) + ")"
        if isinstance(v, (set, frozenset)):
            return "{" + ", ".join(fmt(x) for x in v) + "}"
        if isinstance(v, dict):
            return "{" + ", ".join(f"{fmt(k)}: {fmt(item)}" for k, item in v.items()) + "}"
        if type(v).__name__ == "RLock":
            return "<RLock>"
        try:
            return str(v)
        except Exception:
            return "<unprintable>"

    # --- hint-specific branches ---------------------------------------------

    if hint_name == "internal_cmdset":
        return "<hidden>"

    if hint_name == "external_cmdset":
        if val is None:
            return "None"
        seen: set[int] = set()
        keys: list[str] = []
        for cmd in val.get_all():
            if id(cmd) in seen:
                continue
            seen.add(id(cmd))
            keys.append(cmd.key)
        return "[" + ", ".join(keys) + "]" if keys else "[]"

    if hint_name == "followers":
        if not val:
            return "set()"
        return "{" + ", ".join(expand_id(x) for x in val) + "}"

    if hint_name in ("created_by", "last_touched_by"):
        if val == -1:
            return "-1"
        name = _resolve_obj_name(val)
        return f"{val} ({name})" if name else str(val)

    if hint_name == "scripts":
        if not val:
            return "set()"
        if isinstance(val, (set, list, tuple, frozenset)) and all(isinstance(x, int) for x in val):
            return "{" + ", ".join(expand_id(x) for x in val) + "}"
        return fmt(val)

    if hint_name == "locks":
        lines: list[str] = [""]
        if val:
            for lock_name, callables in val.items():
                bodies = [_lambda_source(fn) for fn in callables]
                lines.append(f"{lock_name}: [{', '.join(bodies)}]")
        return lines

    if hint_name == "session":
        if val is None:
            return "None"
        parts: list[str] = []
        account = getattr(val, "account", None)
        if account is not None:
            parts.append(f"account={account.name} (#{account.id})")
        conn = getattr(val, "connection", None)
        if conn is not None:
            host = getattr(conn, "client_host", None) or getattr(conn, "session_id", None) or "?"
            parts.append(f"conn={host}")
        puppet = getattr(val, "puppet", None)
        if puppet is not None:
            parts.append(f"puppet={puppet.name} (#{puppet.id})")
        w = getattr(val, "term_width", None)
        h = getattr(val, "term_height", None)
        if w and h:
            parts.append(f"w={w}, h={h}")
        if getattr(val, "screenreader", False):
            parts.append("sr=True")
        return "Session(" + ", ".join(parts) + ")" if parts else "Session()"

    if hint_name == "_contents":
        if isinstance(val, (set, list, tuple, frozenset)) and val and all(isinstance(x, int) for x in val):
            return "{" + ", ".join(expand_id(x) for x in val) + "}"
        return fmt(val)

    # --- generic fallback ---------------------------------------------------

    return fmt(val)


class ExamineCommand(Command):
    """
    Examine an object and display all its attributes.

    Usage:
      examine <target>
      examine #<id>
    """

    key = "examine"
    aliases = ["exam", "ex"]
    desc = "Examine an object to see its attributes."
    category = "Building"

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("target", nargs="?", help="Object to examine (name or #id).")

    # pyrefly: ignore
    def run(self, caller: Object, args):
        if not args:
            caller.msg(self.print_help())
            return
        target_str = args.target

        if not target_str:
            target = caller.location
            if not target:
                caller.msg("You are nowhere to examine.")
                return
        elif target_str == "me":
            target = caller
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
            if target_str:
                matches = caller.search(target_str)
                if not matches:
                    loc: Node = caller.location
                    if loc and loc.access(caller, "view"):
                        matches = loc.search(target_str)

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

        if getattr(target, "is_node", False):
            nh = get_node_handler()
            area = nh.get_area(target.coord.area) if target.coord else None
            area_name = area.name if area else target.coord.area
            caller.msg(
                f"Examining Node at {target.coord} in area '{area_name}', z={target.coord.z} (#{target.id}):"
            )
        else:
            caller.msg(f"Examining {target.name} (#{target.id}):")

        ignore = ["access", "lock"]

        attrs = vars(target)
        sorted_keys = sorted(attrs.keys())

        for key in sorted_keys:
            if key in ignore:
                continue
            val = attrs[key]
            val_output = _format_value(val, hint_name=key)
            type_name = type(val).__name__

            if isinstance(val_output, list):
                caller.msg(f"  {key}: {val_output[0]} ({type_name})")
                for line in val_output[1:]:
                    caller.msg(f"    {line}")
            else:
                caller.msg(f"  {key}: {val_output} ({type_name})")
