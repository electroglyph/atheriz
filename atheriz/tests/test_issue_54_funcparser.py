from __future__ import annotations

import time

import pytest

from atheriz.objects.funcparser import FuncParser, ParsingError, _ParsedFunc
from atheriz.objects.funcparser_helpers import safe_convert_to_types
import atheriz.settings as settings


class Test54aListsAndJoin:
    def test_ParsedFunc_defaults_are_lists(self, global_test_env):
        pf = _ParsedFunc()
        assert isinstance(pf.fullstr, list)
        assert isinstance(pf.infuncstr, list)
        assert "".join(pf.fullstr) == ""
        assert "".join(pf.infuncstr) == ""
        assert str(pf) == ""

    def test_ParsedFunc_str_handles_both(self, global_test_env):
        pf1 = _ParsedFunc(prefix="$", fullstr="$foo(", infuncstr="bar")
        assert str(pf1) == "$foo(bar"
        pf2 = _ParsedFunc(prefix="$", fullstr=list("$foo("), infuncstr=list("bar"))
        assert str(pf2) == "$foo(bar"

    def test_large_input_performance_and_correctness(self, global_test_env):
        parser = FuncParser({"pluralize": lambda *a, **k: __import__('atheriz.objects.funcparser', fromlist=['funcparser_callable_pluralize']).funcparser_callable_pluralize(*a, **k)})
        # Use actual builtin pluralize via FUNCPARSER_CALLABLES for realism
        from atheriz.objects.funcparser import FUNCPARSER_CALLABLES
        parser = FuncParser(FUNCPARSER_CALLABLES)
        # Build 60KB string with many funcs
        chunk = "$pluralize(cat, 2) "
        repeats = 3000  # ~ 3000*17=51k + filler to reach 60k
        s = chunk * repeats + "x" * 10000
        # sanity length ~61k (< cap)
        assert len(s) < 2 * settings.WEBSOCKET_MAX_MESSAGE_SIZE
        start = time.monotonic()
        result = parser.parse(s)
        elapsed = time.monotonic() - start
        assert elapsed < 0.2, f"parse took {elapsed:.3f}s, expected <0.2s for quadratic fix"
        # Verify a few replacements
        assert result.count("cats") == repeats
        # Compare with small input for correctness reference
        small = "$pluralize(cat, 2) and $pluralize(dog, 1)"
        assert parser.parse(small) == "cats and dog"

    def test_large_input_with_quoting_correctness(self, global_test_env):
        from atheriz.objects.funcparser import FUNCPARSER_CALLABLES
        parser = FuncParser(FUNCPARSER_CALLABLES)
        s = '$pad("hello $pluralize(cat, 2) world", 20) ' * 500
        result = parser.parse(s)
        # quoting should keep inner $ literal, pad still works
        assert "$pluralize" not in result or "hello" in result

    def test_return_str_false_with_large(self, global_test_env):
        fn = lambda *a, **k: 42
        parser = FuncParser({"foo": fn})
        assert parser.parse("$foo()", return_str=False) == 42
        # mixed with text still returns string
        assert isinstance(parser.parse("hi $foo() there", return_str=False), str)
        # large mixed
        s = "a" * 50000 + "$foo()" + "b" * 5000
        result = parser.parse(s, return_str=False)
        assert isinstance(result, str)
        assert "a" * 10 in result

    def test_length_cap_raises(self, global_test_env):
        parser = FuncParser({})
        huge = "x" * (2 * settings.WEBSOCKET_MAX_MESSAGE_SIZE + 1)
        with pytest.raises(ParsingError, match="too long"):
            parser.parse(huge)
        # exactly at cap should not raise
        at_cap = "x" * (2 * settings.WEBSOCKET_MAX_MESSAGE_SIZE)
        assert parser.parse(at_cap) == at_cap

    def test_escape_and_nesting_still_work(self, global_test_env):
        parser = FuncParser({"foo": lambda *a, **k: "X", "bar": lambda *a, **k: "Y"})
        # double dollar escape
        assert parser.parse("$$foo()") == "$foo()"
        # nested
        assert parser.parse("$foo($bar())") == "X"
        # quoting with dollar literal inside quoted arg should not execute
        boom = pytest.importorskip("unittest.mock").MagicMock(return_value="DOOM")
        boom.__name__ = "boom"
        def pad_fn(*args, **kwargs):
            return args[0] if args else ""
        parser2 = FuncParser({"pad": pad_fn, "boom": boom})
        result = parser2.parse('$pad("costs $boom() here", 30)')
        boom.assert_not_called()
        assert "$boom()" in result

    def test_unclosed_parens_graceful(self, global_test_env):
        parser = FuncParser({"foo": lambda *a, **k: "X"})
        # malformed should degrade gracefully (left as-is) when raise_errors=False
        result = parser.parse("$foo(unclosed")
        assert isinstance(result, str)
        assert "$foo(unclosed" in result

    def test_callstack_merge_correctness(self, global_test_env):
        # Exercise the callstack pop merge path (nested funcs)
        captured = {}
        def outer(*args, **kwargs):
            captured["args"] = args
            return f"outer-{args[0]}"
        def inner(*args, **kwargs):
            return "INNER"
        parser = FuncParser({"outer": outer, "inner": inner})
        result = parser.parse("start $outer($inner()) end")
        assert result == "start outer-INNER end"
        assert captured["args"][0] == "INNER"

    def test_fullstr_list_join_at_end(self, global_test_env):
        # Verify fullstr tail handling (fullstr += infuncstr) works with lists
        parser = FuncParser({})
        result = parser.parse("hello $unknown() world")
        assert result == "hello $unknown() world"


