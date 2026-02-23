class Flags:
    def __init__(self):
        # skip thread-safety patch
        object.__setattr__(self, "is_pc", False)
        object.__setattr__(self, "is_npc", False)
        object.__setattr__(self, "is_item", False)
        object.__setattr__(self, "is_mapable", False)
        object.__setattr__(self, "is_container", False)
        object.__setattr__(self, "is_script", False)
        object.__setattr__(self, "_is_tickable", False)
        object.__setattr__(self, "is_account", False)
        object.__setattr__(self, "is_channel", False)
        object.__setattr__(self, "is_node", False)
        object.__setattr__(self, "is_modified", True)
        object.__setattr__(self, "is_deleted", False)
        object.__setattr__(self, "is_connected", False)
        super().__init__()

        
    @property
    def is_tickable(self):
        return self._is_tickable