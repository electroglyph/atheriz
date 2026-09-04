from __future__ import annotations
import ast
import math
import contextlib
import ctypes
import io
import pprint as _pprint_mod
import sys
import threading
import time as _time_mod
import types

from atheriz import settings
from atheriz.commands.base_cmd import Command, CommandError
from atheriz.globals.objects import get
from atheriz.logger import logger
from atheriz.utils import wrap_xterm256
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object

_SANDBOX_LOCK = threading.Lock()

_DENIED_ATTRS = frozenset({
    "gi_frame", "gi_code", "gi_yieldfrom",
    "cr_frame", "cr_code", "cr_await",
    "ag_frame", "ag_code",
    "f_back", "f_builtins", "f_code", "f_globals", "f_locals", "f_trace",
    "f_trace_lines", "f_trace_opcodes",
    "func_closure", "func_code", "func_defaults", "func_dict", "func_doc",
    "func_globals", "func_name",
    "im_class", "im_func", "im_self",
    "tb_frame", "tb_next", "tb_lineno",
    "format", "format_map",
})
_FRAMED_TYPES = (types.FrameType, types.CodeType, types.TracebackType)

_MAX_POW_OPERAND = 10 ** 100
_MAX_REPEAT_INT = 10 ** 7
_MAX_REPEAT_STR = 4096
_MAX_POW_DIGITS = 50000


def _log_denial(obj, name: str, reason: str) -> None:
    """Audit log for hardening denials; these are tripwires for probing."""
    try:
        obj_type = type(obj).__name__
    except Exception:
        obj_type = "<unknown>"
    logger.warning(f"py sandbox denied {reason}: {name!r} on {obj_type}")


def _check_attr(obj, name) -> None:
    """Shared sandbox attribute policy.

    This is a denylist applied to an AST-transformed tree where every
    attribute load routes through _attr(); it is strong mitigation, not a
    proven security boundary.
    """
    if not isinstance(name, str):
        return
    if name.startswith("__") and name.endswith("__"):
        _log_denial(obj, name, "dunder access")
        raise AttributeError(f"sandbox: dunder access denied: {name!r}")
    if name in _DENIED_ATTRS:
        _log_denial(obj, name, "denylisted attribute")
        raise AttributeError(f"sandbox: access to {name!r} is blocked")
    if isinstance(obj, _FRAMED_TYPES + (types.ModuleType,)):
        raise AttributeError(
            "sandbox: attribute access on modules and interpreter frames is blocked"
        )


def safe_getattr(obj, name, *args):
    """getattr wrapper applying the sandbox attribute policy."""
    _check_attr(obj, name)
    return getattr(obj, name, *args)


def safe_hasattr(obj, name):
    """hasattr wrapper applying the sandbox attribute policy."""
    _check_attr(obj, name)
    return hasattr(obj, name)


def _attr(obj, name, *default):
    """Runtime guard target for every rewritten attribute load in the tree."""
    _check_attr(obj, name)
    return getattr(obj, name, *default)


def safe_chr(codepoint):
    """chr wrapper that blocks control characters."""
    if not isinstance(codepoint, int):
        raise TypeError(f"chr() requires an int, got {type(codepoint).__name__}")
    if codepoint < 0 or codepoint > 0x10FFFF:
        raise ValueError(f"chr() arg not in range(0x110000)")
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


class _SettingsProxy:
    """Read-only whitelist view of engine settings for sandboxed code."""

    _ALLOWED = frozenset({
        "CLIENT_DEFAULT_WIDTH",
        "CLIENT_DEFAULT_HEIGHT",
        "PY_OUTPUT_FG",
        "PY_MAX_OUTPUT_LINES",
        "PY_MAX_OUTPUT_BYTES",
        "PY_MAX_CODE_BYTES",
        "KILL_PY_COMMAND_AFTER",
        "AUTOSAVE_MINUTES",
    })

    def __getattr__(self, name):
        if name not in self._ALLOWED:
            raise AttributeError(f"sandbox: setting {name!r} is not exposed")
        return getattr(settings, name)

    def __setattr__(self, name, value):
        raise AttributeError("sandbox: settings are read-only")


