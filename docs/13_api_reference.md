# 13 API Reference

[Table of Contents](./table_of_contents.md)

This document provides an auto-generated reference for the public classes, methods, and functions within Atheriz.

## 13.1 `atheriz.objects.base_obj`

### Class: `Object`

#### `def create(cls, caller, name, desc, aliases, is_pc, is_item, is_npc, is_mapable, is_container, is_tickable, tick_seconds)`

Create a new object.

Args:
    caller (Object | None): The object executing the creation.
    name (str): The name of the object.
    is_pc (bool, optional): Whether the object is a player character. Defaults to False.
    is_item (bool, optional): Whether the object is an item. Defaults to False.
    is_npc (bool, optional): Whether the object is an NPC. Defaults to False.
    is_mapable (bool, optional): Whether the object is mapable. Defaults to False.
    is_container (bool, optional): Whether the object is a container. Defaults to False.
    is_tickable (bool, optional): Whether the object is tickable. Defaults to False.

Returns:
    Self: The created object.



#### `def add_script(self, script)`

Attaches a Script object to this Object, installing any defined hooks.

Args:
    script (Script | int): The Script object or global ID to attach.



#### `def remove_script(self, script)`

Detaches a Script object from this Object, removing any associated hooks.

Args:
    script (Script | int): The Script object or global ID to remove.



#### `def has_script_type(self, script_type)`

Check if this object has a script of the given type.
It checks the class name of all the attached scripts.

Args:
    script_type (str): Class name of the script to check for, can be partial, case-insensitive.

Returns:
    bool: True if the object has a script of the given type, False otherwise.



#### `def delete(self, caller, recursive)`

Delete this object. If recursive, delete contents recursively.
If not, move contents to container location.

Args:
    recursive (bool, optional): Delete contents recursively. Defaults to True.

Returns:
    list[tuple[str, tuple]] | None: A list of SQL operations to execute, or None if deletion was aborted.



#### `def at_solar_event(self, msg)`

Called when a solar event occurs (e.g., sunrise or sunset).
Receives messages targeted at objects satisfying the `SOLAR_RECEIVER_LAMBDA`.

Args:
    msg (str): The descriptive message of the event.



#### `def at_lunar_event(self, msg)`

Called when a lunar event occurs (e.g., full moon phase changes).
Receives messages targeted at objects satisfying the `LUNAR_RECEIVER_LAMBDA`.

Args:
    msg (str): The descriptive message of the event.



#### `def at_delete(self, caller)`

Called before an object is deleted, aborts deletion if False.

Args:
    caller (Object): The object attempting to trigger the deletion.

Returns:
    bool: True if deletion should proceed, False to abort.



#### `def at_create(self)`

Called after an object is newly created and initialized via `Object.create()`.
Useful for setting initial variables, inventory generation, or database linkage.



#### `def resolve_relations(self)`

Called as pass 2 of the database load to reconnect relational IDs to actual objects.
This reconstitutes pointers like `location` and `home` from their integer IDs,
and reschedules any async ticker events or script hooks.



#### `@property def tick_seconds(self)`

float: The interval in seconds at which `at_tick` is called.



#### `@tick_seconds.setter def tick_seconds(self, value)`



#### `@property def is_tickable(self)`

bool: Indicates if this object is currently registered with the asynchronous ticker.



#### `@is_tickable.setter def is_tickable(self, value)`



#### `@property def seconds_played(self)`

float: The total accumulated playtime in seconds for this character/object.



#### `@seconds_played.setter def seconds_played(self, value)`



#### `def at_init(self)`

Called after this object is deserialized and all attributes are set.



#### `def at_tick(self)`

Called every tick.



#### `def at_alarm(self, time, data)`

Called when an alarm goes off. See time.py for time format.



#### `def at_disconnect(self)`

Called when the client connected to this object drops the WebSocket connection.
Handles internal state updates and optionally triggers an auto-save.



#### `def subscribe(self, channel)`

Subscribe to a channel.



#### `def unsubscribe(self, channel)`

Unsubscribe from a channel.



#### `def search(self, query)`

Search for an object by name or alias inside the contents of this object,
and within the room this object is standing in.

Args:
    query (str): The search string to evaluate.

Returns:
    list[Object]: A list of objects matching the query.



#### `def at_legend_update(self, legend, show_legend, area)`

Sends map legend updates directly to the connected client.

Args:
    legend (list[tuple[str, str, tuple[int, int]]]): Parsed legend data format.
    show_legend (bool, optional): Whether the legend pane should be rendered. Defaults to True.
    area (str, optional): The geographic name of the map area. Defaults to "Somewhere".



#### `def at_map_update(self, map, legend, min_x, max_y, show_legend, area)`



#### `def at_pre_map_render(self, grid)`

to modify map before it's been rendered for this character
mapables and legend entries with coords will be placed over this map



#### `def add_objects(self, objs)`

Add multiple objects to this object's internal inventory.

Args:
    objs (list[Object]): A list of objects to add.



#### `def add_object(self, obj)`

Add a single object to this object's internal inventory.

Args:
    obj (Object): The object to add.



#### `def remove_object(self, obj)`

Remove a single object from this object's internal inventory.

Args:
    obj (Object): The object to remove.



#### `@property def contents(self)`

list[Object]: The list of objects currently stored within this object.



#### `@property def is_superuser(self)`

bool: Indicates if this object possesses superuser administrative rights.



#### `@property def is_builder(self)`

bool: Indicates if this object possesses builder world-editing rights.



#### `def execute_cmd(self, raw_string, session, **kwargs)`

Mock compatibility method simulating executing a command directly as this object.
Currently unimplemented.

Args:
    raw_string (str): The raw string to execute.
    session (Session, optional): The session executing the command.



#### `def msg(self, *args, **kwargs)`

Send a direct textual message to this object. If the object is currently
controlled by a connected session, the message is routed to the client.

Args:
    *args: Ordered textual messages.
    **kwargs: Extra arguments, primarily including 'from_obj' and 'text'.



#### `def for_contents(self, func, exclude, **kwargs)`

Runs a function on every object contained within this one.

Args:
    func (callable): Function to call. This must have the
        formal call sign func(obj, **kwargs), where obj is the
        object currently being processed and `**kwargs` are
        passed on from the call to `for_contents`.
    exclude (list, optional): A list of object not to call the
        function on.

Keyword Args:
    Keyword arguments will be passed to the function for all objects.



#### `def msg_contents(self, text, exclude, from_obj, mapping, raise_funcparse_errors, **kwargs)`

Emits a message to all objects inside this object.

Args:
    text (str or tuple): Message to send. If a tuple, this should be
        on the valid OOB outmessage form `(message, {kwargs})`,
        where kwargs are optional data passed to the `text`
        outputfunc. The message will be parsed for `{key}` formatting and
        `$You/$you()/$You()`, `$obj(name)`, `$conj(verb)` and `$pron(pronoun, option)`
        inline function callables.
        The `name` is taken from the `mapping` kwarg {"name": object, ...}`.
        The `mapping[key].get_display_name(looker=recipient)` will be called
        for that key for every recipient of the string.
    exclude (list, optional): A list of objects not to send to.
    from_obj (Object, optional): An object designated as the
        "sender" of the message. See `DefaultObject.msg()` for
        more info. This will be used for `$You/you` if using funcparser inlines.
    mapping (dict, optional): A mapping of formatting keys
        `{"key":<object>, "key2":<object2>,...}.
        The keys must either match `{key}` or `$You(key)/$you(key)` markers
        in the `text` string. If `<object>` doesn't have a `get_display_name`
        method, it will be returned as a string. Pass "you" to represent the caller,
        this can be skipped if `from_obj` is provided (that will then act as 'you').
    raise_funcparse_errors (bool, optional): If set, a failing `$func()` will
        lead to an outright error. If unset (default), the failing `$func()`
        will instead appear in output unparsed.

    **kwargs: Keyword arguments will be passed on to `obj.msg()` for all
        messaged objects.

