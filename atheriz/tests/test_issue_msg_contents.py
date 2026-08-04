"""Issue tests: msg_contents raises KeyError when the message contains a
`{placeholder}` that has no matching mapping key.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atheriz.globals.objects import add_object
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node
from atheriz.utils import Coord


class TestMsgContentsMissingKey:
    def test_unmapped_placeholder_does_not_crash(self, global_test_env):
        """INTENT: a room message with an unmapped `{placeholder}` must not
        crash with KeyError from str.format_map. The message should be
        delivered with the placeholder left as-is (or stripped)."""
        node = Node(coord=Coord("test", 0, 0, 0))
        add_object(node)

        receiver = Object.create(None, "listener")
        receiver.msg = MagicMock()
        receiver.location = node
        node.add_object(receiver)

        node.msg_contents("hi {foo}")

        receiver.msg.assert_called_once()

    def test_mapped_placeholder_is_replaced(self, global_test_env):
        """Sanity: a mapped placeholder is substituted per-recipient."""
        node = Node(coord=Coord("test", 0, 0, 0))
        add_object(node)

        speaker = Object.create(None, "speaker", is_pc=True)
        receiver = Object.create(None, "listener")
        receiver.msg = MagicMock()
        receiver.location = node
        node.add_object(speaker)
        node.add_object(receiver)

        node.msg_contents("hi {target}", mapping={"target": speaker})
        sent = receiver.msg.call_args.kwargs["text"]
        assert "speaker" in sent
