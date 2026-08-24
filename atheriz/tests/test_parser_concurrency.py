"""Pinned tests for 5.6 — Command.parser lazy init must be thread-safe.

INTENT: `Command.parser` is lazily created on first access (`if _parser is None:
_parser = GameArgumentParser(); setup_parser()`). Without a lock, 8 threads
hitting `cmd.parser` at once could see a half-initialized parser or call
`setup_parser` twice, and `parse_args` (argparse) is not thread-safe for
concurrent calls on the same parser. `Barrier(2)` forces the race.
"""
from __future__ import annotations

import threading
from unittest.mock import Mock

from atheriz.commands.base_cmd import Command


class CounterCommand(Command):
    key = "counter"
    desc = "counter test"

    def __init__(self):
        super().__init__()
        self.setup_calls = 0

    def setup_parser(self):
        self.setup_calls += 1
        self.parser.add_argument("target", help="target")


class EchoCommand(Command):
    key = "echo"
    desc = "echo test"

    def setup_parser(self):
        self.parser.add_argument("--verbose", action="store_true")
        self.parser.add_argument("msg", nargs="?", default="")


def test_parser_init_threadsafe():
    """8 threads `cmd.parser` via Barrier — only one `setup_parser` and parser has arg."""
    cmd = CounterCommand()
    # ensure fresh
    assert cmd._parser is None
    barrier = threading.Barrier(8, timeout=5)
    parsers: list = []
    errors: list[str] = []

    def worker():
        try:
            barrier.wait(timeout=5)
            p = cmd.parser
            parsers.append(p)
        except Exception as e:
            errors.append(f"{e!r}")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors, f"errors: {errors}"
    assert len(parsers) == 8
    # all see same parser object (double-checked locking) or at least equivalent
    assert all(p is parsers[0] for p in parsers), "parsers diverged"
    # setup_parser called exactly once (first init)
    assert cmd.setup_calls == 1, f"setup_parser called {cmd.setup_calls} times"
    # parser has target arg
    assert any(a.dest == "target" for a in parsers[0]._actions)


def test_parse_args_concurrent():
    """8 threads `execute` via Barrier — no crash, each gets correct parse."""
    cmd = EchoCommand()
    # force parser init single-threaded first to isolate parse_args race
    _ = cmd.parser
    barrier = threading.Barrier(8, timeout=5)
    results: list[tuple] = []
    errors: list[str] = []

    def worker(idx: int):
        try:
            caller = Mock()
            caller.msg = Mock()
            barrier.wait(timeout=5)
            # each uses distinct arg string to avoid caching
            run, c, args = cmd.execute(caller, f"hello{idx} --verbose" if idx % 2 == 0 else f"hello{idx}")
            results.append((run, args))
        except Exception as e:
            errors.append(f"{e!r}")
            import traceback
            errors.append(traceback.format_exc())

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors, f"errors: {errors}"
    assert len(results) == 8
    for run, args in results:
        assert callable(run)
        assert hasattr(args, "msg")
        assert args.msg.startswith("hello")


def test_parser_pickle_excludes_lock():
    """_parser_lock must not be pickled (threading.Lock not pickleable)."""
    import pickle

    cmd = EchoCommand()
    _ = cmd.parser
    blob = pickle.dumps(cmd)
    cmd2 = pickle.loads(blob)
    # after unpickle, parser works and lock exists
    assert hasattr(cmd2, "_parser_lock")
    assert cmd2.parser is not None
    # execute still works
    caller = Mock()
    caller.msg = Mock()
    run, _, args = cmd2.execute(caller, "hi --verbose")
    assert args.verbose is True
    assert args.msg == "hi"
