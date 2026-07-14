from __future__ import annotations
from typing import TYPE_CHECKING, Callable, Any

from atheriz.settings import MAX_SEARCH_DEPTH

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node


def filter_visible(obj_list: list[Object], looker: Object | None = None) -> list[Object]:
    """Filter objects by visibility.

    Args:
        obj_list (list[Object]): The objects to filter.
        looker (Object | None): The object doing the looking.

    Returns:
        list[Object]: The filtered list of objects.
    """
    return (
        [obj for obj in obj_list if obj != looker and obj.access(looker, "view")]
        if looker
        else obj_list
    )


def group_by_name(objs: list[Object], looker: Object | None = None) -> str:
    """Group objects by name.

    Args:
        objs (list[Object]): The objects to group.

    Returns:
        str: The grouped objects.
    """
    if not objs:
        return ""
    groups = {}
    for o in objs:
        name = o.get_display_name(looker) if looker else o.name
        count = groups.get(name, 0)
        if count == 0:
            groups[name] = 1
        else:
            groups[name] = count + 1
    return ", ".join([f"{name}({count})" if count > 1 else name for name, count in groups.items()])


def filter_contents(obj: Object | Node, l: Callable[[Any], bool]) -> list[Any]:
    """Filter objects by a lambda.

    For example:
    ```python
    filter_contents(obj, lambda x: x.is_pc)
    ```

    Args:
        obj (Object | Node): The object to filter.
        l (Callable[[Any], bool]): The lambda to use for filtering.

    Returns:
        list[Any]: The list of objects that match the search criteria.
    """
    return [o for o in obj.contents if l(o)]


def _gather_contents(obj: Object | Node, visited: set[int] | None = None, depth: int = 0) -> list[Any]:
    """Recursively gather obj's contents, descending into children with ``is_container``.

    Args:
        obj (Object | Node): The root object to gather from.
        visited (set[int] | None): Accumulating set of already-seen object ids.
        depth (int): Current recursion depth; capped at MAX_SEARCH_DEPTH.

    Returns:
        list[Any]: Flat list of nested contents, top-level first. May be partial if the
            depth limit or a RecursionError halted descent.
    """
    if visited is None:
        visited = set()
    if depth >= MAX_SEARCH_DEPTH:
        return []
    result = []
    for o in obj.contents:
        if o.id in visited:
            continue
        visited.add(o.id)
        result.append(o)
        if getattr(o, "is_container", False):
            try:
                result.extend(_gather_contents(o, visited, depth + 1))
            except RecursionError:
                break
    return result


def search(obj: Object | Node, query: str, recursive: bool = True) -> list[Any]:
    """
    search for matching objects
    example queries:

    'sword' = return first item matching this query,
    'sword 2' = return second item matching 'sword',
    'swords' = return all items matching 'sword',
    'all sword' = same as previous,
    '2 sword' = return first two items matching 'sword'

    Args:
        query (str): search query
        recursive (bool): If True (default), descend into nested containers
            (children with ``is_container``). If False, search only ``obj``'s
            direct contents.
    """
    query = query.lower()
    if query == "me" or query == obj.name.lower():
        return [obj]
    # ponytail: computed once so the #id branch and the match loop share one candidate list
    objs = _gather_contents(obj) if recursive else obj.contents
    if query.startswith("#"):
        try:
            id = int(query[1:])
        except ValueError:
            return []
        for o in objs:
            if o.id == id:
                return [o]
        return []

    # split up query into required and optional terms
    # all required terms must be found for a match, or any of the optional terms
    optional = []
    required = []
    count = 1
    index = 0
    split = query.split(" ")
    start = 0
    end = len(split)
    if split[0] == "all":
        count = 0
        start = 1
    elif split[0].isnumeric():
        count = int(split[0])
        start = 1
    if split[-1].isnumeric():
        index = int(split[-1])
        if index < 1:  # invalid index
            return []
        end -= 1
    for x in range(start, end, 1):
        # try to detect sane plurals, doesn't include stuff like ellipses -> ellipsis, or criteria -> criterion, or geese -> goose, etc.
        # if you wanna match on those, add em to yer aliases
        if len(split[x]) > 3 and split[x].endswith("ies"):  # cities -> city
            if count == 1:
                count = 0  # 0 is placeholder value for 'all'
            required.append(split[x][:-3] + "y")
            optional.append(split[x])
        elif len(split[x]) > 2 and split[x].endswith("es"):  # tomatoes -> tomato
            if count == 1:
                count = 0
            optional.append(split[x][:-2])  # crat / tomato
            optional.append(split[x][:-1])  # crate / tomatoe
            optional.append(split[x])  # crates / tomatoes
        elif len(split[x]) > 1 and split[x].endswith("s"):  # photos -> photo
            if count == 1:
                count = 0
            required.append(split[x][:-1])
            optional.append(split[x])
        elif len(split[x]) > 1 and split[x].endswith("i"):  # cacti -> cactus
            if count == 1:
                count = 0
            required.append(split[x][:-1] + "us")
            optional.append(split[x])
        else:
            required.append(split[x])
    matches = []
    for x in range(len(objs)):
        found = False
        for s in required:
            if s in "".join(objs[x].aliases) + "".join(objs[x].name.lower()):
                found = True
            else:
                found = False
                break
        if found:
            if count == 1 and index == 0:
                return [objs[x]]
            else:
                matches.append(objs[x])
                if len(matches) == count and index == 0:
                    return matches
        for s in optional:
            if s in "".join(objs[x].aliases) + "".join(objs[x].name.lower()):
                if count == 1 and index == 0:
                    return [objs[x]]
                else:
                    matches.append(objs[x])
                    if len(matches) == count and index == 0:
                        return matches
    if count == 0:  # 0 means all
        return matches
    if index == 0 and len(matches) > count:  # we have more matches than requested
        return matches[:count]
    if index != 0 and index <= len(matches):  # specific match index was requested
        return [matches[index - 1]]
    elif index != 0 and index > len(matches):  # match not found
        return []
    return matches  # count >= matches
