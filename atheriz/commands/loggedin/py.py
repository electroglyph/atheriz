from __future__ import annotations
import ast
import contextlib
import io
import pprint
import threading
import time as _time_mod

from atheriz import settings
from atheriz.commands.base_cmd import Command, CommandError
from atheriz.globals.objects import get
from atheriz.logger import logger
from atheriz.utils import wrap_xterm256
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


def safe_getattr(obj, name, *args):
    """getattr wrapper that blocks dunder attribute access."""
    if isinstance(name, str) and name.startswith("__") and name.endswith("__"):
        raise AttributeError(f"Access to dunder attribute {name!r} is blocked")
    return getattr(obj, name, *args)


def safe_hasattr(obj, name):
    """hasattr wrapper that blocks dunder attribute access."""
    if isinstance(name, str) and name.startswith("__") and name.endswith("__"):
        raise AttributeError(f"Access to dunder attribute {name!r} is blocked")
    return hasattr(obj, name)


def safe_chr(codepoint):
    """chr wrapper that blocks control characters."""
    if not isinstance(codepoint, int):
        raise TypeError(f"chr() requires an int, got {type(codepoint).__name__}")
    if codepoint < 0 or codepoint > 0x10FFFF:
        raise ValueError(f"chr() arg not in range(0x110000)")
    # Block null bytes and C0/C1 control characters (except common whitespace)
    if codepoint == 0:
        raise ValueError("chr(0) (null byte) is blocked")
    if codepoint < 32 and codepoint not in (9, 10, 13):  # tab, LF, CR
        raise ValueError(f"chr({codepoint}) control character is blocked")
    if 0x80 <= codepoint <= 0x9F:
        raise ValueError(f"chr({codepoint}) C1 control character is blocked")
    return chr(codepoint)


_SAFE_BUILTINS = {
    "True": True,
    "False": False,
    "None": None,
    "abs": abs,
    "all": all,
    "any": any,
    "bin": bin,
    "bool": bool,
    "chr": safe_chr,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "frozenset": frozenset,
    "getattr": safe_getattr,
    "hasattr": safe_hasattr,
    "hash": hash,
    "hex": hex,
    "id": id,
    "int": int,
    "isinstance": isinstance,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


class _SelfToCaller(ast.NodeTransformer):
    """Rewrite every free Name(id='self') in the user's code to Name(id='caller')."""

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id == "self" and isinstance(node.ctx, ast.Load):
            return ast.copy_location(ast.Name(id="caller", ctx=node.ctx), node)
        return node


def _rewrite_self_to_caller(tree: ast.AST) -> ast.AST:
    return _SelfToCaller().visit(tree)


def _truncate(text: str) -> str:
    if not text:
        return ""
    lines = text.split("\n")
    out: list[str] = []
    total = 0
    truncated = 0
    for i, line in enumerate(lines):
        if i >= settings.PY_MAX_OUTPUT_LINES:
            truncated = len(lines) - i
            break
        cost = len(line.encode("utf-8")) + 1
        if total + cost > settings.PY_MAX_OUTPUT_BYTES:
            truncated = len(lines) - i
            break
        out.append(line)
        total += cost
    if truncated:
        out.append(f"[truncated: {truncated} more line(s)]")
    return "\n".join(out)


def _colorize(text: str) -> str:
    if not text:
        return ""
    fg = settings.PY_OUTPUT_FG
    return "\n".join(wrap_xterm256(line, fg=fg) for line in text.split("\n"))


class PyCommand(Command):
    key = "py"
    category = "Admin"
    desc = "Eval a Python expression in a restricted sandbox."
    extra_desc = (
        "Runs Python with a sandboxed builtins list. Exposed globals: caller/me,\n"
        "here, search, get, settings, logger, time, pprint. The name 'self' is\n"
        "remapped to 'caller'."
    )
    use_parser = False

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_superuser

    # pyrefly: ignore
    def run(self, caller: Object, args: str):
        if not args or not args.strip():
            caller.msg("Usage: py <expression-or-statements>")
            return
        code = args.strip()

        caller.msg(_colorize(f">>> {code}"))
        logger.info(f"py by {caller.name} ({caller.id}): {code!r}")

        py_globals = {
            "__builtins__": _SAFE_BUILTINS,
            "caller": caller,
            "me": caller,
            "here": caller.location,
            "search": caller.search,
            "get": get,
            "settings": settings,
            "logger": logger,
            "time": _time_mod,
            "pprint": pprint,
        }

        stdout_buf = io.StringIO()
        result = [None]
        error = [None]

        def _exec_code():
            try:
                with contextlib.redirect_stdout(stdout_buf):
                    tree = _rewrite_self_to_caller(ast.parse(code, mode="exec"))
                    if len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr):
                        result[0] = eval(
                            compile(ast.Expression(tree.body[0].value), "<py>", "eval"),
                            py_globals,
                        )
                    else:
                        exec(compile(tree, "<py>", "exec"), py_globals)
                        if tree.body and isinstance(tree.body[-1], ast.Expr):
                            result[0] = eval(
                                compile(ast.Expression(tree.body[-1].value), "<py>", "eval"),
                                py_globals,
                            )
            except SyntaxError as e:
                error[0] = ("SyntaxError", str(e))
            except Exception as e:
                error[0] = (type(e).__name__, str(e))

        thread = threading.Thread(target=_exec_code, daemon=True)
        thread.start()
        thread.join(timeout=5)
        if thread.is_alive():
            caller.msg(_colorize("Error: Code execution timed out (5s limit)"))
            return

        if error[0]:
            err_type, err_msg = error[0]
            caller.msg(_colorize(f"Error: {err_type}: {err_msg}"))
            return

        out_parts: list[str] = []
        captured = _truncate(stdout_buf.getvalue())
        if captured:
            out_parts.append(captured)
        if result[0] is not None:
            result_str = _truncate(repr(result[0]))
            out_parts.append(f"-- {type(result[0]).__name__} --\n{result_str}")
        if out_parts:
            caller.msg(_colorize("\n".join(out_parts)))
        elif not captured:
            caller.msg(_colorize("(no output)"))
