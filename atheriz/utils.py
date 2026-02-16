import importlib
import re
from random import randint
from string import punctuation
import colorsys
import math
from typing import TYPE_CHECKING
from atheriz.singletons.get import get_websocket_manager
if TYPE_CHECKING:
    from atheriz.objects.nodes import Node, NodeLink

_ANSI_COLOR = r"\x1b\[[0-9;]+m"
_COLOR_REGEX = re.compile(_ANSI_COLOR)


def msg_all(msg: str) -> None:
    """
    send message to all connected clients

    Args:
        msg (str): message to send
    """
    get_websocket_manager().broadcast(msg)

def ensure_thread_safe(obj):
    """Patches the class of the provided object if not already patched."""
    cls = obj.__class__

    # only patch once
    if getattr(cls, "_is_thread_safe", False):
        return

    orig_get = object.__getattribute__
    orig_set = object.__setattr__

    def __getattribute__(self, name):
        # always allow access to the lock itself and other essentials
        if name in ("lock", "__dict__", "__class__", "__setstate__", "__getstate__"):
            return orig_get(self, name)
        
        lock = orig_get(self, "lock")

        with lock:
            return orig_get(self, name)

    def __setattr__(self, name, value):
        if name == "lock":
            orig_set(self, name, value)
        else:
            with orig_get(self, "lock"):
                orig_set(self, name, value)

    cls.__getattribute__ = __getattribute__
    cls.__setattr__ = __setattr__
    cls._is_thread_safe = True


def tuple_to_str(t: tuple) -> str:
    return repr(t)


def str_to_tuple(s: str) -> tuple:
    import ast

    return ast.literal_eval(s)


def instance_from_string(class_path_string, *args, **kwargs):
    """dynamically import a class and instantiate it with given arguments

    Args:
        class_path_string (str): the full import path to the class (e.g., 'package.module.ClassName')

    Returns:
        object: an instance of the specified class
    """
    module_name, _, class_name = class_path_string.rpartition(".")
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    instance = cls(*args, **kwargs)
    return instance


def get_import_path(obj: object) -> str:
    return obj.__module__ + "." + obj.__class__.__name__


def wrap_xterm256(
    input: str,
    fg=None,
    bg=None,
    bold=False,
    italic=False,
    underline=False,
    inverse=False,
    strikethru=False,
    clear=False,
) -> str:
    """
    colorize input string with ANSI xterm256 color and append a color reset code to the end

    Args:
        input (str): input string
        fg (int, optional): xterm256 foreground color. Defaults to None.
        bg (int, optional): xterm256 background color. Defaults to None.
        bold (bool, optional): bold? Defaults to False.
        italic (bool, optional): italic? Defaults to False.
        underline (bool, optional): underline? Defaults to False.
        inverse (bool, optional): inverse? Defaults to False.
        strikethru (bool, optional): strikethrough? Defaults to False.
        clear (bool, optional): strip existing ANSI color from input. Defaults to False.

    Returns:
        str: colorized string with color reset at the end
    """
    if clear:
        input = strip_ansi(input)
    if fg is not None:
        input = f"\x1b[38;5;{fg}m{input}"
    if bg is not None:
        input = f"\x1b[48;5;{bg}m{input}"
    if bold:
        input = f"\x1b[1m{input}"
    if italic:
        input = f"\x1b[3m{input}"
    if underline:
        input = f"\x1b[4m{input}"
    if inverse:
        input = f"\x1b[7m{input}"
    if strikethru:
        input = f"\x1b[9m{input}"
    return f"{input}\x1b[0m"