Notes:
    For 'actor-stance' reporting (You say/Name says), use the
    `$You()/$you()/$You(key)` and `$conj(verb)` (verb-conjugation)
    inline callables. This will use the respective `get_display_name()`
    for all onlookers except for `from_obj or self`, which will become
    'You/you'. If you use `$You/you(key)`, the key must be in `mapping`.

    For 'director-stance' reporting (Name says/Name says), use {key}
    syntax directly. For both `{key}` and `You/you(key)`,
    `mapping[key].get_display_name(looker=recipient)` may be called
    depending on who the recipient is.

Examples:

    Let's assume:

    - `player1.key` -> "Player1",
    - `player1.get_display_name(looker=player2)` -> "The First girl"
    - `player2.key` -> "Player2",
    - `player2.get_display_name(looker=player1)` -> "The Second girl"

    Actor-stance:
    ::

        char.location.msg_contents(
            "$You() $conj(attack) $you(defender).",
            from_obj=player1,
            mapping={"defender": player2})

    - player1 will see `You attack The Second girl.`
    - player2 will see 'The First girl attacks you.'

    Director-stance:
    ::

        char.location.msg_contents(
            "{attacker} attacks {defender}.",
            mapping={"attacker":player1, "defender":player2})

    - player1 will see: 'Player1 attacks The Second girl.'
    - player2 will see: 'The First girl attacks Player2'



#### `def at_pre_move(self, destination, to_exit, **kwargs)`

Called before moving the object. Evaluates the destination's access locks.

Args:
    destination (Node | Object | None): The target location for the move.
    to_exit (str | None, optional): The name of the exit traversed, if any.
    **kwargs: Extra arguments.

Returns:
    bool: True if the move should proceed, False to abort.



#### `def at_post_move(self, destination, to_exit, **kwargs)`

Called after moving the object successfully completes.

Args:
    destination (Node | Object | None): The new location of the object.
    to_exit (str | None, optional): The name of the exit traversed, if any.
    **kwargs: Extra arguments.



#### `def move_to(self, destination, to_exit, force, announce, **kwargs)`

Execute the complex sequence of moving this object to a new location,
handling locks, announcements, map updates, and hooks bidirectionally.

Args:
    destination (Node | Object | None): The target destination.
    to_exit (str | None, optional): The exit traversed. Defaults to None.
    force (bool, optional): If True, bypasses pre-move checks. Defaults to False.
    announce (bool, optional): If True, broadcasts movement strings to rooms. Defaults to True.
    **kwargs: Optional variables passed to hooks.

Returns:
    bool: True if the move successful, False if aborted.



#### `def get_display_name(self, looker, **kwargs)`

Get the display name of this object, customized for the looker.

Args:
    looker (Object | None, optional): The object looking at this object. Defaults to None.
    **kwargs: Extra arguments.

Returns:
    str: The evaluated name string.



#### `def get_display_desc(self, looker, **kwargs)`

Get the display description of this object, customized for the looker.

Args:
    looker (Object | None, optional): The object looking at this object. Defaults to None.
    **kwargs: Extra arguments.

Returns:
    str: The evaluated description string.



#### `def get_display_things(self, looker, **kwargs)`

Get the formatted inventory/contents of this object.

Args:
    looker (Object | None, optional): The object looking at this object. Defaults to None.
    **kwargs: Extra arguments.

Returns:
    str: The formatted string listing contents, or empty string.



#### `def return_appearance(self, looker, **kwargs)`

Assembles and formats the complete appearance of this object into a single string.

Args:
    looker (Object | None, optional): The object observing this object. Defaults to None.
    **kwargs: Extra arguments.

Returns:
    str: The fully formatted appearance string for rendering on the client.



#### `def at_post_puppet(self, **kwargs)`

Called when a Session successfully assumes direct control of this object.
Re-subscribes to channels, registers with the map system, and loads CmdSets.

Args:
    **kwargs: Extra arguments.



#### `def announce_move_from(self, destination, from_exit, **kwargs)`

Announces that this object has arrived in a target room.

Args:
    destination (Node): The node the object has arrived into.
    from_exit (str | None): The name of the exit traversed to get here, if any.
    **kwargs: Extra arguments passed to msg_contents.



#### `def announce_move_to(self, source_location, to_exit, **kwargs)`

Announces that this object has departed a source room.

Args:
    source_location (Node): The node the object has departed from.
    to_exit (str | None): The name of the exit traversed to leave.
    **kwargs: Extra arguments passed to msg_contents.



#### `def at_msg_receive(self, text, from_obj, **kwargs)`

Called when this object is about to receive an arbitrary string message.
Returning False aborts the message delivery.

Args:
    text (str | None, optional): The message content. Defaults to None.
    from_obj (Object | None, optional): The sender of the message. Defaults to None.
    **kwargs: Extra arguments.

Returns:
    bool: True if the message should be received, False to reject it.



#### `def at_msg_send(self, text, to_obj, **kwargs)`

Called when this object sends an arbitrary string message to another object.

Args:
    text (str | None, optional): The message content. Defaults to None.
    to_obj (Object | None, optional): The intended receiver. Defaults to None.
    **kwargs: Extra arguments.



#### `def at_desc(self, looker, **kwargs)`

Called when another object looks at this object.

Args:
    looker (Object | None, optional): The object observing this one. Defaults to None.
    **kwargs: Extra arguments.



#### `def at_pre_get(self, getter, **kwargs)`

Called before another object attempts to pick up this object.
Evaluates the "get" lock by default.

Args:
    getter (Object): The object attempting to get this object.
    **kwargs: Extra arguments.

Returns:
    bool: True if the get is permitted, False otherwise.



#### `def at_get(self, getter, **kwargs)`

Called after another object successfully picks up this object.

Args:
    getter (Object): The object that picked up this object.
    **kwargs: Extra arguments.



#### `def at_pre_give(self, giver, getter, **kwargs)`

Called before this object is given from one inventory to another.
Evaluates the "give" lock on the receiving object by default.

Args:
    giver (Object): The object currently holding this object.
    getter (Object): The intended recipient.
    **kwargs: Extra arguments.

Returns:
    bool: True if the transfer is permitted, False otherwise.



#### `def at_give(self, giver, getter, **kwargs)`

Called after this object is successfully transferred between inventories.

Args:
    giver (Object): The previous holder of this object.
    getter (Object): The new holder.
    **kwargs: Extra arguments.



#### `def at_pre_drop(self, dropper, **kwargs)`

Called before this object is dropped from an inventory into the room.
Evaluates the "drop" lock by default.

Args:
    dropper (Object): The object attempting to drop this object.
    **kwargs: Extra arguments.

Returns:
    bool: True if dropping is permitted, False otherwise.



#### `def at_drop(self, dropper, **kwargs)`

Called after this object is successfully dropped out of an inventory.

Args:
    dropper (Object): The actor that dropped this object.
    **kwargs: Extra arguments.



#### `def at_pre_say(self, message, **kwargs)`

Called before this object broadcasts a speech message into the room.
Can intercept and mutate the spoken message.

Args:
    message (str): The raw string intended to be spoken.
    **kwargs: Extra arguments.

Returns:
    str: The potentially modified message string.



#### `def at_say(self, message, msg_self, msg_location, receivers, msg_receivers, **kwargs)`

Display the actual say (or whisper) of self.

This hook should display the actual say/whisper of the object in its
location.  It should both alert the object (self) and its
location that some text is spoken.  The overriding of messages or
`mapping` allows for simple customization of the hook without
re-writing it completely.

Args:
    message (str): The message to convey.
    msg_self (bool or str, optional): If boolean True, echo `message` to self. If a string,
        return that message. If False or unset, don't echo to self.
    msg_location (str, optional): The message to echo to self's location.
    receivers (DefaultObject or iterable, optional): An eventual receiver or receivers of the
        message (by default only used by whispers).
    msg_receivers(str): Specific message to pass to the receiver(s). This will parsed
        with the {receiver} placeholder replaced with the given receiver.