class _TimeProxy:
    """Whitelist of safe time-module functions; sleep is excluded."""

    _ALLOWED = frozenset({"time", "monotonic", "gmtime", "localtime"})

    def __getattr__(self, name):
        if name not in self._ALLOWED:
            raise AttributeError(f"sandbox: time.{name} is not exposed")
        return getattr(_time_mod, name)


class _PprintProxy:
    """Whitelist of pprint functions."""

    _ALLOWED = frozenset({"pformat", "pprint"})

    def __getattr__(self, name):
        if name not in self._ALLOWED:
            raise AttributeError(f"sandbox: pprint.{name} is not exposed")
        return getattr(_pprint_mod, name)


class _SelfToCaller(ast.NodeTransformer):
    """Rewrite every free Name(id='self') in the user's code to Name(id='caller')."""

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id == "self" and isinstance(node.ctx, ast.Load):
            return ast.copy_location(ast.Name(id="caller", ctx=node.ctx), node)
        return node


class _SandboxHardener(ast.NodeTransformer):
    """Rewrites every attribute load into a guarded runtime call so no
    compiled attribute load remains in the tree; rejects attribute stores and
    dunder names; rejects constant-string subscripts naming dunders or
    denylisted attributes (closing subscript-key indirection)."""

    def __init__(self):
        self.denied: list[str] = []

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id.startswith("__") and node.id.endswith("__"):
            self.denied.append(node.id)
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        if node.attr.startswith("__") and node.attr.endswith("__"):
            self.denied.append(node.attr)
            return node
        if not isinstance(node.ctx, ast.Load):
            self.denied.append(f"<attribute store/del: {node.attr}>")
            return node
        call = ast.Call(
            func=ast.Name(id="_attr", ctx=ast.Load()),
            args=[node.value, ast.Constant(value=node.attr)],
            keywords=[],
        )
        return ast.copy_location(call, node.value)

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        self.generic_visit(node)
        sl = node.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            key = sl.value
            if (key.startswith("__") and key.endswith("__")) or key in _DENIED_ATTRS:
                self.denied.append(key)
        return node


def _harden_tree(tree: ast.Module) -> ast.Module:
    """Apply the hardening transformer or raise ValueError on denials."""
    hardener = _SandboxHardener()
    tree = hardener.visit(tree)
    ast.fix_missing_locations(tree)
    if hardener.denied:
        all_dunder = all(
            d.startswith("__") and d.endswith("__") for d in hardener.denied
        )
        reason = (
            "dunder access denied: " + ", ".join(sorted(set(hardener.denied)))
            if all_dunder
            else "blocked constructs: " + ", ".join(sorted(set(hardener.denied)))
        )
        logger.warning(f"py sandbox denied {reason}")
        raise ValueError(f"sandbox: {reason}")
    return tree


def _static_int_value(node: ast.AST, depth: int = 0):
    """Best-effort constant folding of pure integer arithmetic subtrees."""
    if depth > 8:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _static_int_value(node.operand, depth + 1)
        return None if inner is None else -inner
    if isinstance(node, ast.BinOp):
        left = _static_int_value(node.left, depth + 1)
        right = _static_int_value(node.right, depth + 1)
        if left is None or right is None:
            return None
        try:
            if abs(right) > 64 or abs(left) > _MAX_REPEAT_INT * 100:
                raise ValueError("sandbox: arithmetic literal too large")
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                if abs(left) > _MAX_REPEAT_INT // max(abs(right), 1) and right != 0:
                    raise ValueError("sandbox: arithmetic literal too large")
                return left * right
            if isinstance(node.op, ast.Pow):
                if left != 0 and right > 0:
                    try:
                        est = int(right * math.log10(abs(left))) + 1
                    except (ValueError, OverflowError):
                        raise ValueError("sandbox: pow size check failed")
                    if est > _MAX_POW_DIGITS:
                        raise ValueError("sandbox: estimated pow size exceeds safe limit")
                return left ** right
            if isinstance(node.op, ast.FloorDiv) and right:
                return left // right
            if isinstance(node.op, ast.Mod) and right:
                return left % right
        except (ValueError, ZeroDivisionError):
            raise
        except Exception:
            return None
    return None


