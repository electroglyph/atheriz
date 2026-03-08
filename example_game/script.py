from atheriz.objects.base_script import Script as BaseScript, before, after, replace
from .flags import Flags
from .db_ops import DbOps


class Script(BaseScript, Flags, DbOps):
    """Custom Script class. Override methods below to customize behavior."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def at_install(self):
        """Called when the script is assigned to and installed on an object."""
        pass
