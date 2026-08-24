"""Issue #63: BaseConnection.msg must not raise on non-str text or falsy text=."""
from __future__ import annotations

from atheriz.network.connection import BaseConnection


class ConcreteConn(BaseConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sent = []

    def send_command(self, cmd, *args, **kwargs):
        self.sent.append((cmd, args, kwargs))

    def close(self):
        pass


def test_msg_non_str_text_coerced(global_test_env):
    c = ConcreteConn()
    c.msg(123)  # AttributeError before fix
    cmd, args, _ = c.sent[0]
    assert cmd == "text"
    assert args[0] == "123\r\n"


def test_msg_falsy_text_kwarg_no_crash(global_test_env):
    c = ConcreteConn()
    c.msg(text="")  # KeyError from popitem() on empty dict before fix