Keyword Args:
    whisper (bool): If this is a whisper rather than a say. Kwargs
        can be used by other verbal commands in a similar way.
    mapping (dict): Pass an additional mapping to the message.

Notes:


    Messages can contain {} markers. These are substituted against the values
    passed in the `mapping` argument.
    ::

        msg_self = 'You say: "{speech}"'
        msg_location = '{object} says: "{speech}"'
        msg_receivers = '{object} whispers: "{speech}"'

    Supported markers by default:

    - {self}: text to self-reference with (default 'You')
    - {speech}: the text spoken/whispered by self.
    - {object}: the object speaking.
    - {receiver}: replaced with a single receiver only for strings meant for a specific
      receiver (otherwise 'None').
    - {all_receivers}: comma-separated list of all receivers,
      if more than one, otherwise same as receiver
    - {location}: the location where object is.



#### `def at_look(self, target, **kwargs)`

Called when this object looks at another target. Evaluates the "view" lock.

Args:
    target (Object | Node | None): The entity being looked at.
    **kwargs: Extra arguments.

Returns:
    str: The evaluated appearance string of the target.



#### `def format_appearance(self, appearance, looker, **kwargs)`

Compresses and cleans up whitespace on the final appearance string.

Args:
    appearance (str): The raw multi-line appearance string.
    looker (Object): The object viewing the appearance.
    **kwargs: Extra arguments.

Returns:
    str: The polished string.



## 13.2 `atheriz.objects.nodes`

### Class: `Node`

this is the equivalent to a room.
many of the functions below are inspired heavily by or pulled straight from evennia.objects.objects.DefaultObject.

#### `def at_desc(self, looker, **kwargs)`

Called when the node is looked at.



#### `def at_tick(self)`

Called every tick.



#### `@property def contents(self)`



#### `def for_contents(self, func, exclude, **kwargs)`



#### `def resolve_relations(self)`

Called as pass 2 of the database load to reconnect relational IDs to actual objects.
This reconstitutes pointers and reschedules async ticker events or script hooks
for the Node.



#### `@property def tick_seconds(self)`

float: The interval in seconds at which `at_tick` is called.



#### `@tick_seconds.setter def tick_seconds(self, value)`



#### `@property def is_tickable(self)`

bool: Indicates if this node is currently registered with the asynchronous ticker.



#### `@is_tickable.setter def is_tickable(self, value)`



#### `def at_pre_object_leave(self, destination, to_exit, **kwargs)`

Called before an object leaves the node. Returning False aborts the move.

Args:
    destination (Node | Object | None): The destination of the object.
    to_exit (str | None, optional): The exit used to leave.
    **kwargs: Extra arguments.

Returns:
    bool: True to allow leaving, False to abort.



#### `def at_object_leave(self, destination, to_exit, **kwargs)`

Called after an object has successfully left the node.

Args:
    destination (Node | Object | None): The destination of the object.
    to_exit (str | None, optional): The exit used to leave.
    **kwargs: Extra arguments.



#### `def at_pre_object_receive(self, source, from_exit, **kwargs)`

Called before an object enters the node. Returning False aborts the entry.

Args:
    source (Node | Object | None): The source location.
    from_exit (str | None, optional): The exit used to enter.
    **kwargs: Extra arguments.

Returns:
    bool: True to allow entry, False to abort.



#### `def at_object_receive(self, source, from_exit, **kwargs)`

Called after an object has successfully entered the node.

Args:
    source (Node | Object | None): The source location.
    from_exit (str | None, optional): The exit used to enter.
    **kwargs: Extra arguments.



#### `def at_init(self)`

Called after this node object is deserialized and all its attributes
and components are linked and instantiated.



#### `def delete(self, caller, recursive)`

Delete this node.

Args:
    recursive (bool, optional): Delete all objects in this node. Defaults to False.

Returns:
    tuple[int, list] | None: (count of nodes deleted/moved, list of object ops), or None if aborted.



#### `def at_delete(self, caller)`

Called before a node is fundamentally deleted from the world grid.
Evaluates the node's delete lock.

Args:
    caller (Object): The object executing the command.

Returns:
    bool: True to proceed with deletion, False to stop.



#### `def add_noun(self, noun, desc)`

Adds a static scenic noun to the room.

Args:
    noun (str): The keyword or name to look at.
    desc (str): The description returned when looked at.



#### `def remove_noun(self, noun)`

Removes a scenic noun from the room.

Args:
    noun (str): The keyword to remove.



#### `def get_noun(self, noun)`

Retrieves the description of a scenic noun.

Args:
    noun (str): The keyword to look for.

Returns:
    str | None: The description, or None if not found.



#### `def search(self, query)`

Searches the contents of this node using the given query string.

Args:
    query (str): The search phrase.

Returns:
    list[Any]: A list of objects matching the search query.



#### `def get_links(self)`

Retrieves a copy of the links (exits) leading out of this node.

Returns:
    list[NodeLink]: A list of exit links.



#### `def has_link_name(self, name)`

Check if this node has a link with the given name.
Args:
    name (str): Name of the link to check
Returns:
    bool: True if the link exists, False otherwise



#### `def get_link_by_name(self, name)`



#### `@property def area(self)`

NodeArea | None: The NodeArea object that encompasses this node.



#### `@property def grid(self)`

NodeGrid | None: The NodeGrid object corresponding to this node's Z-level.



#### `@property def name(self)`

str: The string representation of this node's coordinates.



#### `def add_script(self, script)`

Attach a global script hook to this node.

Args:
    script (int | Any): The ID of the Script, or the Script object itself.



#### `def remove_script(self, script)`

Remove a global script hook from this node.

Args:
    script (int | Any): The ID of the Script, or the Script object itself.



#### `def get_random_link(self)`

randomly select a NodeLink (exit) from this Node
Returns:
    NodeLink | None: NodeLink if this Node has any NodeLinks, otherwise None



#### `def add_link(self, link)`

add an exit to this node
Args:
    link (NodeLink): exit to add



#### `def remove_link(self, name)`

Remove an exit from this node. Also alerts the map handler if it crosses areas.

Args:
    name (str): The name of the exit to remove.



#### `def add_exits(self, obj, internal)`

add this node's exits to obj's cmdset

Args:
    obj (DefaultObject): object, character, etc. to add exit commands to



#### `def add_objects(self, objs)`

add objects to this node's inventory
Args:
    objs (list): list of objects to add



#### `def add_object(self, obj)`

add object to this node's inventory
Args:
    obj: object to add



#### `def remove_object(self, obj)`

remove object from this node's inventory
Args:
    obj (Object): object to remove



#### `def msg_contents(self, text, exclude, from_obj, mapping, raise_funcparse_errors, **kwargs)`

send a message to all objects in this node

Args:
    text (str | tuple, optional): message to send. Defaults to None.
    exclude (list, optional): objects to exclude from message. Defaults to None.
    from_obj (Object, optional): object sending message. Defaults to None.
    mapping (dict, optional): mapping for funcparse. Defaults to None.
    raise_funcparse_errors (bool, optional): raise funcparse errors. Defaults to False.
    internal (bool, optional): internal message, bypass lock if True. Defaults to False.
    **kwargs: additional keyword arguments to pass to msg



#### `def get_display_things(self, looker, **kwargs)`

Get the formatted inventory/contents of strictly inanimate items in this node.

Args:
    looker (Object | None, optional): The object viewing the room. Defaults to None.
    **kwargs: Extra arguments.

Returns:
    str: The formatted string listing contents, or an empty string.



#### `def get_display_characters(self, looker, **kwargs)`

Get the formatted list of other characters currently in this node.

Args:
    looker (Object | None, optional): The object viewing the room (excluded from output). Defaults to None.
    **kwargs: Extra arguments.

Returns:
    str: The formatted string listing characters, or an empty string.



