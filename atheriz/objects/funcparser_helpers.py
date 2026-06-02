"""
Helper functions for funcparser, sourced from Evennia.

This file contains helper functions that funcparser.py needs.
All code in this file is from Evennia
and is licensed under BSD 3-Clause (see EVENNIA_LICENSE.txt at the repo root).

Source: https://github.com/evennia/evennia
Original file: evennia/utils/utils.py
"""

# --- Begin Evennia code (BSD 3-Clause) ---
# Copyright 2012- Griatch (griatch <AT> gmail <DOT> com), Gregory Taylor
# See EVENNIA_LICENSE.txt for full license text.

import importlib
import inspect
import types
from ast import literal_eval
from collections.abc import Callable
from inspect import getmembers, getmodule, ismodule
from unicodedata import east_asian_width


def is_iter(obj):
    """
    Checks if an object behaves iterably.

    Args:
        obj (any): Entity to check for iterability.

    Returns:
        is_iterable (bool): If `obj` is iterable or not.

    Notes:
        Strings are *not* accepted as iterable (although they are
        actually iterable), since string iterations are usually not
        what we want to do with a string.
    """
    if isinstance(obj, (str, bytes)):
        return False
    try:
        return iter(obj) and True
    except TypeError:
        return False


def make_iter(obj):
    """
    Makes sure that the object is always iterable.
    """
    return not is_iter(obj) and [obj] or obj


def mod_import(module):
    """
    A generic Python module loader.
    """
    if not module:
        return None
    if isinstance(module, types.ModuleType):
        return module
    try:
        return importlib.import_module(module)
    except ImportError:
        return None


def all_from_module(module):
    """
    Return all global-level variables defined in a module.
    """
    mod = mod_import(module)
    if not mod:
        return {}
    members = getmembers(mod, predicate=lambda obj: getmodule(obj) in (mod, None))
    return dict((key, val) for key, val in members if not key.startswith("_"))


def callables_from_module(module):
    """
    Return all global-level callables defined in a module.

    Notes:
        Will ignore callables whose names start with underscore "_".
    """
    mod = mod_import(module)
    if not mod:
        return {}
    members = getmembers(mod, predicate=lambda obj: callable(obj) and getmodule(obj) == mod)
    return dict((key, val) for key, val in members if not key.startswith("_"))


def variable_from_module(module, variable=None, default=None):
    """
    Retrieve a variable or list of variables from a module.
    """
    if not module:
        return default
    mod = mod_import(module)
    if not mod:
        return default
    if variable:
        result = []
        for var in make_iter(variable):
            if var:
                result.append(mod.__dict__.get(var, default))
    else:
        result = [
            val for key, val in mod.__dict__.items() if not (key.startswith("_") or ismodule(val))
        ]
    if len(result) == 1:
        return result[0]
    return result


# --- End Evennia code ---


# --- Begin Evennia code (BSD 3-Clause) ---
# Atheriz-adapted version: simple m_len that uses east_asian_width directly,
# without depending on inherits_from or ANSIString.
def m_len(target):
    """
    Display-width length of a string, counting east-asian wide chars as 2.
    Falls back to len() for non-strings.
    """
    if isinstance(target, str):
        return sum(2 if east_asian_width(ch) in ("W", "F") else 1 for ch in target)
    return len(target)


# --- End Evennia code ---


# --- Begin Evennia code (BSD 3-Clause) ---
def pad(text, width=None, align="c", fillchar=" "):
    """
    Pads to a given width.
    """
    from atheriz.settings import CLIENT_DEFAULT_WIDTH
    width = width if width else CLIENT_DEFAULT_WIDTH
    align = align if align in ("c", "l", "r") else "c"
    fillchar = fillchar[0] if fillchar else " "
    if align == "l":
        return text.ljust(width, fillchar)
    elif align == "r":
        return text.rjust(width, fillchar)
    return text.center(width, fillchar)


def crop(text, width=None, suffix="[...]"):
    """
    Crop text to a certain width.
    """
    from atheriz.settings import CLIENT_DEFAULT_WIDTH
    width = width if width else CLIENT_DEFAULT_WIDTH
    ltext = len(text)
    if ltext <= width:
        return text
    lsuffix = len(suffix)
    if lsuffix >= width:
        return text[:width]
    return f"{text[: width - lsuffix]}{suffix}"


# --- End Evennia code ---