def _check_static_bounds(tree: ast.Module) -> None:
    """Reject oversized trees, imports, and literal bombs before compilation."""
    nodes = list(ast.walk(tree))
    if len(nodes) > settings.PY_MAX_AST_NODES:
        raise ValueError(f"sandbox: program too large ({len(nodes)} AST nodes)")
    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("sandbox: imports are not permitted")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            if isinstance(node.left, ast.BinOp) and isinstance(node.left.op, ast.Pow):
                raise ValueError("sandbox: chained exponentiation is blocked")
            for operand in (node.left, node.right):
                if (
                    isinstance(operand, ast.Constant)
                    and isinstance(operand.value, int)
                    and abs(operand.value) > _MAX_POW_OPERAND
                ):
                    raise ValueError("sandbox: exponent literal too large")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            folded_left = _static_int_value(node.left)
            folded_right = _static_int_value(node.right)
            for operand, folded in ((node.left, folded_left), (node.right, folded_right)):
                if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                    if len(operand.value) > _MAX_REPEAT_STR:
                        raise ValueError("sandbox: string repeat operand too large")
                elif folded is not None and abs(folded) > _MAX_REPEAT_INT:
                    raise ValueError("sandbox: repeat operand too large")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            folded = _static_int_value(node.right)
            if folded is not None and abs(folded) > 64:
                raise ValueError("sandbox: exponent result too large")


class _PySandboxTimeout(BaseException):
    """Raised when the wall-clock deadline expires."""


class _PySandboxBudget(BaseException):
    """Raised when the line-event budget is exhausted."""


def _make_tracer(deadline, max_lines):
    """sys.settrace hook counting line events and enforcing the deadline;
    reliable for pure-Python loops where async-exc delivery can fail."""
    state = {"lines": 0}

    def tracer(frame, event, arg):
        if deadline is not None and _time_mod.monotonic() > deadline:
            raise _PySandboxTimeout
        state["lines"] += 1
        if state["lines"] > max_lines:
            raise _PySandboxBudget
        return tracer

    return tracer


def _raise_in_thread(ident, exc_type):
    """Forcibly raise exc_type in another thread via PyThreadState_SetAsyncExc."""
    # The C API takes an unsigned long thread ID. Use c_ulong because Windows
    # thread IDs may exceed signed 32-bit c_long range.
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(ident), ctypes.py_object(exc_type)
    )
    if res == 0:
        return  # thread already gone
    if res != 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_ulong(ident), ctypes.c_ulong(0)
        )


def _rewrite_self_to_caller(tree: ast.AST) -> ast.AST:
    return _SelfToCaller().visit(tree)


def _capture_last_expr(tree: ast.Module) -> ast.Module:
    """Rewrite the trailing expression statement into `_result[0] = <expr>` so
    its value is captured during the single exec instead of being re-evaluated
    (which would run its side effects twice). Must run after hardening so the
    captured expression is already transformed."""
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        expr = tree.body[-1].value
        target = ast.Subscript(
            value=ast.Name(id="_result", ctx=ast.Load()),
            slice=ast.Constant(value=0),
            ctx=ast.Store(),
        )
        assign = ast.Assign(targets=[target], value=expr)
        tree.body[-1] = ast.copy_location(assign, expr)
        ast.fix_missing_locations(tree)
    return tree