#### `def get_display_exits(self, looker, **kwargs)`

Get the formatted list of available exits from this node.

Args:
    looker (Object | None, optional): The object viewing the room. Defaults to None.
    **kwargs: Extra arguments.

Returns:
    str: The formatted string listing exits, or an empty string.



#### `def get_display_doors(self, looker, **kwargs)`

Get the formatted list of doors present in this node.

Args:
    looker (Object | None, optional): The object viewing the room. Defaults to None.
    **kwargs: Extra arguments.

Returns:
    str: The formatted string listing doors, or an empty string.



#### `def get_display_desc(self, looker, **kwargs)`

Get the main descriptive text for this node.

Args:
    looker (Object | None, optional): The object viewing the room. Defaults to None.
    **kwargs: Extra arguments.

Returns:
    str: The description text, followed by a newline.



#### `def get_display_name(self, looker, **kwargs)`

Get the name of the node (usually returns empty/none for rooms unless builder).

Args:
    looker (Object | None, optional): The object viewing the room. Defaults to None.
    **kwargs: Extra arguments.

Returns:
    str: The builder string identifying the coord, or an empty string.



#### `def return_appearance(self, looker, **kwargs)`

Assembles and formats the complete appearance of this room into a single string.
Fills the standard appearance_template using the object's helper display methods.

Args:
    looker (Object | None, optional): The object observing this room. Defaults to None.
    **kwargs: Extra arguments.

Returns:
    str: The fully formatted room output string for rendering.



## 13.3 `atheriz.objects.base_account`

### Class: `Account`

#### `def create(cls, name, password)`

Create a new account.



#### `def delete(self, caller, unused)`

Delete this account from the game entirely.

Args:
    caller (Object | None, optional): The object executing the deletion. Defaults to None.
    unused (bool, optional): Unused parameter for API compatibility. Defaults to True.

Returns:
    bool: True if the account was successfully deleted, False if aborted.



#### `def at_pre_puppet(self, character)`

Called before a character is puppeted by this account.

Args:
    character (Object): The character object to puppet.

Returns:
    bool: True to allow puppeting, False to cancel.



#### `def at_delete(self, caller)`

Called before the account is deleted.

Args:
    caller (Object | None, optional): The object executing the command. Defaults to None.

Returns:
    bool: True to proceed with deletion, False to stop.



#### `def at_create(self)`

Called after a new account is successfully created.



#### `def at_disconnect(self)`

Called when a session associated with this account disconnects.



#### `def add_character(self, character)`

Add a character's ID to the list of characters owned by this account.

Args:
    character (Object): The character to add.



#### `def remove_character(self, character)`

Remove a character's ID from the list of characters owned by this account.

Args:
    character (Object): The character to remove.



#### `def hash_password(password)`

Hash the given plaintext password using the system salt.

Args:
    password (str): The plaintext password to hash.

Returns:
    str: The SHA-256 hashed password string.



#### `def check_password(self, password)`

Check if the provided plaintext password matches the account's hashed password.

Args:
    password (str): The plaintext password to test.

Returns:
    bool: True if the passwords match, False otherwise.



#### `def set_password(self, password)`

Update and hash the account's password.

Args:
    password (str): The new plaintext password.



#### `def login(self, name, password)`

Attempt to log in to the account with given credentials.

Args:
    name (str): The provided account name.
    password (str): The plaintext password to verify.

Returns:
    bool: True on successful authentication, False otherwise.



## 13.4 `atheriz.objects.base_channel`

### Class: `Channel`

#### `def create(cls, name)`



#### `def delete(self, caller, unused)`

Delete this channel from the database entirely.

Args:
    caller (Object | None, optional): The object executing the deletion. Defaults to None.
    unused (bool, optional): Unused parameter for API compatibility. Defaults to True.
    
Returns:
    bool: True if the channel was successfully deleted, False if aborted.



#### `def at_delete(self, caller)`

Called before the channel is deleted.

Args:
    caller (Object | None, optional): The object executing the command. Defaults to None.
    
Returns:
    bool: True to proceed with deletion, False to stop.



#### `def at_create(self)`

Called after a new channel is successfully created.



#### `def add_listener(self, listener)`

Connects an object to this channel to receive broadcasts.

Args:
    listener (Object): The object to subscribe to this channel.



#### `def remove_listener(self, listener)`

Disconnects an object from this channel.

Args:
    listener (Object): The object to unsubscribe.



#### `def get_command(self)`

Generates and retrieves the Command class instance used to converse on this channel.

Returns:
    Command | None: The specialized hook command for this channel.



#### `def msg(self, message, sender)`

Send a message to the channel.



#### `def format_message(self, timestamp, sender, message)`

Format a message. Override in subclasses for custom formatting.



#### `def get_history(self, count)`

Return last 'count' messages, oldest first, each formatted with newline.



#### `def clear_history(self)`

Clear all history from the channel.



## 13.5 `atheriz.objects.base_script`

### Class: `Script`

#### `def create(cls, caller, name, desc)`

Create a new persistent Script in the database.

Args:
    caller (Object | None): The object executing the creation.
    name (str): The name of the script.
    desc (str, optional): A description for the script. Defaults to "".

Returns:
    Self: The generated Script object.



#### `def delete(self, caller, recursive)`

Delete this script entirely from the database and remove any active hooks.

Args:
    caller (Object | None, optional): The object executing the command. Defaults to None.
    recursive (bool, optional): Unused compatibility argument. Defaults to True.

Returns:
    bool: True upon successful deletion.



#### `def at_install(self)`

Called when the script is assigned to and installed on an object.

This occurs immediately when the script is attached, and upon every subsequent 
server reboot. You can use this for initialization code, or alternatively hook 
`at_init` on the child. `at_init` will only run on object instantiation (server boot/creation).



#### `def install_hooks(self, child)`

Attaches all properly-decorated `at_*` hook methods in this script to a child object.

Every hook in this class must be prefixed with `at_` to mirror the child object's method, 
and decorated with `@before`, `@after`, or `@replace`.

Args:
    child (Object | Node): The target object experiencing the method injection.



#### `def remove_hooks(self, child)`

Detaches all hook methods in this Script from the currently-assigned child object.

Args:
    child (Object | Node | None, optional): An explicitly provided object to detach from. 
    Defaults to the currently active child payload.



## 13.6 `atheriz.commands.base_cmd`

### Class: `Command`

Base command class.

Attributes:
    key (str): The primary keyword to invoke this command.
    aliases (list[str]): Alternate keywords.
    description (str): Brief description of the command.

#### `def access(self, caller)`

Override this method to implement access control.

Args:
    caller: The object/player calling the command.

Returns:
    bool: True if the caller has access, False otherwise.

Separate locks aren't implemented for commands since all commands are already custom classes
it's just as easy to implement access control in the command class itself.



#### `@property def parser(self)`



#### `@parser.setter def parser(self, value)`



#### `def setup_parser(self)`

Override this method to add arguments to self.parser.
Example:
    self.parser.add_argument("target", help="Target name")



#### `def print_help(self)`

Override this method to implement help text.



#### `def run(self, caller, args)`

Override this method to implement the command logic.

Args:
    caller: The object/player calling the command.
    args: The parsed namespace from argparse.



#### `def execute(self, caller, args_string)`

Parses arguments and runs the command.

Args:
    caller: The object/player calling the command.
    args_string: The string containing the arguments (command name stripped).

Returns:
    tuple[Callable[[Object | Connection, Any], None], Object | Connection, Any]: the run function, caller, and the parsed arguments



## 13.7 `atheriz.commands.base_cmdset`

### Class: `CmdSet`

#### `def get_all(self)`

Extract all commands currently active in this command set.

Returns:
    list[Command]: A list of all Command instances.



#### `def add(self, command, tag)`

Merge a single Command instance into this command set. 
If a command with the same key or alias already exists, it is overwritten.

