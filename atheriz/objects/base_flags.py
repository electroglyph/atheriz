from __future__ import annotations
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
        object.__setattr__(self, "is_temporary", False)
        object.__setattr__(self, "can_hear", False)
        object.__setattr__(self, "tags", set())
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