# --- Begin Evennia code (BSD 3-Clause) ---
# Simplified version of Evennia's justify that doesn't depend on ANSIString.
# Uses m_len for accurate width measurement.
def justify(text, width=None, align="l", indent=0, fillchar=" "):
    """
    Justify text to a width with alignment l/c/r/f.
    """
    from atheriz.settings import CLIENT_DEFAULT_WIDTH
    width = width if width is not None else CLIENT_DEFAULT_WIDTH
    sp = fillchar

    if align == "a":
        # absolute - just fill or crop
        abs_lines = []
        for line in text.split("\n"):
            nlen = m_len(line)
            if m_len(line) < width:
                line += sp * (width - nlen)
            else:
                line = crop(line, width=width, suffix="")
            abs_lines.append(line)
        return "\n".join(abs_lines)

    paragraphs = []
    paragraph_words = []
    for input_line in text.split("\n"):
        line_words = [(word, m_len(word)) for word in input_line.split()]
        if line_words:
            paragraph_words.extend(line_words)
        else:
            if paragraph_words:
                paragraphs.append(paragraph_words)
                paragraph_words = []
            paragraphs.append(None)
    if paragraph_words:
        paragraphs.append(paragraph_words)

    if not paragraphs:
        return sp * width

    def _process_line(line, line_word_length, line_gaps):
        line_rest = width - (line_word_length + line_gaps)
        gap = " "
        if line_rest > 0:
            if align == "l":
                if line and line[-1] == "\n\n":
                    line[-1] = sp * (line_rest - 1) + "\n" + sp * width + "\n" + sp * width
                else:
                    line[-1] += sp * line_rest
            elif align == "r":
                line[0] = sp * line_rest + line[0]
            elif align == "c":
                pad_amt = sp * (line_rest // 2)
                line[0] = pad_amt + line[0]
                if line and line[-1] == "\n\n":
                    line[-1] += pad_amt + sp * (line_rest % 2 - 1) + "\n" + sp * width + "\n" + sp * width
                else:
                    line[-1] = line[-1] + pad_amt + sp * (line_rest % 2)
            else:  # full
                gap += sp * (line_rest // max(1, line_gaps))
                rest_gap = line_rest % max(1, line_gaps)
                for i in range(rest_gap):
                    line[i % len(line)] += sp
        elif not any(line):
            return [sp * width]
        return gap.join(line)

    blank_line = sp * width
    lines = []
    for paragraph in paragraphs:
        if paragraph is None:
            lines.append(blank_line)
        else:
            ngaps = 0
            wlen = 0
            line = []
            paragraph_lines = []
            words = list(paragraph)
            while words:
                if not line:
                    word = words.pop(0)
                    wlen = word[1]
                    line.append(word[0])
                elif (words[0][1] + wlen + ngaps) >= width:
                    paragraph_lines.append(_process_line(line, wlen, ngaps))
                    ngaps, wlen, line = 0, 0, []
                else:
                    word = words.pop(0)
                    line.append(word[0])
                    wlen += word[1]
                    ngaps += 1
            if line:
                paragraph_lines.append(_process_line(line, wlen, ngaps))
            lines.extend(paragraph_lines)

    indentstring = sp * indent
    return "\n".join([indentstring + line for line in lines])


# --- End Evennia code ---


# --- Begin Evennia code (BSD 3-Clause) ---
_INT2STR_MAP_NOUN = {
    0: "no",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
}
_INT2STR_MAP_ADJ = {1: "1st", 2: "2nd", 3: "3rd"}


def int2str(number, adjective=False):
    """
    Convert a number to an English string for display.
    """
    number = int(number)
    if adjective:
        return _INT2STR_MAP_ADJ.get(number, f"{number}th")
    return _INT2STR_MAP_NOUN.get(number, str(number))


# --- End Evennia code ---


# --- Begin Evennia code (BSD 3-Clause) ---
# Atheriz-adapted: removed simple_eval dependency (not installed).
# Uses literal_eval as the only "py" converter, with a fallback simple_arith
# for basic arithmetic expressions (1+2, 3*4, etc.) on numbers.
def _safe_arith_eval(inp):
    """
    Safely evaluate arithmetic expressions on numeric literals only.
    Supports +, -, *, /, //, %, **, unary -, and parentheses.
    """
    import ast
    allowed_binops = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a ** b,
    }
    allowed_unaryops = {ast.UAdd: lambda a: +a, ast.USub: lambda a: -a}

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"non-numeric constant: {node.value!r}")
        if isinstance(node, ast.BinOp) and type(node.op) in allowed_binops:
            return allowed_binops[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in allowed_unaryops:
            return allowed_unaryops[type(node.op)](_eval(node.operand))
        raise ValueError(f"unsupported expression node: {type(node).__name__}")

    tree = ast.parse(inp, mode="eval")
    return _eval(tree)


def safe_convert_to_types(converters, *args, raise_errors=True, **kwargs):
    """
    Helper to safely convert inputs to expected data types.
    """
    container_end_char = {"(": ")", "[": "]", "{": "}"}

    def _manual_parse_containers(inp):
        startchar = inp[0]
        endchar = inp[-1]
        if endchar != container_end_char.get(startchar):
            return None
        return [str(part).strip() for part in inp[1:-1].split(",")]

    def _safe_eval(inp):
        if not inp:
            return ""
        if not isinstance(inp, str):
            return inp
        literal_err = ""
        try:
            return literal_eval(inp)
        except (ValueError, SyntaxError) as err:
            literal_err = f"{err.__class__.__name__}: {err}"
            try:
                return _safe_arith_eval(inp)
            except (ValueError, SyntaxError) as arith_err:
                parts = _manual_parse_containers(inp)
                if parts is not None:
                    return parts
                if raise_errors:
                    from atheriz.objects.funcparser import ParsingError
                    raise ParsingError(
                        f"Errors converting '{inp}' to python: "
                        f"literal_eval raised {literal_err}, "
                        f"arith_eval raised {arith_err}"
                    )
                return str(inp)

    if not converters:
        return args, kwargs
    arg_converters, *kwarg_converters = converters
    arg_converters = make_iter(arg_converters)
    kwarg_converters = kwarg_converters[0] if kwarg_converters else {}

    if args and arg_converters:
        args = list(args)
        arg_converters = make_iter(arg_converters)
        for iarg, arg in enumerate(args[: len(arg_converters)]):
            converter = arg_converters[iarg]
            converter = _safe_eval if converter in ("py", "python") else converter
            try:
                args[iarg] = converter(arg)
            except Exception:
                if raise_errors:
                    raise
        args = tuple(args)
    if kwarg_converters and isinstance(kwarg_converters, dict):
        for key, converter in kwarg_converters.items():
            converter = _safe_eval if converter in ("py", "python") else converter
            if key in kwargs:
                try:
                    kwargs[key] = converter(kwargs[key])
                except Exception:
                    if raise_errors:
                        raise
    return args, kwargs


# --- End Evennia code ---
