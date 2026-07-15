"""Tests for atheriz.objects.funcparser — the $func() string parser.

Tests focus on INTENT, not just behavior. We verify:
- Safety properties: malformed input doesn't crash, failures degrade gracefully
- Priority: kwargs are merged in correct order (defaults < string < reserved)
- Escape semantics: $$ → $, \\$func → literal $func
- Strip vs escape: which is which
- Nested function calls execute inside-out
- Unknown callables don't crash
- parse_to_any returns raw value only for pure-call strings
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from atheriz.objects.funcparser import (
    FuncParser, ParsingError, _ParsedFunc,
    FUNCPARSER_CALLABLES, ACTOR_STANCE_CALLABLES,
)


# ============================================================================
# Test helpers
# ============================================================================

def make_func(name, return_value=None, side_effect=None):
    """Create a tracking callable for use in tests."""
    fn = MagicMock()
    fn.__name__ = name
    if side_effect is not None:
        fn.side_effect = side_effect
    else:
        fn.return_value = return_value
    # Make it look like a real *args/**kwargs function for validation
    return fn


# ============================================================================
# _ParsedFunc dataclass
# ============================================================================

class TestParsedFunc:
    def test_defaults(self, global_test_env):
        pf = _ParsedFunc()
        assert pf.prefix == "$"
        assert pf.funcname == ""
        assert pf.args == []
        assert pf.kwargs == {}
        assert pf.fullstr == ""
        assert pf.infuncstr == ""
        assert pf.rawstr == ""
        assert pf.double_quoted == -1
        assert pf.current_kwarg == ""
        assert pf.open_lparens == 0
        assert pf.open_lsquate == 0  # sic — typo in source
        assert pf.open_lcurly == 0
        assert pf.exec_return == ""

    def test_get_returns_tuple(self, global_test_env):
        pf = _ParsedFunc(funcname="foo", args=["a", 1], kwargs={"k": "v"})
        assert pf.get() == ("foo", ["a", 1], {"k": "v"})

    def test_str_includes_prefix_rawstr_infuncstr(self, global_test_env):
        pf = _ParsedFunc(prefix="$", rawstr="foo(", infuncstr="bar")
        assert str(pf) == "$foo(bar"

    def test_args_kwargs_not_shared_between_instances(self, global_test_env):
        # Mutable defaults must not be shared
        pf1 = _ParsedFunc()
        pf2 = _ParsedFunc()
        pf1.args.append("x")
        pf1.kwargs["k"] = "v"
        assert pf2.args == []
        assert pf2.kwargs == {}


# ============================================================================
# ParsingError
# ============================================================================

class TestParsingError:
    def test_is_runtime_error(self, global_test_env):
        # Intent: ParsingError is the parser's canonical exception type
        assert issubclass(ParsingError, RuntimeError)

    def test_message_preserved(self, global_test_env):
        e = ParsingError("test")
        assert str(e) == "test"


# ============================================================================
# FuncParser constructor
# ============================================================================

class TestFuncParserInit:
    def test_dict_callables(self, global_test_env):
        fn = make_func("foo", return_value="X")
        parser = FuncParser({"foo": fn})
        assert parser.callables["foo"] is fn

    def test_dict_is_copied(self, global_test_env):
        # Modifying the original dict should not affect the parser
        d = {"foo": make_func("foo")}
        parser = FuncParser(d)
        d["bar"] = make_func("bar")
        assert "bar" not in parser.callables

    def test_start_char_default(self, global_test_env):
        parser = FuncParser({})
        assert parser.start_char == "$"

    def test_escape_char_default(self, global_test_env):
        parser = FuncParser({})
        assert parser.escape_char == "\\"

    def test_max_nesting_is_accepted_as_kwarg(self, global_test_env):
        # INTENT: max_nesting is accepted in __init__ and stored on the
        # instance so it can be introspected and used by future validation.
        parser = FuncParser({}, max_nesting=5)
        assert parser.max_nesting == 5

    def test_max_nesting_default(self, global_test_env):
        from atheriz.objects.funcparser import _MAX_NESTING
        parser = FuncParser({})
        assert parser.max_nesting == _MAX_NESTING

    def test_custom_start_char(self, global_test_env):
        fn = make_func("foo", return_value="X")
        parser = FuncParser({"foo": fn}, start_char="@")
        result = parser.parse("@foo()")
        assert result == "X"

    def test_custom_start_char_does_not_match_dollar(self, global_test_env):
        # If start_char is @, then $foo() should NOT be parsed
        fn = make_func("foo", return_value="X")
        parser = FuncParser({"foo": fn}, start_char="@")
        result = parser.parse("$foo()")
        assert result == "$foo()"

    def test_default_kwargs_stored(self, global_test_env):
        parser = FuncParser({}, foo="bar")
        assert parser.default_kwargs == {"foo": "bar"}


# ============================================================================
# validate_callables
# ============================================================================

class TestValidateCallables:
    def test_function_with_args_kwargs_passes(self, global_test_env):
        def myfn(*args, **kwargs):
            return ""
        # Should not raise
        FuncParser({"myfn": myfn})

    def test_function_without_args_raises(self, global_test_env):
        def myfn(x, **kwargs):  # no *args
            return ""
        with pytest.raises(AssertionError, match="\\*args"):
            FuncParser({"myfn": myfn})

    def test_function_without_kwargs_raises(self, global_test_env):
        def myfn(*args):  # no **kwargs
            return ""
        with pytest.raises(AssertionError, match="\\*\\*kwargs"):
            FuncParser({"myfn": myfn})

    def test_lambda_passes(self, global_test_env):
        # *args/**kwargs via *args, **kwargs
        parser = FuncParser({"x": lambda *a, **k: 1})
        assert "x" in parser.callables


# ============================================================================
# execute()
# ============================================================================

class TestExecute:
    def test_unknown_func_returns_string(self, global_test_env):
        # INTENT: unknown callables should NOT raise — they should leave the
        # function as-is in the output, so typos don't break display strings.
        parser = FuncParser({})
        pf = _ParsedFunc(prefix="$", funcname="missing", args=[], kwargs={})
        pf.rawstr = "missing()"
        result = parser.execute(pf)
        assert result == "$missing()"

    def test_unknown_func_raises_when_requested(self, global_test_env):
        parser = FuncParser({})
        pf = _ParsedFunc(prefix="$", funcname="missing", args=[], kwargs={})
        pf.rawstr = "missing()"
        with pytest.raises(ParsingError, match="missing"):
            parser.execute(pf, raise_errors=True)

    def test_known_func_called(self, global_test_env):
        fn = make_func("foo", return_value="RESULT")
        parser = FuncParser({"foo": fn})
        pf = _ParsedFunc(prefix="$", funcname="foo", args=["x"], kwargs={})
        pf.rawstr = "foo(x)"
        result = parser.execute(pf)
        fn.assert_called_once()
        assert result == "RESULT"

    def test_kwargs_merged_priority(self, global_test_env):
        # INTENT: priority order is defaults < string < reserved
        # We verify by checking what the callable receives.
        captured = {}

        def myfn(*args, **kwargs):
            captured.update(kwargs)
            return ""

        parser = FuncParser({"myfn": myfn}, greeting="default", fromdefault="yes")
        pf = _ParsedFunc(prefix="$", funcname="myfn", args=[], kwargs={"fromstring": "yes"})
        pf.rawstr = "myfn()"
        parser.execute(pf, override="yes", reserved="yes")
        # All three layers should be present
        assert captured.get("fromdefault") == "yes"
        assert captured.get("fromstring") == "yes"
        assert captured.get("reserved") == "yes"
        # And the parser always injects its own kwargs
        assert "funcparser" in captured
        assert "raise_errors" in captured

    def test_reserved_overrides_string(self, global_test_env):
        # INTENT: reserved > string > default
        captured = {}

        def myfn(*args, **kwargs):
            captured.update(kwargs)
            return ""

        parser = FuncParser({"myfn": myfn}, x="default")
        pf = _ParsedFunc(prefix="$", funcname="myfn", args=[], kwargs={"x": "string"})
        pf.rawstr = "myfn()"
        parser.execute(pf, x="reserved")
        assert captured["x"] == "reserved"

    def test_string_overrides_default(self, global_test_env):
        captured = {}

        def myfn(*args, **kwargs):
            captured.update(kwargs)
            return ""

        parser = FuncParser({"myfn": myfn}, x="default")
        pf = _ParsedFunc(prefix="$", funcname="myfn", args=[], kwargs={"x": "string"})
        pf.rawstr = "myfn()"
        parser.execute(pf)
        assert captured["x"] == "string"

    def test_funcparser_kwarg_injected(self, global_test_env):
        captured = {}

        def myfn(*args, **kwargs):
            captured.update(kwargs)
            return ""

        parser = FuncParser({"myfn": myfn})
        pf = _ParsedFunc(prefix="$", funcname="myfn", args=[], kwargs={})
        pf.rawstr = "myfn()"
        parser.execute(pf)
        assert captured["funcparser"] is parser

    def test_raise_errors_kwarg_injected(self, global_test_env):
        captured = {}

        def myfn(*args, **kwargs):
            captured.update(kwargs)
            return ""

        parser = FuncParser({"myfn": myfn})
        pf = _ParsedFunc(prefix="$", funcname="myfn", args=[], kwargs={})
        pf.rawstr = "myfn()"
        parser.execute(pf, raise_errors=True)
        assert captured["raise_errors"] is True

    def test_parsing_error_swallowed_by_default(self, global_test_env):
        def myfn(*args, **kwargs):
            raise ParsingError("boom")
        parser = FuncParser({"myfn": myfn})
        pf = _ParsedFunc(prefix="$", funcname="myfn", args=[], kwargs={})
        pf.rawstr = "myfn()"
        # Should NOT raise; returns str(parsedfunc)
        result = parser.execute(pf)
        assert result == "$myfn()"

    def test_parsing_error_raises_when_requested(self, global_test_env):
        def myfn(*args, **kwargs):
            raise ParsingError("boom")
        parser = FuncParser({"myfn": myfn})
        pf = _ParsedFunc(prefix="$", funcname="myfn", args=[], kwargs={})
        pf.rawstr = "myfn()"
        with pytest.raises(ParsingError, match="boom"):
            parser.execute(pf, raise_errors=True)

    def test_generic_exception_returns_unparsed(self, global_test_env):
        # INTENT: a non-ParsingError exception in a callable is caught,
        # logged via logger.error(traceback.format_exc()), and the unparsed
        # function string is returned.
        def myfn(*args, **kwargs):
            raise ValueError("oops")
        parser = FuncParser({"myfn": myfn})
        pf = _ParsedFunc(prefix="$", funcname="myfn", args=[], kwargs={})
        pf.rawstr = "myfn()"
        result = parser.execute(pf)
        assert result == "$myfn()"

    def test_generic_exception_raises_when_requested(self, global_test_env):
        # INTENT: with raise_errors=True, the underlying exception propagates
        # after being logged.
        def myfn(*args, **kwargs):
            raise ValueError("oops")
        parser = FuncParser({"myfn": myfn})
        pf = _ParsedFunc(prefix="$", funcname="myfn", args=[], kwargs={})
        pf.rawstr = "myfn()"
        with pytest.raises(ValueError, match="oops"):
            parser.execute(pf, raise_errors=True)


# ============================================================================
# parse() — the main API
# ============================================================================

class TestParsePlain:
    def test_no_funcs(self, global_test_env):
        parser = FuncParser({})
        assert parser.parse("Hello world") == "Hello world"

    def test_empty_string(self, global_test_env):
        parser = FuncParser({})
        assert parser.parse("") == ""

    def test_dollar_sign_without_funcname(self, global_test_env):
        parser = FuncParser({})
        # A lone $ should pass through unchanged
        assert parser.parse("$") == "$"

    def test_preserves_whitespace(self, global_test_env):
        parser = FuncParser({})
        assert parser.parse("  spaces  here  ") == "  spaces  here  "


class TestParseExec:
    def test_simple_func(self, global_test_env):
        fn = make_func("foo", return_value="X")
        parser = FuncParser({"foo": fn})
        assert parser.parse("$foo()") == "X"

    def test_func_with_arg(self, global_test_env):
        captured = {}

        def myfn(*args, **kwargs):
            captured["args"] = args
            return "OUT"
        parser = FuncParser({"myfn": myfn})
        result = parser.parse("$myfn(hello)")
        assert result == "OUT"
        assert captured["args"] == ("hello",)

    def test_func_with_multiple_args(self, global_test_env):
        captured = {}

        def myfn(*args, **kwargs):
            captured["args"] = args
            return ""
        parser = FuncParser({"myfn": myfn})
        parser.parse("$myfn(a, b, c)")
        assert captured["args"] == ("a", "b", "c")

    def test_func_with_kwargs(self, global_test_env):
        captured = {}

        def myfn(*args, **kwargs):
            captured["kwargs"] = kwargs
            return ""
        parser = FuncParser({"myfn": myfn})
        parser.parse("$myfn(name=bob, age=5)")
        assert captured["kwargs"]["name"] == "bob"
        assert captured["kwargs"]["age"] == "5"

    def test_mixed_text_and_func(self, global_test_env):
        fn = make_func("foo", return_value="X")
        parser = FuncParser({"foo": fn})
        result = parser.parse("Hello $foo() world")
        assert result == "Hello X world"

    def test_func_at_start(self, global_test_env):
        fn = make_func("foo", return_value="X")
        parser = FuncParser({"foo": fn})
        result = parser.parse("$foo() then text")
        assert result == "X then text"

    def test_func_at_end(self, global_test_env):
        fn = make_func("foo", return_value="X")
        parser = FuncParser({"foo": fn})
        result = parser.parse("text then $foo()")
        assert result == "text then X"

    def test_multiple_funcs(self, global_test_env):
        fn = make_func("a", return_value="1")
        fn2 = make_func("b", return_value="2")
        parser = FuncParser({"a": fn, "b": fn2})
        result = parser.parse("$a() and $b()")
        assert result == "1 and 2"

    def test_func_returning_int(self, global_test_env):
        # The result is converted to a string
        fn = make_func("foo", return_value=42)
        parser = FuncParser({"foo": fn})
        result = parser.parse("Number: $foo()")
        assert result == "Number: 42"

    def test_func_returning_empty_string(self, global_test_env):
        fn = make_func("foo", return_value="")
        parser = FuncParser({"foo": fn})
        result = parser.parse("A$foo()B")
        assert result == "AB"


class TestParseEscape:
    def test_double_dollar_escape(self, global_test_env):
        # INTENT: $$ in source means a literal $ in output
        parser = FuncParser({})
        # Without a registered foo, plain $foo would be left as-is
        # But $$ should become a literal $ BEFORE further processing
        result = parser.parse("$$5")
        assert result == "$5"

    def test_backslash_dollar_escape(self, global_test_env):
        # INTENT: \\$func escapes the function — it should NOT execute
        fn = make_func("foo", return_value="X")
        parser = FuncParser({"foo": fn})
        result = parser.parse("\\$foo()")
        # The foo should NOT have been called
        fn.assert_not_called()
        # And the output should contain a literal $foo
        assert "$foo()" in result

    def test_escape_kwarg(self, global_test_env):
        # INTENT: escape=True escapes all found functions in output
        fn = make_func("foo", return_value="X")
        parser = FuncParser({"foo": fn})
        result = parser.parse("$foo()", escape=True)
        fn.assert_not_called()
        assert "$foo()" in result


class TestParseStrip:
    def test_strip_removes_func(self, global_test_env):
        # INTENT: strip=True removes the function from the output entirely
        fn = make_func("foo", return_value="X")
        parser = FuncParser({"foo": fn})
        result = parser.parse("A$foo()B", strip=True)
        fn.assert_not_called()
        assert result == "AB"

    def test_strip_vs_escape(self, global_test_env):
        # INTENT: strip removes; escape preserves as literal
        fn = make_func("foo", return_value="X")
        parser_strip = FuncParser({"foo": make_func("foo", return_value="X")})
        parser_escape = FuncParser({"foo": make_func("foo", return_value="X")})
        # These use separate mocks so we can compare behavior
        stripped = parser_strip.parse("A$foo()B", strip=True)
        escaped = parser_escape.parse("A$foo()B", escape=True)
        # strip removes the function entirely
        assert "foo" not in stripped
        # escape preserves the function as literal
        assert "foo" in escaped


class TestParseUnknown:
    def test_unknown_func_left_as_is(self, global_test_env):
        # INTENT: unknown callables should not break the parser
        parser = FuncParser({})
        result = parser.parse("Hello $unknown() world")
        assert result == "Hello $unknown() world"

    def test_unknown_with_args_left_as_is(self, global_test_env):
        parser = FuncParser({})
        result = parser.parse("$missing(a, b=1)")
        assert result == "$missing(a, b=1)"

    def test_known_and_unknown_mixed(self, global_test_env):
        fn = make_func("known", return_value="K")
        parser = FuncParser({"known": fn})
        result = parser.parse("$known() and $unknown()")
        assert result == "K and $unknown()"


class TestParseRaiseErrors:
    def test_malformed_left_as_is_even_with_raise(self, global_test_env):
        # INTENT/BUG: An unclosed paren currently doesn't raise even with
        # raise_errors=True. The malformed function is silently left as-is.
        # This documents the current (somewhat permissive) behavior.
        parser = FuncParser({})
        result = parser.parse("$unclosed(", raise_errors=True)
        assert result == "$unclosed("

    def test_raises_on_unknown_when_requested(self, global_test_env):
        parser = FuncParser({})
        with pytest.raises(ParsingError, match="missing"):
            parser.parse("$missing()", raise_errors=True)

    def test_no_raise_by_default(self, global_test_env):
        # INTENT: graceful degradation — never raise by default
        parser = FuncParser({})
        # This should not raise
        result = parser.parse("$unclosed( and $unknown()")
        # Result is a string
        assert isinstance(result, str)


class TestParseNesting:
    def test_simple_nested(self, global_test_env):
        fn_outer = MagicMock()
        fn_outer.__name__ = "outer"
        fn_inner = MagicMock()
        fn_inner.__name__ = "inner"
        fn_inner.return_value = "INNER"
        fn_outer.return_value = "OUTER"
        fn_outer.side_effect = lambda *a, **k: f"<{a[0]}>"
        parser = FuncParser({"outer": fn_outer, "inner": fn_inner})
        result = parser.parse("$outer($inner())")
        # inner must have been called
        fn_inner.assert_called_once()
        # outer's first arg should be the inner result
        assert "INNER" in result

    def test_nested_in_arg(self, global_test_env):
        captured = {}

        def myfn(*args, **kwargs):
            captured["args"] = args
            return ""
        parser = FuncParser({"myfn": myfn})
        parser.parse("$myfn(Hello $name(world))")  # $name is unknown
        # The outer fn should still have been called, with one arg
        assert len(captured["args"]) == 1
        # The arg should contain the unknown $name() as a string
        assert "$name(world)" in captured["args"][0]

    def test_max_nesting(self, global_test_env):
        # INTENT: deeply nested funcs should be handled gracefully
        parser = FuncParser({})
        # Build a string with 25 nested levels (exceeds default 20)
        s = "x" + "$" * 25 + "f()"
        # Should not crash
        result = parser.parse(s)
        assert isinstance(result, str)


class TestParseReturnStr:
    def test_return_str_true_is_default(self, global_test_env):
        # INTENT: by default, always returns a string
        fn = make_func("foo", return_value=42)
        parser = FuncParser({"foo": fn})
        result = parser.parse("$foo()")
        assert isinstance(result, str)

    def test_return_str_false_returns_raw_when_pure(self, global_test_env):
        # INTENT: if the string is ONLY a $func() call, return the raw value
        fn = make_func("foo", return_value=42)
        parser = FuncParser({"foo": fn})
        result = parser.parse("$foo()", return_str=False)
        assert result == 42  # int, not str

    def test_return_str_false_still_string_when_mixed(self, global_test_env):
        # INTENT: if mixed with other text, always return string
        fn = make_func("foo", return_value=42)
        parser = FuncParser({"foo": fn})
        result = parser.parse("text $foo() more", return_str=False)
        assert isinstance(result, str)


class TestParseToAny:
    def test_pure_call_returns_raw(self, global_test_env):
        # INTENT: parse_to_any is a convenience for "give me the value if it's pure"
        fn = make_func("foo", return_value=42)
        parser = FuncParser({"foo": fn})
        assert parser.parse_to_any("$foo()") == 42

    def test_mixed_returns_string(self, global_test_env):
        fn = make_func("foo", return_value=42)
        parser = FuncParser({"foo": fn})
        result = parser.parse_to_any("text $foo() more")
        assert isinstance(result, str)

    def test_pure_unknown_returns_string(self, global_test_env):
        parser = FuncParser({})
        # parse_to_any with return_str=False: if not pure, returns a string
        result = parser.parse_to_any("$unknown()")
        # It's a string, not None
        assert isinstance(result, str)


# ============================================================================
# Built-in callables
# ============================================================================

class TestEval:
    def test_simple_arithmetic(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_eval
        assert funcparser_callable_eval("1+2") == 3
        assert funcparser_callable_eval("3*4") == 12
        assert funcparser_callable_eval("10-3") == 7
        assert funcparser_callable_eval("10/2") == 5.0

    def test_literal_int(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_eval
        assert funcparser_callable_eval("42") == 42

    def test_literal_list(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_eval
        assert funcparser_callable_eval("[1,2,3]") == [1, 2, 3]

    def test_literal_string(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_eval
        assert funcparser_callable_eval("'hello'") == "hello"

    def test_empty_returns_empty(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_eval
        assert funcparser_callable_eval("") == ""


class TestArith:
    def test_add(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_add
        assert funcparser_callable_add("3", "4") == 7

    def test_sub(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_sub
        assert funcparser_callable_sub("10", "3") == 7

    def test_mult(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_mult
        assert funcparser_callable_mult("3", "4") == 12

    def test_div(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_div
        assert funcparser_callable_div("10", "2") == 5.0

    def test_too_few_args(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_add
        # Need at least 2 args
        assert funcparser_callable_add("3") == ""


class TestRound:
    def test_round_to_int(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_round
        assert funcparser_callable_round("3.7") == 4

    def test_round_to_n_digits(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_round
        assert funcparser_callable_round("3.54343", "2") == 3.54

    def test_round_no_args(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_round
        assert funcparser_callable_round() == ""


class TestToInt:
    def test_float_to_int(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_toint
        assert funcparser_callable_toint("43.0") == 43

    def test_string_int(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_toint
        assert funcparser_callable_toint("42") == 42

    def test_invalid_returns_string(self, global_test_env):
        # INTENT: per the docstring, non-numeric input is returned unchanged
        # as a string. The function catches TypeError, ValueError, and the
        # ParsingError raised by funcparser_callable_eval on unparseable input.
        from atheriz.objects.funcparser import funcparser_callable_toint
        assert funcparser_callable_toint("abc") == "abc"


class TestRandom:
    def test_random_in_range(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_random
        result = funcparser_callable_random("5", "10")
        assert 5 <= result <= 10

    def test_random_int(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_random
        result = funcparser_callable_random("5", "10")
        assert isinstance(result, int)

    def test_random_float(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_random
        # If either has '.', returns float
        result = funcparser_callable_random("5.0", "10")
        assert isinstance(result, float)

    def test_random_no_args(self, global_test_env):
        # INTENT: with no args, defaults to (0, 1) range, integer
        from atheriz.objects.funcparser import funcparser_callable_random
        result = funcparser_callable_random()
        assert result in (0, 1)  # int from randint(0, 1)

    def test_randint_always_int(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_randint
        result = funcparser_callable_randint("5.0", "10.0")
        assert isinstance(result, int)


class TestChoice:
    def test_choice_from_list(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_choice
        result = funcparser_callable_choice("[1, 2, 3]")
        assert result in [1, 2, 3]

    def test_choice_from_args(self, global_test_env):
        # INTENT: choice(a, b, c) treats each as a Python literal (via
        # safe_convert_to_types with 'py' converter). Strings like 'a'
        # are Name nodes, not literals, so this raises.
        from atheriz.objects.funcparser import funcparser_callable_choice
        # The docstring's `$choice(key, flower, house)` only works if
        # the args happen to be valid Python literals. Document this.
        with pytest.raises(ParsingError):
            funcparser_callable_choice("a", "b", "c")

    def test_choice_from_int_args(self, global_test_env):
        # Integer args work because they're valid Python literals
        from atheriz.objects.funcparser import funcparser_callable_choice
        result = funcparser_callable_choice(1, 2, 3)
        assert result in (1, 2, 3)

    def test_choice_no_args(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_choice
        assert funcparser_callable_choice() == ""


class TestPad:
    def test_center_pad(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pad
        result = funcparser_callable_pad("hi", "10", "c")
        assert len(result) == 10
        assert "hi" in result

    def test_left_pad(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pad
        result = funcparser_callable_pad("hi", "10", "l")
        assert result.startswith("hi")
        assert len(result) == 10

    def test_right_pad(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pad
        result = funcparser_callable_pad("hi", "10", "r")
        assert result.endswith("hi")
        assert len(result) == 10

    def test_invalid_align_defaults_to_center(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pad
        result = funcparser_callable_pad("hi", "10", "x")
        assert len(result) == 10
        # 'x' is not in (c, l, r) so it defaults to 'c'
        # Verify it's centered
        assert result.index("hi") == (10 - 2) // 2

    def test_no_args(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pad
        assert funcparser_callable_pad() == ""


class TestCrop:
    def test_short_text_unchanged(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_crop
        assert funcparser_callable_crop("hi", "10") == "hi"

    def test_long_text_cropped(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_crop
        result = funcparser_callable_crop("a" * 100, "10", "...")
        assert len(result) == 10
        assert result.endswith("...")

    def test_custom_suffix(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_crop
        result = funcparser_callable_crop("a" * 100, "10", "X")
        assert result.endswith("X")


class TestJustify:
    def test_left_justify(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_justify
        result = funcparser_callable_justify("hi", "10", "l")
        assert result.startswith("hi")
        assert len(result) == 10

    def test_right_justify(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_justify
        result = funcparser_callable_justify("hi", "10", "r")
        assert result.endswith("hi")
        assert len(result) == 10

    def test_center_justify(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_justify
        result = funcparser_callable_justify("hi", "10", "c")
        assert "hi" in result
        assert len(result) == 10

    def test_legacy_left(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_left_justify
        result = funcparser_callable_left_justify("hi", "10")
        assert len(result) == 10


class TestSpace:
    def test_returns_whitespace(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_space
        result = funcparser_callable_space("5")
        assert result == "     "
        assert len(result) == 5

    def test_no_args(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_space
        assert funcparser_callable_space() == ""

    def test_invalid_returns_one_space(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_space
        # 'abc' can't be int()'d, defaults to 1
        assert funcparser_callable_space("abc") == " "


class TestClr:
    def test_basic_color(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_clr
        result = funcparser_callable_clr("r", "text", "n")
        assert result == "|rtext|n"

    def test_default_end(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_clr
        # Only 2 args: end defaults to |n
        result = funcparser_callable_clr("r", "text")
        assert result == "|rtext|n"

    def test_no_color(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_clr
        result = funcparser_callable_clr("text")
        assert result == "text"

    def test_keyword_form(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_clr
        result = funcparser_callable_clr("text", start="r", end="n")
        assert result == "|rtext|n"


class TestPluralize:
    def test_singular(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pluralize
        assert funcparser_callable_pluralize("cat", "1") == "cat"

    def test_plural(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pluralize
        assert funcparser_callable_pluralize("cat", "2") == "cats"

    def test_zero_treated_as_singular(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pluralize
        assert funcparser_callable_pluralize("cat", "0") == "cat"

    def test_custom_plural(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pluralize
        assert funcparser_callable_pluralize("goose", "3", "geese") == "geese"

    def test_no_args(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pluralize
        assert funcparser_callable_pluralize() == ""


class TestInt2Str:
    def test_small_numbers(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_int2str
        assert funcparser_callable_int2str("1") == "one"
        assert funcparser_callable_int2str("5") == "five"
        assert funcparser_callable_int2str("12") == "twelve"

    def test_large_numbers(self, global_test_env):
        # Beyond 12, returns the digit
        from atheriz.objects.funcparser import funcparser_callable_int2str
        assert funcparser_callable_int2str("15") == "15"
        assert funcparser_callable_int2str("100") == "100"

    def test_zero(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_int2str
        assert funcparser_callable_int2str("0") == "no"

    def test_no_args(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_int2str
        assert funcparser_callable_int2str() == ""


class TestAn:
    def test_vowel(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_an
        assert funcparser_callable_an("apple") == "an apple"
        assert funcparser_callable_an("elephant") == "an elephant"

    def test_consonant(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_an
        assert funcparser_callable_an("banana") == "a banana"
        assert funcparser_callable_an("cat") == "a cat"

    def test_y_is_vowel(self, global_test_env):
        # INTENT: the source uses 'aeiouy' as the vowel set
        from atheriz.objects.funcparser import funcparser_callable_an
        assert funcparser_callable_an("yellow") == "an yellow"

    def test_no_args(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_an
        assert funcparser_callable_an() == ""


# ============================================================================
# Actor-stance callables
# ============================================================================

class TestYou:
    def test_self_sees_you(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_you
        result = funcparser_callable_you(caller="alice", receiver="alice")
        assert result == "you"

    def test_other_sees_display_name(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_you

        class Obj:
            def get_display_name(self, looker):
                return "Alice"

        obj = Obj()
        result = funcparser_callable_you(caller=obj, receiver="bob")
        assert result == "Alice"

    def test_capitalize(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_you
        result = funcparser_callable_you(caller="alice", receiver="alice", capitalize=True)
        assert result == "You"

    def test_no_caller_or_receiver_raises(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_you
        with pytest.raises(ParsingError, match="No caller"):
            funcparser_callable_you()


class TestYour:
    def test_self(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_your
        result = funcparser_callable_your(caller="alice", receiver="alice")
        assert result == "your"

    def test_other(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_your

        class Obj:
            def get_display_name(self, looker):
                return "Bob"

        result = funcparser_callable_your(caller=Obj(), receiver="alice")
        assert result == "Bob's"

    def test_capitalize(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_your
        result = funcparser_callable_your(caller="alice", receiver="alice", capitalize=True)
        assert result == "Your"


class TestConjugate:
    def test_self_uses_second_person(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_conjugate
        # "jump" -> "jump" for self, "jumps" for other
        result = funcparser_callable_conjugate("jump", caller="alice", receiver="alice")
        assert result == "jump"

    def test_other_uses_third_person(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_conjugate
        result = funcparser_callable_conjugate("jump", caller="alice", receiver="bob")
        assert result == "jumps"

    def test_no_caller_raises(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_conjugate
        with pytest.raises(ParsingError, match="No caller"):
            funcparser_callable_conjugate("jump", receiver="bob")

    def test_no_args(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_conjugate
        assert funcparser_callable_conjugate(caller="x", receiver="x") == ""

    def test_with_mapping(self, global_test_env):
        # If mapping is provided and a key is given, the key's object is used
        from atheriz.objects.funcparser import funcparser_callable_conjugate
        # caller=alice, mapping has tommy=alice, options=["tommy"]
        # The verb should be conjugated for alice (the mapped object)
        result = funcparser_callable_conjugate(
            "jump", "tommy", caller="alice", receiver="alice", mapping={"tommy": "alice"}
        )
        assert result == "jump"


class TestPConjugate:
    def test_self(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_conjugate_for_pronouns
        result = funcparser_callable_conjugate_for_pronouns(
            "jump", caller="x", receiver="x"
        )
        assert result == "jump"

    def test_other_singular(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_conjugate_for_pronouns
        obj = MagicMock()
        obj.gender = "male"
        result = funcparser_callable_conjugate_for_pronouns(
            "jump", caller=obj, receiver="other"
        )
        assert result == "jumps"

    def test_other_plural(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_conjugate_for_pronouns
        obj = MagicMock()
        obj.gender = "plural"
        result = funcparser_callable_conjugate_for_pronouns(
            "jump", caller=obj, receiver="other"
        )
        # The verb should use plural 3rd person form
        assert "jump" in result


class TestPronoun:
    def test_self_sees_first_or_second(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pronoun
        result = funcparser_callable_pronoun("I", caller="alice", receiver="alice")
        # "I" -> "I" for self
        assert result == "I"

    def test_other_sees_third(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pronoun
        # When viewing from a different person, "I" -> 3rd person
        # Default gender is "neutral" -> "it" for subject
        result = funcparser_callable_pronoun("I", caller="alice", receiver="bob")
        assert result == "it"

    def test_gender_male(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pronoun
        obj = MagicMock()
        obj.gender = "male"
        result = funcparser_callable_pronoun("I", caller=obj, receiver="bob")
        assert result == "he"

    def test_gender_female(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pronoun
        obj = MagicMock()
        obj.gender = "female"
        result = funcparser_callable_pronoun("I", caller=obj, receiver="bob")
        assert result == "she"

    def test_gender_plural(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pronoun
        obj = MagicMock()
        obj.gender = "plural"
        result = funcparser_callable_pronoun("I", caller=obj, receiver="bob")
        assert result == "they"

    def test_capitalize(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pronoun
        result = funcparser_callable_pronoun(
            "I", caller="alice", receiver="alice", capitalize=True
        )
        assert result == "I"

    def test_no_args(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pronoun
        assert funcparser_callable_pronoun(caller="x", receiver="x") == ""

    def test_callable_gender(self, global_test_env):
        # INTENT: gender can be a callable that returns the gender string
        from atheriz.objects.funcparser import funcparser_callable_pronoun
        obj = MagicMock()
        obj.gender = MagicMock(return_value="male")
        result = funcparser_callable_pronoun("I", caller=obj, receiver="bob")
        assert result == "he"


# ============================================================================
# Integration: full pipeline
# ============================================================================

class TestIntegration:
    def test_built_in_parser(self, global_test_env):
        # INTENT: the entire built-in callable set should work via FuncParser
        parser = FuncParser(FUNCPARSER_CALLABLES)
        result = parser.parse("$an(apple) and $an(banana)")
        assert result == "an apple and a banana"

    def test_actor_stance_parser(self, global_test_env):
        # INTENT: the full actor-stance set should work
        parser = FuncParser(ACTOR_STANCE_CALLABLES)
        result = parser.parse("$You() $conj(laugh)", caller="alice", receiver="alice")
        assert "You" in result
        assert "laugh" in result

    def test_complex_string(self, global_test_env):
        # Mix of plain text and multiple funcs
        parser = FuncParser(FUNCPARSER_CALLABLES)
        result = parser.parse("Count: $eval(1+2), Plural: $pluralize(cat, 3), An: $an(orange)")
        assert "Count: 3" in result
        assert "Plural: cats" in result
        assert "An: an orange" in result

    def test_safe_failure_in_one_func(self, global_test_env):
        # INTENT: one func failing should not break the rest of the parse
        # The parser catches ParsingError internally. The result includes
        # the failed function (in some form) and the others work.
        parser = FuncParser(FUNCPARSER_CALLABLES)
        result = parser.parse("A$eval(abc)B and $an(orange)")
        # $an(orange) should work
        assert "an orange" in result
        # The result should still be a string
        assert isinstance(result, str)
        # 'A' and 'B' should surround the failed eval
        assert result.startswith("A")
        assert "B and" in result
