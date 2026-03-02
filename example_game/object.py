from atheriz.objects.base_obj import Object as BaseObject
from .flags import Flags
from .db_ops import DbOps
from .access import AccessLock


class Object(BaseObject, Flags, DbOps, AccessLock):
    """Custom Object class. Override methods below to customize behavior."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def at_alarm(self, *args, **kwargs):
        return super().at_alarm(*args, **kwargs)

    def at_create(self, *args, **kwargs):
        return super().at_create(*args, **kwargs)

    def at_delete(self, *args, **kwargs):
        return super().at_delete(*args, **kwargs)

    def at_desc(self, *args, **kwargs):
        return super().at_desc(*args, **kwargs)

    def at_disconnect(self, *args, **kwargs):
        return super().at_disconnect(*args, **kwargs)

    def at_drop(self, *args, **kwargs):
        return super().at_drop(*args, **kwargs)

    def at_get(self, *args, **kwargs):
        return super().at_get(*args, **kwargs)

    def at_give(self, *args, **kwargs):
        return super().at_give(*args, **kwargs)

    def at_init(self, *args, **kwargs):
        return super().at_init(*args, **kwargs)

    def at_legend_update(self, *args, **kwargs):
        return super().at_legend_update(*args, **kwargs)

    def at_look(self, *args, **kwargs):
        return super().at_look(*args, **kwargs)

    def at_lunar_event(self, *args, **kwargs):
        return super().at_lunar_event(*args, **kwargs)

    def at_map_update(self, *args, **kwargs):
        return super().at_map_update(*args, **kwargs)

    def at_msg_receive(self, *args, **kwargs):
        return super().at_msg_receive(*args, **kwargs)

    def at_msg_send(self, *args, **kwargs):
        return super().at_msg_send(*args, **kwargs)

    def at_post_move(self, *args, **kwargs):
        return super().at_post_move(*args, **kwargs)

    def at_post_puppet(self, *args, **kwargs):
        return super().at_post_puppet(*args, **kwargs)

    def at_pre_drop(self, *args, **kwargs):
        return super().at_pre_drop(*args, **kwargs)

    def at_pre_get(self, *args, **kwargs):
        return super().at_pre_get(*args, **kwargs)

    def at_pre_give(self, *args, **kwargs):
        return super().at_pre_give(*args, **kwargs)

    def at_pre_map_render(self, *args, **kwargs):
        return super().at_pre_map_render(*args, **kwargs)

    def at_pre_move(self, *args, **kwargs):
        return super().at_pre_move(*args, **kwargs)

    def at_pre_say(self, *args, **kwargs):
        return super().at_pre_say(*args, **kwargs)

    def at_say(self, *args, **kwargs):
        return super().at_say(*args, **kwargs)

    def at_solar_event(self, *args, **kwargs):
        return super().at_solar_event(*args, **kwargs)

    def at_tick(self, *args, **kwargs):
        return super().at_tick(*args, **kwargs)

    def format_appearance(self, appearance, looker, **kwargs):
        return super().format_appearance(appearance, looker, **kwargs)
