import ast
import logging
from unittest.mock import MagicMock

import pytest

from atheriz import settings
from atheriz.commands.loggedin.py import (
    PyCommand,
    _SAFE_BUILTINS,
    _colorize,
    _rewrite_self_to_caller,
    _truncate,
    safe_chr,
    safe_getattr,
    safe_hasattr,
)
from atheriz.logger import logger
from atheriz.objects.base_obj import Object
from atheriz.utils import strip_ansi


# ---------------- helpers ----------------


def _msg_texts(caller) -> list[str]:
    """Return every text passed to caller.msg, ANSI-stripped."""
    out = []
    for call in caller.msg.call_args_list:
        args, kwargs = call
        if args:
            out.append(strip_ansi(str(args[0])))
        elif "text" in kwargs and kwargs["text"] is not None:
            out.append(strip_ansi(str(kwargs["text"])))
    return out


def _last_msg(caller) -> str:
    return _msg_texts(caller)[-1]


# ---------------- fixtures ----------------


@pytest.fixture
def caller():
    c = Object.create(None, "Admin")
    c.privilege_level = settings.Privilege.Admin
    c.msg = MagicMock()
    return c


@pytest.fixture
def caller_with_mock_lock(caller):
    """Caller whose lock is a MagicMock so we can verify acquire/release."""
    # plain MagicMock: supports the context manager protocol.
    # Do NOT spec=threading.RLock: the C-level RLock doesn't expose __exit__
    # to spec introspection, which breaks the engine's lock-aware attribute access.
    caller.lock = MagicMock()
    return caller


# ---------------- _SAFE_BUILTINS ----------------


class TestSafeBuiltins:
    FORBIDDEN = [
        "__import__", "open", "exec", "eval", "compile",
        "globals", "locals", "input", "breakpoint",
        "super", "memoryview",
        # Sandbox lockdown: removed to prevent MRO walking / dunder access
        "type", "vars", "object", "format", "issubclass",
        "setattr", "delattr",
    ]

    @pytest.mark.parametrize("name", FORBIDDEN)
    def test_forbidden_builtin_excluded(self, name):
        assert name not in _SAFE_BUILTINS, f"{name!r} must not be in the sandbox"

    @pytest.mark.parametrize("name", [
        "True", "False", "None", "abs", "all", "any", "bool",
        "dict", "float", "int", "isinstance",
        "len", "list", "max", "min", "print", "range", "repr",
        "set", "sorted", "str", "sum", "tuple", "zip",
        # Safe wrappers replace raw builtins
        "getattr", "hasattr", "chr",
    ])
    def test_expected_builtin_present(self, name):
        assert name in _SAFE_BUILTINS


# ---------------- _truncate ----------------


class TestTruncate:
    def test_empty(self):
        assert _truncate("") == ""

    def test_short_unchanged(self):
        assert _truncate("hello\nworld") == "hello\nworld"

    def test_truncates_by_line_count(self, monkeypatch):
        monkeypatch.setattr(settings, "PY_MAX_OUTPUT_LINES", 3)
        out = _truncate("\n".join(str(i) for i in range(10)))
        lines = out.split("\n")
        assert lines[-1].startswith("[truncated:")
        assert lines[0] == "0"
        assert lines[1] == "1"
        assert lines[2] == "2"

    def test_truncates_by_byte_count(self, monkeypatch):
        monkeypatch.setattr(settings, "PY_MAX_OUTPUT_BYTES", 10)
        out = _truncate("a" * 1000)
        assert "truncated" in out
        assert len(out.encode("utf-8")) < 1000


# ---------------- _colorize ----------------


class TestColorize:
    def test_empty(self):
        assert _colorize("") == ""

    def test_single_line_wrapped(self):
        out = _colorize("hello")
        assert out.startswith("\x1b[")
        assert out.endswith("\x1b[0m")
        assert "hello" in strip_ansi(out)

    def test_each_line_wrapped_independently(self):
        out = _colorize("a\nb\nc")
        assert strip_ansi(out) == "a\nb\nc"
        # one reset per line
        assert out.count("\x1b[0m") == 3

    def test_uses_configured_fg(self, monkeypatch):
        monkeypatch.setattr(settings, "PY_OUTPUT_FG", 15)
        out = _colorize("x")
        assert "38;5;15" in out


