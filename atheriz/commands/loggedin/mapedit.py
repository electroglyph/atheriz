from __future__ import annotations

from typing import TYPE_CHECKING

from atheriz.commands.base_cmd import Command
from atheriz.globals.get import get_map_handler, get_node_handler
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
        payload = {"area": area, "z": z, "grid": [], "rooms": []}
        if mi.pre_grid:
            mi.pre_render()
        with mi.lock:
            grid = list(mi.post_grid.items())
        area_obj = get_node_handler().get_area(area)
        node_grid = area_obj.get_grid(z) if area_obj else None
        for (x, y), symbol in grid:
            payload["grid"].append([x, y, symbol])
            if not node_grid:
                continue
            node = node_grid.get_node((x, y))
            if not node:
                continue
            exits = []
            for link in node.get_links():
                if link.coord is None:
                    continue
                exits.append(
                    {
                        "name": link.name,
                        "aliases": link.aliases,
                        "coord": [link.coord.area, link.coord.x, link.coord.y, link.coord.z],
                    }
                )
            payload["rooms"].append({"x": x, "y": y, "desc": node.desc, "exits": exits})
        conn.send_command("launch_draw", key, payload)
        caller.msg("Opening AtheriZ Draw in a new tab.")