Args:
    command (Command): The command object to add.
    tag (str | None, optional): An optional tag to categorize the command (e.g. "exits"). 
        Defaults to None.



#### `def adds(self, commands, tag)`

Merge multiple Command instances into this command set simultaneously.
Any commands with duplicate keys or aliases will overwrite pre-existing ones.

Args:
    commands (list[Command]): A list of Command objects to add.
    tag (str | None, optional): An optional tag to apply to all added commands. 
        Defaults to None.



#### `def remove(self, command)`

Remove a specific Command instance from this command set, including its aliases.

Args:
    command (Command): The command object to remove.



#### `def remove_by_tag(self, tag)`

Remove all commands matching a specific tag string from this command set.

Args:
    tag (str): The tag identifier (e.g., "exits").



#### `def get(self, command)`

Retrieve a Command instance by its key or alias.

Args:
    command (str): The key or alias to search for.

Returns:
    Command | None: The matching Command object, or None if not found.



#### `def get_keys(self)`

Retrieve a list of all raw command keywords and aliases currently registered in this set.

Returns:
    list[str]: A list of command keys.



## 13.8 `atheriz.inputfuncs`

### Class: `InputFuncs`

Handles parsed JSON-RPC input messages from the client.
Methods in this class correspond to specific message commands sent by the client.

To add custom handlers, subclass this and add methods decorated with @inputfunc:

    class MyInputFuncs(InputFuncs):
        @inputfunc()
        def my_command(self, connection, args, kwargs):
            # Handle 'my_command' messages
            pass

#### `def get_handlers(self)`

Scans this class instance to discover and map all methods decorated with @inputfunc.

Returns:
    dict[str, Callable]: A dictionary mapping the expected input string command 
        to its corresponding handler function.



#### `def text(self, connection, args, kwargs)`

Handle plain text/command input from the client (e.g. typing commands in the game).

This method is responsible for matching plain text to command sets, checking 
abbreviations and aliases, and queuing the matched command for execution.

Args:
    connection (Connection): The connection receiving the text.
    args (list): List of arguments from the RPC call (expects string as first element).
    kwargs (dict): Extra Keyword arguments.



#### `def term_size(self, connection, args, kwargs)`

Handle terminal resize events sent natively from the client.

Args:
    connection (Connection): The connection triggering the resize.
    args (list): Expects a list containing `[width (int), height (int)]`.
    kwargs (dict): Extra Keyword arguments.



#### `def map_size(self, connection, args, kwargs)`

Handle map UI resize events sent natively from the web client.

Args:
    connection (Connection): The connection triggering the resize.
    args (list): Expects a list containing `[width (int), height (int)]` of the map pane.
    kwargs (dict): Extra Keyword arguments.



#### `def screenreader(self, connection, args, kwargs)`

Handle screenreader accessibility status updates from the client.

Args:
    connection (Connection): The connection sending the update.
    args (list): Expects a list containing a single boolean denoting active status.
    kwargs (dict): Extra Keyword arguments.



#### `def client_ready(self, connection, args, kwargs)`

Handle the 'client ready' lifecycle signal, prompting the welcome screen to render.

Args:
    connection (Connection): The connection reporting ready status.
    args (list): Unused.
    kwargs (dict): Unused.



## 13.9 `atheriz.globals.objects`

### `def filter_by(l)`

Filter objects by a lambda.

For example:
```python
filter_by(lambda x: x.is_pc)
```

Args:
    l (Callable[[Any], bool]): The lambda to use for filtering.

Returns:
    list[Any]: The list of objects that match the search criteria.



### `def get(ids)`

Search for objects by ID.

Args:
    ids (int | list[int]): The ID or list of IDs to search for.

Returns:
    list[object]: The list of objects that match the search criteria.



### `def add_object(obj)`

Add an object to the global object registry.



### `def remove_object(obj)`

Remove an object from the global object registry.



### `def load_objects()`

Load objects from the database.



### `def save_objects(force)`

Save modified objects to the database.



### `def delete_objects(ops)`

Delete objects using a list of SQL operations in a transaction.

Args:
    ops (list[tuple[str, tuple]]): The list of SQL operations to execute.



## 13.10 `atheriz.globals.map`

## 13.11 `atheriz.globals.time`

## 13.12 `atheriz.utils`

### `def is_in_game_folder()`

Check if the current directory is a game folder.



### `def msg_all(msg)`

send message to all connected clients

Args:
    msg (str): message to send



### `def ensure_thread_safe(obj)`

Patches the class of the provided object if not already patched.



### `def wrap_xterm256(input, fg, bg, bold, italic, underline, inverse, strikethru, clear)`

colorize input string with ANSI xterm256 color and append a color reset code to the end

Args:
    input (str): input string
    fg (int, optional): xterm256 foreground color. Defaults to None.
    bg (int, optional): xterm256 background color. Defaults to None.
    bold (bool, optional): bold? Defaults to False.
    italic (bool, optional): italic? Defaults to False.
    underline (bool, optional): underline? Defaults to False.
    inverse (bool, optional): inverse? Defaults to False.
    strikethru (bool, optional): strikethrough? Defaults to False.
    clear (bool, optional): strip existing ANSI color from input. Defaults to False.

Returns:
    str: colorized string with color reset at the end



### `def wrap_truecolor(input, fg, bg, fg_bright, fg_sat, bg_bright, bg_sat, bold, italic, underline, inverse, strikethru, clear)`

colorize input string with ANSI truecolor and append a color reset code to the end

Args:
    input (str): input string
    fg (float, optional): foreground color where 120.0 = green. Defaults to None.
    bg (float, optional): background color where 120.0 = green. Defaults to None.
    fg_bright (float, optional): foreground brightness where 100.0 = maximum. Defaults to 100.0.
    fg_sat (float, optional): foreground saturation where 100.0 = maximum. Defaults to 100.0.
    bg_bright (float, optional): background brightness where 100.0 = maximum. Defaults to 100.0.
    bg_sat (float, optional): background saturation where 100.0 = maximum. Defaults to 100.0.
    bold (bool, optional): bold? Defaults to False.
    italic (bool, optional): italic? Defaults to False.
    underline (bool, optional): underline? Defaults to False.
    inverse (bool, optional): inverse? Defaults to False.
    strikethru (bool, optional): strikethrough? Defaults to False.
    clear (bool, optional): strip existing ANSI color from input. Defaults to False.

Returns:
    str: colorized string with color reset at the end



### `def strip_ansi(input)`



### `def dice_roll(rolls, faces)`



### `def dice_roll_average(rolls, faces)`



### `def clamp(minimum, value, maximum)`



### `def get_dir(origin, dest)`

get map direction between two points. (0,0) is lower left.
returns '' if origin == dest



### `def dist_3d(origin, dest)`



### `def get_reverse_link(location, destination)`



### `def compress_whitespace(text, max_linebreaks, max_spacing)`

Removes extra sequential whitespace in a block of text. This will also remove any trailing
whitespace at the end.

Args:
    text (str):   A string which may contain excess internal whitespace.

Keyword args:
    max_linebreaks (int):  How many linebreak characters are allowed to occur in a row.
    max_spacing (int):     How many spaces are allowed to occur in a row.



### `def is_iter(obj)`

Checks if an object behaves iterably.

Args:
    obj (any): Entity to check for iterability.

Returns:
    is_iterable (bool): If `obj` is iterable or not.

Notes:
    Strings are *not* accepted as iterable (although they are
    actually iterable), since string iterations are usually not
    what we want to do with a string.



### `def make_iter(obj)`

Makes sure that the object is always iterable.

Args:
    obj (any): Object to make iterable.

Returns:
    iterable (list or iterable): The same object
        passed-through or made iterable.



### `def copy_word_case(base_word, new_word)`

Converts a word to use the same capitalization as a first word.

Args:
    base_word (str): A word to get the capitalization from.
    new_word (str): A new word to capitalize in the same way as `base_word`.

Returns:
    str: The `new_word` with capitalization matching the first word.