# ---------------- _rewrite_self_to_caller ----------------


class TestSelfRewrite:
    def test_attribute_access_rewritten(self):
        tree = ast.parse("self.name", mode="exec")
        out = ast.unparse(_rewrite_self_to_caller(tree))
        assert "caller.name" in out
        assert "self" not in out

    def test_attribute_chain_rewritten(self):
        tree = ast.parse("self.session.connection", mode="exec")
        out = ast.unparse(_rewrite_self_to_caller(tree))
        assert "caller.session.connection" in out

    def test_self_in_nested_scope_rewritten(self):
        tree = ast.parse("[self.name for _ in range(1)]", mode="exec")
        out = ast.unparse(_rewrite_self_to_caller(tree))
        assert "caller.name" in out
        assert "self" not in out

    def test_self_in_store_context_unchanged(self):
        # assigning to `self` would be a SyntaxError anyway in class scope,
        # but our rewriter must not turn `self = 5` into `caller = 5`.
        tree = ast.parse("self = 5", mode="exec")
        out = ast.unparse(_rewrite_self_to_caller(tree))
        assert "caller = 5" not in out

    def test_other_names_unchanged(self):
        tree = ast.parse("x = 1; y = x + 2", mode="exec")
        out = ast.unparse(_rewrite_self_to_caller(tree))
        assert "x = 1" in out
        assert "y = x + 2" in out
        assert "caller" not in out


# ---------------- PyCommand.end-to-end ----------------


class TestPyCommandAccess:
    def test_superuser_allowed(self, caller):
        assert PyCommand().access(caller) is True

    def test_player_denied(self, caller):
        caller.privilege_level = settings.Privilege.Player
        assert PyCommand().access(caller) is False

    def test_quelled_admin_denied(self, caller):
        caller.privilege_level = settings.Privilege.Admin
        caller.quelled = True
        assert PyCommand().access(caller) is False


class TestPyCommandUsage:
    def test_empty(self, caller):
        PyCommand().run(caller, "")
        assert "Usage" in _last_msg(caller)

    def test_whitespace(self, caller):
        PyCommand().run(caller, "   \t  ")
        assert "Usage" in _last_msg(caller)


class TestPyCommandExpression:
    def test_pure_expression_returns_result_block(self, caller):
        PyCommand().run(caller, "1 + 2")
        assert any("-- int --" in t and "3" in t for t in _msg_texts(caller))

    def test_print_captured_in_stdout(self, caller):
        PyCommand().run(caller, "print('hi')")
        assert any("hi" in t for t in _msg_texts(caller))

    def test_assignment_then_trailing_expression(self, caller):
        PyCommand().run(caller, "x = 5\nx * 2")
        assert any("-- int --" in t and "10" in t for t in _msg_texts(caller))

    def test_statement_only_shows_no_output(self, caller):
        PyCommand().run(caller, "x = 5")
        assert any("(no output)" in t for t in _msg_texts(caller))


class TestPyCommandSelfRewrite:
    def test_self_name_returns_caller_name(self, caller):
        PyCommand().run(caller, "self.name")
        assert any("Admin" in t and "-- str --" in t for t in _msg_texts(caller))

    def test_self_location_equals_here(self, caller):
        PyCommand().run(caller, "self.location is here")
        assert any("True" in t and "-- bool --" in t for t in _msg_texts(caller))