def wrap_truecolor(
    input: str,
    fg=None,
    bg=0.0,
    fg_bright=100.0,
    fg_sat=100.0,
    bg_bright=100.0,
    bg_sat=100.0,
    bold=False,
    italic=False,
    underline=False,
    inverse=False,
    strikethru=False,
    clear=False,
) -> str:
    """
    colorize input string with ANSI xterm256 color and append a color reset code to the end

    Args:
        input (str): input string
        fg (float, optional): foreground color where 120.0 = green. Defaults to None.
        bg (float, optional): background color where 120.0 = green. Defaults to None.
        fg_bright (float, optional): foreground brightness where 100.0 = maximum. Defaults to 100.0.
        fg_sat (float, optional): foreground saturation where 100.0 = maximum. Defaults to 100.0.
        bg_bright (float, optional): background brightness where 100.0 = maximum. Defaults to 100.0.
        bg_sat (float, optional): background saturation where 100.0 = maximum. Defaults to 100.0.
        bold (bool, optional): bold? Defaults to False.
        italic (bool, optional): italic? Defaults to False.
        underline (bool, optional): underline? Defaults to False.
        inverse (bool, optional): inverse? Defaults to False.
        strikethru (bool, optional): strikethrough? Defaults to False.
        clear (bool, optional): strip existing ANSI color from input. Defaults to False.

    Returns:
        str: colorized string with color reset at the end
    """
    if clear:
        input = strip_ansi(input)
    if bg is not None and bg != 0.0:
        bg /= 360.0
        if bg_bright != 0.0:
            bg_bright /= 100.0
        if bg_sat != 0.0:
            bg_sat /= 100.0
        r, g, b = tuple(round(i * 255) for i in colorsys.hsv_to_rgb(bg, bg_sat, bg_bright))
        input = f"\x1b[48;2;{r};{g};{b}m{input}"
    else:
        input = f"\x1b[48;2;0;0;0m{input}"
    if fg is not None and fg != 0.0:
        fg /= 360.0
        if fg_bright != 0.0:
            fg_bright /= 100.0
        if fg_sat != 0.0:
            fg_sat /= 100.0
        r, g, b = tuple(round(i * 255) for i in colorsys.hsv_to_rgb(fg, fg_sat, fg_bright))
        input = f"\x1b[38;2;{r};{g};{b}m{input}"
    else:
        r, g, b = tuple(round(i * 255) for i in colorsys.hsv_to_rgb(1.0, 0.0, 1.0))
        input = f"\x1b[38;2;{r};{g};{b}m{input}"
    if bold:
        input = f"\x1b[1m{input}"
    if italic:
        input = f"\x1b[3m{input}"
    if underline:
        input = f"\x1b[4m{input}"
    if inverse:
        input = f"\x1b[7m{input}"
    if strikethru:
        input = f"\x1b[9m{input}"
    return f"{input}\x1b[0m"


def strip_ansi(input: str) -> str:
    return _COLOR_REGEX.sub("", input)


def dice_roll(rolls: int, faces: int):
    result = 0
    for _ in range(rolls):
        result += randint(1, faces)
    return result


def dice_roll_average(rolls: int, faces: int):
    return rolls * ((faces + 1) / 2)


def clamp(minimum, value, maximum):
    return max(min(maximum, value), minimum)


def get_dir(origin: tuple, dest: tuple) -> str:
    """
    get map direction between two points. (0,0) is lower left.
    returns '' if origin == dest
    """
    ns_vec = abs(origin[1] - dest[1])
    if origin[1] > dest[1]:
        ns_vec *= -1
    ew_vec = abs(origin[0] - dest[0])
    if origin[0] > dest[0]:
        ew_vec *= -1
    dir = ""
    if ns_vec > 0:
        dir = "north"
    elif ns_vec < 0:
        dir = "south"
    if ew_vec > 0:
        dir += "east"
    elif ew_vec < 0:
        dir += "west"
    return dir


def dist_3d(origin: tuple, dest: tuple) -> float:
    if len(origin) == len(dest) == 3:
        return math.hypot(origin[0] - dest[0], origin[1] - dest[1], origin[2] - dest[2])
    # tuple of (str, x, y, z) (standard room coord)
    return math.hypot(origin[1] - dest[1], origin[2] - dest[2], origin[3] - dest[3])


def get_reverse_link(location: Node, destination: Node) -> NodeLink | None:
    links = destination.links
    if not links:
        return None
    for link in links:
        if link.coord == location.coord:
            return link
    return None


# everything below here is from Evennia (https://github.com/evennia/evennia)
# see EVENNIA_LICENSE.txt for license (BSD-3-Clause)

re_empty = re.compile("\n\\s*\n")


