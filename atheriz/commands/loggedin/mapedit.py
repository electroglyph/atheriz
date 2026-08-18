from __future__ import annotations

from typing import TYPE_CHECKING

from atheriz.commands.base_cmd import Command
from atheriz.globals.get import get_map_handler
from atheriz.globals.map import MapInfo
import atheriz.globals.mapedit as mapedit

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class DrawCommand(Command):
    key = "mapedit"
    desc = "Open the AtheriZ map editor in a new browser tab."
    use_parser = False

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    # pyrefly: ignore
    def run(self, caller: Object, args):
        loc = caller.location
        if not loc:
            caller.msg("You must be in a valid location to open the map editor.")
            return
        conn = caller.session.connection
        area, z = loc.coord.area, loc.coord.z
        mh = get_map_handler()
        mi = mh.get_mapinfo(area, z)
        if not mi:
            mi = MapInfo(name=area)
            mh.set_mapinfo(area, z, mi)
        key = mapedit.grant(getattr(conn, "client_host", "?"), area, z)
        payload = {"area": area, "z": z, "grid": []}
        with mi.lock:
            for (x, y), symbol in mi.pre_grid.items():
                payload["grid"].append([x, y, symbol])
        conn.send_command("launch_draw", key, payload)
        caller.msg("Opening AtheriZ Draw in a new tab.")