class TestPyCommandSandboxGlobals:
    def test_me_alias_is_caller(self, caller):
        PyCommand().run(caller, "me is caller")
        assert any("True" in t and "-- bool --" in t for t in _msg_texts(caller))

    def test_here_alias_is_location(self, caller):
        PyCommand().run(caller, "here is caller.location")
        assert any("True" in t and "-- bool --" in t for t in _msg_texts(caller))

    def test_settings_exposed(self, caller):
        PyCommand().run(caller, "settings.PY_OUTPUT_FG")
        assert any("15" in t for t in _msg_texts(caller))

    def test_time_exposed(self, caller):
        PyCommand().run(caller, "time.time()")
        assert any("-- float --" in t for t in _msg_texts(caller))

    def test_pprint_exposed(self, caller):
        PyCommand().run(caller, "pprint.pformat({'a': 1})")
        assert any("'a': 1" in t for t in _msg_texts(caller))

    def test_get_lookup_works(self, caller):
        PyCommand().run(caller, "get(caller.id)[0] is caller")
        assert any("True" in t and "-- bool --" in t for t in _msg_texts(caller))

    def test_search_is_callable(self, caller):
        PyCommand().run(caller, "search('nothing-matches-this')")
        # caller has no contents, search returns []
        assert any("[]" in t for t in _msg_texts(caller))


class TestPyCommandSandboxRestrictions:
    @pytest.mark.parametrize("snippet", [
        "__import__('os')",
        "open('/etc/passwd')",
        "exec('1+1')",
        "eval('1+1')",
        "compile('1+1', '<>', 'eval')",
        "globals()",
        "locals()",
        "input('> ')",
        "breakpoint()",
    ])
    def test_forbidden_builtin_raises_nameerror(self, caller, snippet):
        PyCommand().run(caller, snippet)
        text = _last_msg(caller)
        assert "Error:" in text, f"Expected an error for `{snippet}`, got: {text!r}"
        assert "NameError" in text, f"Expected NameError for `{snippet}`, got: {text!r}"

    @pytest.mark.parametrize("snippet", [
        "type(caller)",
        "vars(caller)",
        "object.__subclasses__()",
        "format(caller)",
        "issubclass(type(caller), object)",
        "setattr(caller, 'name', 'hacked')",
        "delattr(caller, 'name')",
    ])
    def test_removed_builtins_raises_nameerror(self, caller, snippet):
        PyCommand().run(caller, snippet)
        text = _last_msg(caller)
        assert "Error:" in text, f"Expected an error for `{snippet}`, got: {text!r}"
        assert "NameError" in text, f"Expected NameError for `{snippet}`, got: {text!r}"

    def test_syntax_error_reported(self, caller):
        PyCommand().run(caller, "1 +")
        assert "Error: SyntaxError" in _last_msg(caller)


class TestSafeGetattr:
    def test_allows_normal_attr(self):
        obj = type("Obj", (), {"name": "test"})()
        assert safe_getattr(obj, "name") == "test"

    def test_blocks_dunder_getitem(self):
        obj = type("Obj", (), {})()
        with pytest.raises(AttributeError, match="dunder"):
            safe_getattr(obj, "__class__")

    def test_blocks_dunder_subclasses(self):
        with pytest.raises(AttributeError, match="dunder"):
            safe_getattr(object, "__subclasses__")

    def test_blocks_dunder_dict(self):
        obj = type("Obj", (), {})()
        with pytest.raises(AttributeError, match="dunder"):
            safe_getattr(obj, "__dict__")

    def test_default_value_works(self):
        obj = type("Obj", (), {})()
        assert safe_getattr(obj, "missing", "default") == "default"


class TestSafeHasattr:
    def test_allows_normal_attr(self):
        obj = type("Obj", (), {"name": "test"})()
        assert safe_hasattr(obj, "name") is True

    def test_blocks_dunder(self):
        obj = type("Obj", (), {})()
        with pytest.raises(AttributeError, match="dunder"):
            safe_hasattr(obj, "__class__")


