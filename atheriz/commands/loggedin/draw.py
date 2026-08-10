from __future__ import annotations

from typing import TYPE_CHECKING

from atheriz.commands.base_cmd import Command

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class DrawCommand(Command):
    key = "draw"
    desc = "Open the AtheriZ Draw editor in a new browser tab."
    use_parser = False

    # pyrefly: ignore
    def run(self, caller: Object, args):
        caller.session.connection.launch_draw()
        caller.msg("Opening AtheriZ Draw in a new tab.")