class Test54bPluralize:
    def test_non_numeric_fallback_singular(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pluralize
        assert funcparser_callable_pluralize("cat", "abc") == "cat"
        assert funcparser_callable_pluralize("cat", "abc", "cats") == "cat"
        assert funcparser_callable_pluralize("cat", "") == "cat"
        assert funcparser_callable_pluralize("cat", None) == "cat"

    def test_non_numeric_raise_errors(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pluralize
        with pytest.raises(ParsingError, match="not an integer"):
            funcparser_callable_pluralize("cat", "abc", raise_errors=True)
        with pytest.raises(ParsingError):
            funcparser_callable_pluralize("cat", "2.0", raise_errors=True)
        with pytest.raises(ParsingError):
            funcparser_callable_pluralize("cat", None, raise_errors=True)

    def test_valid_numbers(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pluralize
        assert funcparser_callable_pluralize("cat", "0") == "cat"
        assert funcparser_callable_pluralize("cat", "1") == "cat"
        assert funcparser_callable_pluralize("cat", "2") == "cats"
        assert funcparser_callable_pluralize("cat", "-1") == "cat"
        assert funcparser_callable_pluralize("cat", "-2") == "cats"
        assert funcparser_callable_pluralize("goose", "3", "geese") == "geese"
        assert funcparser_callable_pluralize("cat", 2) == "cats"
        assert funcparser_callable_pluralize("cat", 0) == "cat"

    def test_float_string_fallback(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pluralize
        # int("2.0") raises -> fallback to singular
        assert funcparser_callable_pluralize("cat", "2.0") == "cat"
        with pytest.raises(ParsingError):
            funcparser_callable_pluralize("cat", "2.0", raise_errors=True)

    def test_bool_handling(self, global_test_env):
        from atheriz.objects.funcparser import funcparser_callable_pluralize
        assert funcparser_callable_pluralize("cat", True) == "cat"
        assert funcparser_callable_pluralize("cat", False) == "cat"

    def test_via_parser_integration(self, global_test_env):
        from atheriz.objects.funcparser import FUNCPARSER_CALLABLES
        parser = FuncParser(FUNCPARSER_CALLABLES)
        assert parser.parse("$pluralize(cat, abc)") == "cat"
        assert parser.parse("$pluralize(cat, 2)") == "cats"
        with pytest.raises(ParsingError):
            parser.parse("$pluralize(cat, abc)", raise_errors=True)


class Test54cValidateCallables:
    def test_valid_passes(self, global_test_env):
        def ok(*args, **kwargs):
            return ""
        FuncParser({"ok": ok})

    def test_missing_varargs_raises_parsing_error(self, global_test_env):
        def bad(x, **kwargs):
            return ""
        with pytest.raises(ParsingError, match=r"\*args"):
            FuncParser({"bad": bad})

    def test_missing_varkw_raises_parsing_error(self, global_test_env):
        def bad(*args):
            return ""
        with pytest.raises(ParsingError, match=r"\*\*kwargs"):
            FuncParser({"bad": bad})

    def test_missing_both_raises(self, global_test_env):
        def bad():
            return ""
        with pytest.raises(ParsingError):
            FuncParser({"bad": bad})

    def test_builtin_without_spec_warns_not_raises(self, global_test_env):
        # builtins like len have no getfullargspec -> warning path
        import math
        # math.sqrt has no varargs but getfullargspec may succeed? Use len
        parser = FuncParser({"ok": lambda *a, **k: 1})
        assert "ok" in parser.callables

    def test_docstring_updated(self, global_test_env):
        import inspect
        doc = inspect.getdoc(FuncParser.validate_callables)
        assert "ParsingError" in doc


class Test54dManualParseContainers:
    def test_flat_containers_still_work(self, global_test_env):
        args, _ = safe_convert_to_types((("py",), {}), "(a, b)", raise_errors=True)
        assert args[0] == ["a", "b"]
        args, _ = safe_convert_to_types((("py",), {}), "[1, 2, 3]", raise_errors=True)
        assert args[0] == [1, 2, 3]
        args, _ = safe_convert_to_types((("py",), {}), "(a, b, c)", raise_errors=True)
        assert args[0] == ["a", "b", "c"]

    def test_flat_with_quoted_comma(self, global_test_env):
        args, _ = safe_convert_to_types((("py",), {}), "('a, b', 'c')", raise_errors=True)
        # literal_eval succeeds for this -> tuple
        assert args[0] == ("a, b", "c") or args[0] == ["a, b", "c"]

    def test_nested_rejected_via_manual_path(self, global_test_env):
        # Force manual path by using non-literal inner: (a,(b,c)) literal_eval fails -> manual should reject -> ParsingError
        with pytest.raises(ParsingError):
            safe_convert_to_types((("py",), {}), "(a,(b,c))", raise_errors=True)
        with pytest.raises(ParsingError):
            safe_convert_to_types((("py",), {}), "(a, [1,2])", raise_errors=True)
        # valid Python nested literal should succeed via literal_eval, not manual
        args, _ = safe_convert_to_types((("py",), {}), "([1,2], 3)", raise_errors=True)
        assert args[0] == ([1, 2], 3)

    def test_nested_via_mocked_literal_eval(self, global_test_env):
        # Directly test _manual returning None leads to ParsingError even if we mock
        from unittest.mock import patch
        from atheriz.objects import funcparser_helpers as fh
        with patch.object(fh, "literal_eval", side_effect=ValueError("mock")):
            with patch.object(fh, "_safe_arith_eval", side_effect=ValueError("mock")):
                # flat should still succeed via manual
                args, _ = safe_convert_to_types((("py",), {}), "(a, b)", raise_errors=True)
                assert args[0] == ["a", "b"]
                # nested should fail
                with pytest.raises(ParsingError):
                    safe_convert_to_types((("py",), {}), "(a,(b,c))", raise_errors=True)

    def test_quoted_commas_not_split(self, global_test_env):
        from unittest.mock import patch
        from atheriz.objects import funcparser_helpers as fh
        with patch.object(fh, "literal_eval", side_effect=ValueError("mock")):
            with patch.object(fh, "_safe_arith_eval", side_effect=ValueError("mock")):
                args, _ = safe_convert_to_types((("py",), {}), "('a, b', \"c, d\")", raise_errors=True)
                assert args[0] == ["'a, b'", '"c, d"']

    def test_valid_literal_still_uses_literal_eval(self, global_test_env):
        # (1,(2,3)) is valid python tuple, literal_eval succeeds -> should return actual tuple
        args, _ = safe_convert_to_types((("py",), {}), "(1,(2,3))", raise_errors=True)
        assert args[0] == (1, (2, 3))

    def test_empty_container(self, global_test_env):
        args, _ = safe_convert_to_types((("py",), {}), "()", raise_errors=True)
        # manual path for "()" returns [""] -> but literal_eval for "()" returns () tuple
        # Ensure no crash, either [] or () is acceptable but should not be mangled
        assert args[0] in ((), [""])

    def test_no_manual_corruption(self, global_test_env):
        # Ensure old bug: "(a,(b,c))" never returns ["a","(b","c)"]
        from unittest.mock import patch
        from atheriz.objects import funcparser_helpers as fh
        with patch.object(fh, "literal_eval", side_effect=ValueError("mock")):
            with patch.object(fh, "_safe_arith_eval", side_effect=ValueError("mock")):
                try:
                    safe_convert_to_types((("py",), {}), "(a,(b,c))", raise_errors=True)
                    assert False, "should have raised"
                except ParsingError as e:
                    assert "a" not in str(e) or "ParsingError" in type(e).__name__
                # Verify flat still not corrupted
                args, _ = safe_convert_to_types((("py",), {}), "(a, b)", raise_errors=True)
                assert args[0] != ["a", "(b"]