class TestSafeChr:
    def test_allows_printable_ascii(self):
        assert safe_chr(65) == "A"
        assert safe_chr(97) == "a"
        assert safe_chr(32) == " "

    def test_allows_tab_lf_cr(self):
        assert safe_chr(9) == "\t"
        assert safe_chr(10) == "\n"
        assert safe_chr(13) == "\r"

    def test_allows_unicode(self):
        assert safe_chr(0x00E9) == "\u00e9"  # e-acute
        assert safe_chr(0x4E16) == "\u4e16"  # CJK

    def test_blocks_null_byte(self):
        with pytest.raises(ValueError, match="null byte"):
            safe_chr(0)

    def test_blocks_c0_control_chars(self):
        with pytest.raises(ValueError, match="control character"):
            safe_chr(1)  # SOH
        with pytest.raises(ValueError, match="control character"):
            safe_chr(31)  # US

    def test_blocks_c1_control_chars(self):
        with pytest.raises(ValueError, match="C1 control"):
            safe_chr(0x80)
        with pytest.raises(ValueError, match="C1 control"):
            safe_chr(0x9F)

    def test_blocks_negative(self):
        with pytest.raises(ValueError, match="not in range"):
            safe_chr(-1)

    def test_blocks_too_large(self):
        with pytest.raises(ValueError, match="not in range"):
            safe_chr(0x110000)

    def test_blocks_non_int(self):
        with pytest.raises(TypeError, match="requires an int"):
            safe_chr("A")


class TestPyCommandSandboxMroWalk:
    def test_mro_walk_via_getattr_blocked(self, caller):
        PyCommand().run(caller, "getattr(caller, '__class__')")
        text = _last_msg(caller)
        assert "Error:" in text
        assert "AttributeError" in text

    def test_chr_string_build_blocked(self, caller):
        PyCommand().run(caller, "chr(0)")
        text = _last_msg(caller)
        assert "Error:" in text
        assert "ValueError" in text


class TestPyCommandTimeout:
    def test_infinite_loop_times_out(self, caller, monkeypatch):
        PyCommand().run(caller, "while True: pass")
        text = _last_msg(caller)
        assert "timed out" in text


class TestPyCommandTruncation:
    def test_stdout_truncated_by_line_count(self, caller, monkeypatch):
        monkeypatch.setattr(settings, "PY_MAX_OUTPUT_LINES", 5)
        PyCommand().run(caller, r"print('\n'.join(str(i) for i in range(50)))")
        assert "truncated" in _last_msg(caller)

    def test_stdout_truncated_by_byte_count(self, caller, monkeypatch):
        monkeypatch.setattr(settings, "PY_MAX_OUTPUT_BYTES", 100)
        PyCommand().run(caller, "print('a' * 1000)")
        assert "truncated" in _last_msg(caller)


class TestPyCommandColorize:
    def test_output_contains_ansi_codes(self, caller):
        PyCommand().run(caller, "1 + 1")
        found = False
        for call in caller.msg.call_args_list:
            args, kwargs = call
            text = args[0] if args else kwargs.get("text", "")
            if text and "\x1b[" in str(text):
                found = True
                break
        assert found, "Expected ANSI color codes in py output"

    def test_echo_contains_input(self, caller):
        PyCommand().run(caller, "1 + 1")
        assert any(">>> 1 + 1" in t for t in _msg_texts(caller))


class TestPyCommandLock:
    # Lock is no longer held during code execution (would deadlock with
    # thread-safe attribute access). Lock tests verify the caller is not
    # corrupted by the threaded execution.

    def test_no_lock_deadlock_on_success(self, caller_with_mock_lock):
        caller = caller_with_mock_lock
        PyCommand().run(caller, "1 + 1")
        # Verify caller.msg was called (no deadlock)
        assert caller.msg.call_count >= 1

    def test_no_lock_deadlock_on_exception(self, caller_with_mock_lock):
        caller = caller_with_mock_lock
        PyCommand().run(caller, "1/0")
        assert caller.msg.call_count >= 1

    def test_no_lock_deadlock_on_timeout(self, caller_with_mock_lock):
        caller = caller_with_mock_lock
        PyCommand().run(caller, "while True: pass")
        assert caller.msg.call_count >= 1


class TestPyCommandAuditLog:
    def test_info_record_emitted(self, caller, tmp_path):
        # caplog doesn't see records from the atheriz logger because it has
        # propagate=False; use a temporary file handler instead, matching
        # the pattern in test_logger.py.
        log_file = tmp_path / "py_audit.log"
        handler = logging.FileHandler(log_file)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            PyCommand().run(caller, "1 + 1")
            handler.flush()
            content = log_file.read_text()
            assert "py by" in content
            assert "Admin" in content
            assert "1 + 1" in content
        finally:
            logger.removeHandler(handler)
            handler.close()