Notes:
    This is meant for words. Longer sentences may get unexpected results.

    If the two words have a mix of capital/lower letters _and_ `new_word`
    is longer than `base_word`, the excess will retain its original case.



### `def iter_to_str(iterable, sep, endsep, addquote)`

This pretty-formats an iterable list as string output, adding an optional
alternative separator to the second to last entry.  If `addquote`
is `True`, the outgoing strings will be surrounded by quotes.

Args:
    iterable (any): Usually an iterable to print. Each element must be possible to
        present with a string. Note that if this is a generator, it will be
        consumed by this operation.
    sep (str, optional): The string to use as a separator for each item in the iterable.
    endsep (str, optional): The last item separator will be replaced with this value.
    addquote (bool, optional): This will surround all outgoing
        values with double quotes.

Returns:
    str: The list represented as a string.

Notes:
    Default is to use 'Oxford comma', like 1, 2, 3, and 4.

Examples:
    ```python
    >>> iter_to_string([1,2,3], endsep=',')
    '1, 2, 3'
    >>> iter_to_string([1,2,3], endsep='')
    '1, 2 3'
    >>> iter_to_string([1,2,3], ensdep='and')
    '1, 2 and 3'
    >>> iter_to_string([1,2,3], sep=';', endsep=';')
    '1; 2; 3'
    >>> iter_to_string([1,2,3], addquote=True)
    '"1", "2", and "3"'
    ```



### `def is_empty_method(method)`

Check if a method body is effectively empty (only contains 'pass' or 'return None').



### `def get_class_hooks(cls)`

Inspect a class to extract methods meant to be overridden (hooks).
Handles cases where inspect.signature might fail due to NameErrors in type hints.

Returns:
    List of tuples: (method_name, signature, docstring, is_empty)



## 13.13 `atheriz.objects.funcparser`

Generic function parser for functions embedded in a string, on the form
`$funcname(*args, **kwargs)`, for example:

```
"A string $foo() with $bar(a, b, c, $moo(), d=23) etc."
```

Each arg/kwarg can also be another nested function. These will be executed
inside-out and their return will used as arguments for the enclosing function
(so the same as for regular Python function execution).

This is the base for all forms of embedded func-parsing, like inlinefuncs and
protfuncs. Each function available to use must be registered as a 'safe'
function for the parser to accept it. This is usually done in a module with
regular Python functions on the form:

```python
# in a module whose path is passed to the parser

def _helper(x):
    # use underscore to NOT make the function available as a callable

def funcname(*args, **kwargs):
    # this can be accessed as $funcname(*args, **kwargs)
    # it must always accept *args and **kwargs.
    ...
    return something
```

Usage:

```python
from evennia.utils.funcparser import FuncParser

parser = FuncParser("path.to.module_with_callables")
result = parser.parse("String with $funcname() in it")

```

The `FuncParser` also accepts a direct dict mapping of `{'name': callable, ...}`.

---

### `def funcparser_callable_eval(*args, **kwargs)`

Funcparser callable. This will combine safe evaluations to try to parse the
incoming string into a python object. If it fails, the return will be same
as the input.

Args:
    string (str): The string to parse. Only simple literals or operators are allowed.

Returns:
    any: The string parsed into its Python form, or the same as input.

Examples:
    - `$py(1) -> 1`
    - `$py([1,2,3,4] -> [1, 2, 3]`
    - `$py(3 + 4) -> 7`



### `def funcparser_callable_toint(*args, **kwargs)`

Usage: $toint(43.0) -> 43



### `def funcparser_callable_int2str(*args, **kwargs)`

Usage: $int2str(1) -> 'one' etc, up to 12->twelve.

Args:
    number (int): The number. If not an int, will be converted.

Uses the int2str utility function.



### `def funcparser_callable_an(*args, **kwargs)`

Usage: $an(thing) -> a thing

Adds a/an depending on if the first letter of the given word is a consonant or not.



### `def funcparser_callable_add(*args, **kwargs)`

Usage: `$add(val1, val2) -> val1 + val2`



### `def funcparser_callable_sub(*args, **kwargs)`

