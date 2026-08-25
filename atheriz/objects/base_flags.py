from __future__ import annotations

FLAG_DEFAULTS: dict[str, object] = {
    "is_pc": False,
    "is_npc": False,
    "is_item": False,
    "is_mapable": False,
    "is_container": False,
    "is_script": False,
    "_is_tickable": False,
    "is_account": False,
    "is_channel": False,
    "is_node": False,
    "is_modified": True,
    "is_deleted": False,
    "is_connected": False,
    "is_temporary": False,
    "is_banned": False,
    "can_hear": False,
    "tags": set,
}

class Flags:
    def __init__(self):
        for name, default in FLAG_DEFAULTS.items():
            value = default() if name == "tags" else default
            object.__setattr__(self, name, value)
        super().__init__()

        
    @property
    def is_tickable(self):
        return self._is_tickable
    
    def add_tag(self, tag: str | list[str] | set[str]) -> None:
        """Add one or more tags to this object.

        Args:
            tag (str | list[str] | set[str]): A single tag string, or a list/set of tag strings.
        """
        tags = {tag} if isinstance(tag, str) else set(tag)
        with self.lock:
            self.tags.update(tags)
            self.is_modified = True

    def remove_tag(self, tag: str | list[str] | set[str]) -> None:
        """Remove one or more tags from this object. Missing tags are silently ignored.

        Args:
            tag (str | list[str] | set[str]): A single tag string, or a list/set of tag strings.
        """
        tags = {tag} if isinstance(tag, str) else set(tag)
        with self.lock:
            self.tags.difference_update(tags)
            self.is_modified = True

    def has_tag(self, tag: str | list[str] | set[str], all: bool = False) -> bool:
        """Check whether this object carries the given tags.

        By default, when multiple tags are supplied the check is an ANY match — returns
        ``True`` if at least one of the given tags is present.
        If `all` is set to True, returns ``True`` only if ALL given tags are present.

        Args:
            tag (str | list[str] | set[str]): A single tag string, or a list/set of tag strings.
            all (bool, optional): If True, require all tags to be present. Defaults to False.

        Returns:
            bool: True if the tag conditions are met on this object.
        """
        tags = {tag} if isinstance(tag, str) else set(tag)
        with self.lock:
            if all:
                return tags.issubset(self.tags)
            return bool(tags & self.tags)