class _BoundedWriter(io.StringIO):
    """stdout capture that refuses growth beyond a byte cap."""

    def __init__(self, limit: int):
        super().__init__()
        self._limit = limit
        self.overflowed = False

    def write(self, s):
        if not isinstance(s, str):
            s = str(s)
        pos = self.tell()
        if pos >= self._limit:
            self.overflowed = True
            return len(s)
        remaining = self._limit - pos
        if len(s) > remaining:
            super().write(s[:remaining])
            self.overflowed = True
        else:
            super().write(s)
        return len(s)


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
        "Runs Python in a hardened sandbox: every attribute access passes a\n"
        "policy guard (no dunders, no interpreter internals, no str.format),\n"
        "modules are replaced by whitelisted proxies, and execution runs\n"
        "under CPU/output budgets with a per-server single-flight lock.\n"
        "Exposed globals: caller/me, here, search, get, settings (read-only\n"
        "subset), time (no sleep), pprint. The name 'self' remaps to 'caller'.\n"
        "Imports and attribute assignment are rejected."
    )
    use_parser = False

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        if settings.PY_REQUIRE_SUPERUSER:
            return caller.is_superuser
        return caller.is_builder

    # pyrefly: ignore
    def run(self, caller: Object, args: str):
        if not args or not args.strip():
            caller.msg("Usage: py <expression-or-statements>")
            return
        code = args.strip()

        if len(code.encode("utf-8")) > settings.PY_MAX_CODE_BYTES:
            caller.msg(
                _colorize(
                    f"Error: code too long ({len(code.encode('utf-8'))} bytes; "
                    f"max {settings.PY_MAX_CODE_BYTES})"
                )
            )
            return

        if not _SANDBOX_LOCK.acquire(blocking=False):
            caller.msg(_colorize("Error: a previous py execution is still running"))
            return
        release_lock = True
        try:
            caller.msg(_colorize(f">>> {code}"))
            logger.info(f"py by {caller.name} ({caller.id}): {code!r}")

            stdout_buf = _BoundedWriter(max(1, settings.PY_MAX_OUTPUT_BYTES * 2))
            result = [None]
            error = [None]
            timed_out = [False]

            py_globals = {
                "__builtins__": _SAFE_BUILTINS,
                "caller": caller,
                "me": caller,
                "here": caller.location,
                "search": caller.search,
                "get": get,
                "settings": _SettingsProxy(),
                "time": _TimeProxy(),
                "pprint": _PprintProxy(),
                "_result": result,
                "_attr": _attr,
            }

            def _exec_code():
                limit = settings.KILL_PY_COMMAND_AFTER
                deadline = (_time_mod.monotonic() + limit) if limit > 0 else None
                tracer = _make_tracer(deadline, settings.PY_MAX_LINE_EVENTS)
                try:
                    with contextlib.redirect_stdout(stdout_buf):
                        sys.settrace(tracer)
                        try:
                            tree = _rewrite_self_to_caller(ast.parse(code, mode="exec"))
                            _check_static_bounds(tree)
                            tree = _harden_tree(tree)
                            if len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr):
                                result[0] = eval(
                                    compile(ast.Expression(tree.body[0].value), "<py>", "eval"),
                                    py_globals,
                                )
                            else:
                                tree = _capture_last_expr(tree)
                                exec(compile(tree, "<py>", "exec"), py_globals)
                        finally:
                            sys.settrace(None)
                except SyntaxError as e:
                    error[0] = ("SyntaxError", str(e))
                except (_PySandboxTimeout, _PySandboxBudget):
                    timed_out[0] = True
                except Exception as e:
                    error[0] = (type(e).__name__, str(e))

            thread = threading.Thread(target=_exec_code, daemon=True)
            thread.start()
            limit = settings.KILL_PY_COMMAND_AFTER
            if limit <= 0:
                thread.join()
            else:
                thread.join(timeout=limit + 0.5)
                if thread.is_alive():
                    _raise_in_thread(thread.ident, _PySandboxTimeout)
                    thread.join(timeout=0.5)

            stuck = thread.is_alive()
            if stuck:
                release_lock = False
                logger.critical(
                    f"py sandbox thread from {caller.name} ({caller.id}) survived "
                    f"the kill watchdog; refusing further py runs until restart"
                )
            if timed_out[0] or stuck:
                caller.msg(_colorize("Error: Code execution timed out (killed)"))
                return

            if error[0]:
                err_type, err_msg = error[0]
                caller.msg(_colorize(f"Error: {err_type}: {err_msg}"))
                return

            out_parts: list[str] = []
            captured = _truncate(stdout_buf.getvalue())
            if captured:
                out_parts.append(captured)
            if stdout_buf.overflowed:
                out_parts.append("[output buffer cap reached]")
            if result[0] is not None:
                result_str = _truncate(repr(result[0]))
                out_parts.append(f"-- {type(result[0]).__name__} --\n{result_str}")
            if out_parts:
                caller.msg(_colorize("\n".join(out_parts)))
            elif not captured:
                caller.msg(_colorize("(no output)"))
        finally:
            if release_lock:
                _SANDBOX_LOCK.release()