Usage: ``$sub(val1, val2) -> val1 - val2`



### `def funcparser_callable_mult(*args, **kwargs)`

Usage: `$mult(val1, val2) -> val1 * val2`



### `def funcparser_callable_div(*args, **kwargs)`

Usage: `$mult(val1, val2) -> val1 / val2`



### `def funcparser_callable_round(*args, **kwargs)`

Funcparser callable. Rounds an incoming float to a
certain number of significant digits.

Args:
    inp (str or number): If a string, it will attempt
        to be converted to a number first.
    significant (int): The number of significant digits.  Default is None -
        this will turn the result into an int.

Returns:
    any: The rounded value or inp if inp was not a number.

Examples:
    - `$round(3.5434343, 3) -> 3.543`
    - `$round($random(), 2)` - rounds random result, e.g `0.22`



### `def funcparser_callable_random(*args, **kwargs)`

Funcparser callable. Returns a random number between 0 and 1, from 0 to a
maximum value, or within a given range (inclusive).

Args:
    minval (str, optional): Minimum value. If not given, assumed 0.
    maxval (str, optional): Maximum value.

Notes:
    If either of the min/maxvalue has a '.' in it, a floating-point random
    value will be returned. Otherwise it will be an
    integer value in the given range.

Examples:
    - `$random()` - random value [0 .. 1) (float).
    - `$random(5)` - random value [0..5] (int)
    - `$random(5.0)` - random value [0..5] (float)
    - `$random(5, 10)` - random value [5..10] (int)
    - `$random(5, 10.0)` - random value [5..10] (float)



### `def funcparser_callable_randint(*args, **kwargs)`

Usage: $randint(start, end):

Legacy alias - always returns integers.



### `def funcparser_callable_choice(*args, **kwargs)`

FuncParser callable. Picks a random choice from a list.

Args:
    listing (list): A list of items to randomly choose between.
        This will be converted from a string to a real list.
    *args: If multiple args are given, will pick one randomly from them.

Returns:
    any: The randomly chosen element.

Example:
    - `$choice(key, flower, house)`
    - `$choice([1, 2, 3, 4])`



### `def funcparser_callable_pad(*args, **kwargs)`

FuncParser callable. Pads text to given width, optionally with fill-characters

Args:
    text (str): Text to pad.
    width (int): Width of padding.
    align (str, optional): Alignment of padding; one of 'c', 'l' or 'r'.
    fillchar (str, optional): Character used for padding. Defaults to a space.

Example:
    - `$pad(text, 12, r, ' ') -> "        text"`
    - `$pad(text, width=12, align=c, fillchar=-) -> "----text----"`



### `def funcparser_callable_crop(*args, **kwargs)`

FuncParser callable. Crops ingoing text to given widths.

Args:
    text (str, optional): Text to crop.
    width (str, optional): Will be converted to an integer. Width of
        crop in characters.
    suffix (str, optional): End string to mark the fact that a part
        of the string was cropped. Defaults to `[...]`.

Example:
    - `$crop(A long text, 10, [...]) -> "A lon[...]"`
    - `$crop(text, width=11, suffix='[...]) -> "A long[...]"`



### `def funcparser_callable_space(*args, **kwarg)`

Usage: $space(43)

Insert a length of space.



### `def funcparser_callable_justify(*args, **kwargs)`

Justify text across a width, default across screen width.

Args:
    text (str): Text to justify.
    width (int, optional): Defaults to default screen width.
    align (str, optional): One of 'l', 'c', 'r' or 'f' for 'full'.
    indent (int, optional): Intendation of text block, if any.

Returns:
    str: The justified text.

Examples:
    - `$just(text, width=40)`
    - `$just(text, align=r, indent=2)`



### `def funcparser_callable_left_justify(*args, **kwargs)`

Usage: $ljust(text)



### `def funcparser_callable_right_justify(*args, **kwargs)`

Usage: $rjust(text)



### `def funcparser_callable_center_justify(*args, **kwargs)`

Usage: $cjust(text)



### `def funcparser_callable_clr(*args, **kwargs)`

FuncParser callable. Colorizes nested text.

Args:
    startclr (str, optional): An ANSI color abbreviation without the
        prefix `|`, such as `r` (red foreground) or `[r` (red background).
    text (str, optional): Text
    endclr (str, optional): The color to use at the end of the string. Defaults
        to `|n` (reset-color).
Kwargs:
    color (str, optional): If given,

Example:
    - `$clr(r, text, n) -> "|rtext|n"`
    - `$clr(r, text) -> "|rtext|n`
    - `$clr(text, start=r, end=n) -> "|rtext|n"`



### `def funcparser_callable_pluralize(*args, **kwargs)`

FuncParser callable. Handles pluralization of a word.

Args:
    singular_word (str): The base (singular) word to optionally pluralize
    number (int): The number of elements; if 1 (or 0), use `singular_word` as-is,
        otherwise use plural form.
    plural_word (str, optional): If given, this will be used if `number`
        is greater than one. If not given, we simply add 's' to the end of
        `singular_word`.

Example:
    - `$pluralize(thing, 2)` -> "things"
    - `$pluralize(goose, 18, geese)` -> "geese"



### `def funcparser_callable_you(caller, receiver, mapping, capitalize, *args, **kwargs)`

Usage: $you() or $you(key)

Replaces with you for the caller of the string, with the display_name
of the caller for others.

Keyword Args:
    caller (Object): The 'you' in the string. This is used unless another
        you-key is passed to the callable in combination with `mapping`.
    receiver (Object): The recipient of the string.
    mapping (dict, optional): This is a mapping `{key:Object, ...}` and is
        used to find which object `$you(key)` refers to. If not given, the
        `caller` kwarg is used.
    capitalize (bool): Passed by the You helper, to capitalize you.

Returns:
    str: The parsed string.

Raises:
    ParsingError: If `caller` and `receiver` were not supplied.

Notes:
    The kwargs should be passed the to parser directly.

Examples:
    This can be used by the say or emote hooks to pass actor stance
    strings. This should usually be combined with the $conj() callable.

    - `With a grin, $you() $conj(jump) at $you(tommy).`

    The caller-object will see "With a grin, you jump at Tommy."
    Tommy will see "With a grin, CharName jumps at you."
    Others will see "With a grin, CharName jumps at Tommy."



### `def funcparser_callable_you_capitalize(you, receiver, mapping, capitalize, *args, **kwargs)`

Usage: $You() - capitalizes the 'you' output.



### `def funcparser_callable_your(caller, receiver, mapping, capitalize, *args, **kwargs)`

Usage: $your() or $your(key)

Replaces with your for the caller of the string, with the display_name +'s
of the caller for others.

Keyword Args:
    caller (Object): The 'your' in the string. This is used unless another
        your-key is passed to the callable in combination with `mapping`.
    receiver (Object): The recipient of the string.
    mapping (dict, optional): This is a mapping `{key:Object, ...}` and is
        used to find which object `$you(key)` refers to. If not given, the
        `caller` kwarg is used.
    capitalize (bool): Passed by the You helper, to capitalize you.

Returns:
    str: The parsed string.

Raises:
    ParsingError: If `caller` and `receiver` were not supplied.

Notes:
    The kwargs should be passed the to parser directly.

Examples:
    This can be used by the say or emote hooks to pass actor stance
    strings.

    - `$your() pet jumps at $you(tommy).`

    The caller-object will see "Your pet jumps Tommy."
    Tommy will see "CharName's pet jumps at you."
    Others will see "CharName's pet jumps at Tommy."



### `def funcparser_callable_your_capitalize(you, receiver, mapping, capitalize, *args, **kwargs)`

Usage: $Your() - capitalizes the 'your' output.



### `def funcparser_callable_conjugate(caller, receiver, mapping, *args, **kwargs)`

Usage: $conj(word, [key])

Conjugate a verb according to if it should be 2nd or third person.

Keyword Args:
    caller (Object): The object who represents 'you' in the string.
    receiver (Object): The recipient of the string.
    mapping (dict, optional): This is a mapping `{key:Object, ...}` and is
        used to find which object the optional `key` argument refers to. If not given,
        the `caller` kwarg is used.

Returns:
    str: The parsed string.

Raises:
    ParsingError: If `you` and `recipient` were not both supplied.

Notes:
    Note that the verb will not be capitalized.

Examples:
    This is often used in combination with the $you/You callables.

    - `With a grin, $you() $conj(jump)`

    You will see "With a grin, you jump."
    Others will see "With a grin, CharName jumps."



### `def funcparser_callable_conjugate_for_pronouns(caller, receiver, mapping, *args, **kwargs)`

Usage: $pconj(word, [key])

Conjugate a verb according to if it should be 2nd or third person, respecting the
singular/plural gendering for third person.

Keyword Args:
    caller (Object): The object who represents 'you' in the string.
    receiver (Object): The recipient of the string.
    mapping (dict, optional): This is a mapping `{key:Object, ...}` and is
        used to find which object the optional `key` argument refers to. If not given,
        the `caller` kwarg is used.

Returns:
    str: The parsed string.

Raises:
    ParsingError: If `you` and `recipient` were not both supplied.

Notes:
    Note that the verb will not be capitalized.

Examples:
    This is often used in combination with the $pron/Pron callables.

    - `With a grin, $pron(you) $pconj(jump)`

    You will see "With a grin, you jump."
    With your gender as "male", others will see "With a grin, he jumps."
    With your gender as "plural", others will see "With a grin, they jump."



### `def funcparser_callable_pronoun(caller, receiver, mapping, capitalize, *args, **kwargs)`

Usage: $pron(word, [options], [key])

Adjust pronouns to the expected form. Pronouns are words you use instead of a
proper name, such as 'him', 'herself', 'theirs' etc. These look different
depending on who sees the outgoing string.

The parser maps between this table ...

====================  =======  =======  ==========  ==========  ===========
1st/2nd person        Subject  Object   Possessive  Possessive  Reflexive
                      Pronoun  Pronoun  Adjective   Pronoun     Pronoun
====================  =======  =======  ==========  ==========  ===========
1st person               I        me        my        mine       myself
1st person plural       we       us        our        ours       ourselves
2nd person              you      you       your       yours      yourself
2nd person plural       you      you       your       yours      yourselves
====================  =======  =======  ==========  ==========  ===========

... and this table (and vice versa).

====================  =======  =======  ==========  ==========  ===========
3rd person            Subject  Object   Possessive  Possessive  Reflexive
                      Pronoun  Pronoun  Adjective   Pronoun     Pronoun
====================  =======  =======  ==========  ==========  ===========
3rd person male         he       him       his        his        himself
3rd person female       she      her       her        hers       herself
3rd person neutral      it       it        its                   itself
3rd person plural       they    them       their      theirs     themselves
====================  =======  =======  ==========  ==========  ===========

This system will examine `caller` for either a property or a callable `.gender` to
get a default gender fallback (if not specified in the call). If a callable,
`.gender` will be called without arguments and should return a string
`male`/`female`/`neutral`/`plural` (plural is considered a gender for this purpose).
If no `gender` property/callable is found, `neutral` is used as a fallback.

The pronoun-type default (if not specified in call) is `subject pronoun`.

Args:
    pronoun (str): Input argument to parsed call. This can be any of the pronouns
        in the table above. If given in 1st/second form, they will be mappped to
        3rd-person form for others viewing the message (but will need extra input
        via the `gender`, see below). If given on 3rd person form, this will be
        mapped to 2nd person form for `caller` unless `viewpoint` is specified
        in options.
    options (str, optional): A space- or comma-separated string detailing `pronoun_type`,
        `gender`/`plural` and/or `viewpoint` to help the mapper differentiate between
        non-unique cases (such as if `you` should become `him` or `they`).
        Allowed values are:

        - `subject pronoun`/`subject`/`sp` (I, you, he, they)
        - `object pronoun`/`object/`/`op`  (me, you, him, them)
        - `possessive adjective`/`adjective`/`pa` (my, your, his, their)
        - `possessive pronoun`/`pronoun`/`pp`  (mine, yours, his, theirs)
        - `male`/`m`
        - `female`/`f`
        - `neutral`/`n`
        - `plural`/`p`
        - `1st person`/`1st`/`1`
        - `2nd person`/`2nd`/`2`
        - `3rd person`/`3rd`/`3`
    key (str, optional): If a mapping is provided, a string defining which object to
        reference when finding the correct pronoun. If not provided, it defaults
        to `caller`

Keyword Args:

    caller (Object): The object creating the string. If this has a property 'gender',
        it will be checked for a string 'male/female/neutral' to determine
        the 3rd person gender (but if `pronoun_type` contains a gender
        component, that takes precedence). Provided automatically to the
        funcparser.
    receiver (Object): The recipient of the string. This being the same as
        `caller` or not helps determine 2nd vs 3rd-person forms. This is
        provided automatically by the funcparser.
    mapping (dict, optional): This is a mapping `{key:Object, ...}` and is
        used to find which object the optional `key` argument refers to. If not given,
        the `caller` kwarg is used.
    capitalize (bool): The input retains its capitalization. If this is set the output is
        always capitalized.

Examples:

    ======================  =============    ===========
    Input                   caller sees      others see
    ======================  =============    ===========
    $pron(I, m)             I                he
    $pron(you,fo)           you              her
    $pron(yourself)         yourself         itself
    $pron(its)              your             its
    $pron(you,op,p)         you              them
    ======================  =============    ===========

Notes:
    There is no option to specify reflexive pronouns since they are all unique
    and the mapping can always be auto-detected.



### `def funcparser_callable_pronoun_capitalize(caller, receiver, capitalize, *args, **kwargs)`

Usage: $Pron(word, [options]) - always maps to a capitalized word.



## 13.14 `atheriz.settings`

### `SAVE_PATH`

Default value: `'save'`


### `SECRET_PATH`

Default value: `'secret'`


### `SERVERNAME`

Default value: `'AtheriZ'`


### `SERVER_HOSTNAME`

Default value: `'localhost'`


### `WEBSOCKET_ENABLED`

Default value: `True`


### `TELNET_ENABLED`

Default value: `True`


### `TELNET_PORT`

Default value: `4000`


### `TELNET_INTERFACE`

Default value: `'0.0.0.0'`


### `NETWORK_PROTOCOLS`

Default value: `['atheriz.network.websocket.WebSocketProtocol', 'atheriz.network.telnet.TelnetProtocol']`


### `ACCOUNT_CREATION_ENABLED`

Default value: `True`


### `WEBSERVER_ENABLED`

Default value: `True`


### `WEBSERVER_PORT`

Default value: `8000`


### `WEBSERVER_INTERFACE`

Default value: `'0.0.0.0'`


### `THREADPOOL_LIMIT`

Default value: `os.cpu_count()`


### `MAX_CHARACTERS`

Default value: `5`


### `DEFAULT_TICK_SECONDS`

Default value: `1.0`


### `FUNCPARSER_START_CHAR`

Default value: `'$'`


### `FUNCPARSER_ESCAPE_CHAR`

Default value: `'\\'`


### `FUNCPARSER_MAX_NESTING`

Default value: `20`


### `CLIENT_DEFAULT_WIDTH`

Default value: `78`


### `CLIENT_DEFAULT_HEIGHT`

Default value: `45`


### `DEBUG`

Default value: `True`


### `LOG_LEVEL`

Default value: `'info'`


### `SAVE_CHANNEL_HISTORY`

Default value: `True`


### `CHANNEL_HISTORY_LIMIT`

Default value: `50`


### `SLOW_LOCKS`

Default value: `True`


### `MAX_LOGIN_ATTEMPTS`

Default value: `3`


### `LOGIN_ATTEMPT_COOLDOWN`

Default value: `100`


### `ALWAYS_SAVE_ALL`

Default value: `False`


### `DEFAULT_HOME`

Default value: `('limbo', 0, 0, 0)`


### `MAP_ENABLED`

Default value: `True`


### `LEGEND_ENABLED`

Default value: `True`


### `MAP_FPS_LIMIT`

Default value: `5`


### `MAX_OBJECTS_PER_LEGEND`

Default value: `30`


### `AUTOSAVE_PLAYERS_ON_DISCONNECT`

Default value: `True`


### `AUTOSAVE_ON_SHUTDOWN`

Default value: `True`


### `AUTOSAVE_ON_RELOAD`

Default value: `True`


### `AUTO_COMMAND_ALIASING`

Default value: `True`


### `THREADSAFE_GETTERS_SETTERS`

Default value: `True`


### `DEFAULT_ROOM_OUTLINE`

Default value: `'single'`


### `SINGLE_WALL_PLACEHOLDER`

Default value: `'༗'`


### `DOUBLE_WALL_PLACEHOLDER`

Default value: `'༁'`


### `ROUNDED_WALL_PLACEHOLDER`

Default value: `'⍮'`


### `ROOM_PLACEHOLDER`

Default value: `'℣'`


### `PATH_PLACEHOLDER`

Default value: `'߶'`


### `ROAD_PLACEHOLDER`

Default value: `'᭤'`


### `ALL_SYMBOLS`

Default value: `[SINGLE_WALL_PLACEHOLDER, DOUBLE_WALL_PLACEHOLDER, ROUNDED_WALL_PLACEHOLDER, PATH_PLACEHOLDER, ROAD_PLACEHOLDER]`


### `NS_CLOSED_DOOR`

Default value: `'\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m━\x1b[0m'`


### `NS_OPEN_DOOR1`

Default value: `'\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m┚\x1b[0m'`


### `NS_OPEN_DOOR2`

Default value: `'\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m┒\x1b[0m'`


### `EW_CLOSED_DOOR`

Default value: `'\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m┃\x1b[0m'`


### `EW_OPEN_DOOR1`

Default value: `'\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m┙\x1b[0m'`


### `EW_OPEN_DOOR2`

Default value: `'\x1b[1m\x1b[38;2;166;97;0m\x1b[48;2;0;0;0m┕\x1b[0m'`


### `TIME_SYSTEM_ENABLED`

Default value: `True`


### `SOLAR_RECEIVER_LAMBDA`

Default value: `lambda x: x.is_pc and x.is_connected`


### `LUNAR_RECEIVER_LAMBDA`

Default value: `lambda x: x.is_pc and x.is_connected`


### `TIME_UPDATE_SECONDS`

Default value: `1.0`


### `START_YEAR`

Default value: `888`


### `TICK_MINUTES`

Default value: `1.0`


### `SECONDS_PER_MINUTE`

Default value: `60`


### `MINUTES_PER_HOUR`

Default value: `60`


### `HOURS_PER_DAY`

Default value: `24`


### `DAYS_PER_MONTH`

Default value: `30`


### `MONTHS_PER_YEAR`

Default value: `12`


### `DAYS_PER_YEAR`

Default value: `DAYS_PER_MONTH * MONTHS_PER_YEAR`


### `SECONDS_PER_HOUR`

Default value: `SECONDS_PER_MINUTE * MINUTES_PER_HOUR`


### `SECONDS_PER_DAY`

Default value: `SECONDS_PER_HOUR * HOURS_PER_DAY`


### `LUNAR_CYCLE_DAYS`

Default value: `30`


### `DAYS_PER_WEEK`

Default value: `7`


### `SUNRISE_HOUR`

Default value: `6`


### `SUNSET_HOUR`

Default value: `18`


### `SUNRISE_MESSAGE`

Default value: `'The sun rises on a new day.'`


### `SUNSET_MESSAGE`

Default value: `'The sun begins to set.'`