def compress_whitespace(text: str, max_linebreaks: int = 1, max_spacing: int = 2) -> str:
    """
    Removes extra sequential whitespace in a block of text. This will also remove any trailing
    whitespace at the end.

    Args:
        text (str):   A string which may contain excess internal whitespace.

    Keyword args:
        max_linebreaks (int):  How many linebreak characters are allowed to occur in a row.
        max_spacing (int):     How many spaces are allowed to occur in a row.

    """
    text = text.rstrip()
    # replaces any non-visible lines that are just whitespace characters with actual empty lines
    # this allows the blank-line compression to eliminate them if needed
    text = re_empty.sub("\n\n", text)
    # replace groups of extra spaces with the maximum number of spaces
    text = re.sub(rf"(?<=\S) {{{max_spacing},}}", " " * max_spacing, text)
    # replace groups of extra newlines with the maximum number of newlines
    text = re.sub(f"\n{{{max_linebreaks},}}", "\n" * max_linebreaks, text)
    return text


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

    Args:
        obj (any): Object to make iterable.

    Returns:
        iterable (list or iterable): The same object
            passed-through or made iterable.

    """
    return not is_iter(obj) and [obj] or obj


def copy_word_case(base_word, new_word):
    """
    Converts a word to use the same capitalization as a first word.

    Args:
        base_word (str): A word to get the capitalization from.
        new_word (str): A new word to capitalize in the same way as `base_word`.

    Returns:
        str: The `new_word` with capitalization matching the first word.

    Notes:
        This is meant for words. Longer sentences may get unexpected results.

        If the two words have a mix of capital/lower letters _and_ `new_word`
        is longer than `base_word`, the excess will retain its original case.

    """

    # Word
    if base_word.istitle():
        return new_word.title()
    # word
    elif base_word.islower():
        return new_word.lower()
    # WORD
    elif base_word.isupper():
        return new_word.upper()
    else:
        # WorD - a mix. Handle each character
        maxlen = len(base_word)
        shared, excess = new_word[:maxlen], new_word[maxlen - 1 :]
        return (
            "".join(
                char.upper() if base_word[ic].isupper() else char.lower()
                for ic, char in enumerate(new_word)
            )
            + excess
        )


def iter_to_str(iterable, sep=",", endsep=", and", addquote=False):
    """
    This pretty-formats an iterable list as string output, adding an optional
    alternative separator to the second to last entry.  If `addquote`
    is `True`, the outgoing strings will be surrounded by quotes.

    Args:
        iterable (any): Usually an iterable to print. Each element must be possible to
            present with a string. Note that if this is a generator, it will be
            consumed by this operation.
        sep (str, optional): The string to use as a separator for each item in the iterable.
        endsep (str, optional): The last item separator will be replaced with this value.
        addquote (bool, optional): This will surround all outgoing
            values with double quotes.

    Returns:
        str: The list represented as a string.

    Notes:
        Default is to use 'Oxford comma', like 1, 2, 3, and 4.

    Examples:

        ```python
        >>> iter_to_string([1,2,3], endsep=',')
        '1, 2, 3'
        >>> iter_to_string([1,2,3], endsep='')
        '1, 2 3'
        >>> iter_to_string([1,2,3], ensdep='and')
        '1, 2 and 3'
        >>> iter_to_string([1,2,3], sep=';', endsep=';')
        '1; 2; 3'
        >>> iter_to_string([1,2,3], addquote=True)
        '"1", "2", and "3"'
        ```

    """
    iterable = list(make_iter(iterable))
    if not iterable:
        return ""
    len_iter = len(iterable)

    if addquote:
        iterable = tuple(f'"{val}"' for val in iterable)
    else:
        iterable = tuple(str(val) for val in iterable)

    if endsep:
        if endsep.startswith(sep) and endsep != sep:
            # oxford comma alternative
            endsep = endsep[1:] if len_iter < 3 else endsep
        elif endsep[0] not in punctuation:
            # add a leading space if endsep is a word
            endsep = " " + str(endsep).strip()

    # also add a leading space if separator is a word
    if sep not in punctuation:
        sep = " " + sep

    if len_iter == 1:
        return str(iterable[0])
    elif len_iter == 2:
        return f"{endsep} ".join(str(v) for v in iterable)
    else:
        return f"{sep} ".join(str(v) for v in iterable[:-1]) + f"{endsep} {iterable[-1]}"
