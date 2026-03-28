from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING
from atheriz.objects.base_script import Script, after
from atheriz.globals.objects import get

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.nodes import Node


class FollowScript(Script):
    def __init__(self):
        super().__init__()
        self.is_temporary = True

    @after
    def at_post_move(
        self, destination: Node | Object | None, to_exit: str | None = None, **kwargs
    ) -> None:
        if not destination:
            return
        if not self.child:
            self.delete()
            return
        if not self.child.followers:
            self.delete()
            return
        with self.child.lock:
            for id in self.child.followers:
                follower = get(id)
                if follower:
                    success = follower[0].move_to(destination, to_exit)
                    if not success:
                        follower[0].msg(f"You can't follow {self.child.name} there!")


class FollowCommand(Command):
    key = "follow"
    desc = "Follow another character or creature."
    category = "General"


    def setup_parser(self):
        # pyrefly: ignore
        self.parser.add_argument(
            "target", type=str, nargs="?", help="Character or creature to follow."
        )

    # pyrefly: ignore
    def run(self, caller: "Object", args):
        if not args or not args.target:
            caller.msg("Follow who?")
            return

        target_name = args.target

        # Search for the object
        matches = caller.search(target_name)
        if not matches:
            loc = caller.location
            if loc and loc.access(caller, "view"):
                matches = loc.search(target_name)

        if not matches:
            caller.msg(f"Could not find '{target_name}'.")
            return
        elif len(matches) > 1:
            caller.msg(f"Multiple matches found for '{target_name}'.")
            return

        target = matches[0]

        if target == caller:
            caller.msg("You can't follow yourself!")
            return

        if not (target.is_pc or target.is_npc):
            caller.msg("You can't follow that!")
            return
        if target.no_follow and not caller.is_builder:
            caller.msg(f"{target.name} will not lead you.")
            return
        if caller.following == target.id:
            caller.msg(f"You are already following {target.name}!")
            return
        with caller.lock:
            caller.following = target.id
        with target.lock:
            target.followers.add(caller.id)
            if not target.get_scripts_by_type("FollowScript"):
                s = FollowScript.create(caller, f"FollowScript_for_{caller.id}")
                target.add_script(s)
        loc = caller.location
        if loc and target.access(caller, "view"):
            loc.msg_contents(
                f"$You(caller) $conj(start) following $you(target).",
                mapping={"caller": caller, "target": target},
                from_obj=caller,
                type="move",
            )


class NoFollowCommand(Command):
    key = "nofollow"
    category = "General"
    desc = "Disallow others from following you."
    use_parser = False

    # pyrefly: ignore
    def run(self, caller: Object, args):
        caller.no_follow = not caller.no_follow
        if caller.no_follow:
            caller.msg("You will no longer allow others to follow you.")
            with caller.lock:
                for id in caller.followers:
                    follower = get(id)
                    if follower:
                        if follower[0].is_builder:
                            continue
                        with follower[0].lock:
                            follower[0].following = None
                        if caller.access(follower[0], "view"):
                            follower[0].msg(f"{caller.get_display_name(follower[0])} is no longer leading you.")
                        if follower[0].access(caller, "view"):
                            caller.msg(f"You are no longer leading {follower[0].get_display_name(caller)}.")
                caller.followers.clear()
                for script in caller.get_scripts_by_type("FollowScript"):
                    script.delete()
        else:
            caller.msg("You will now allow others to follow you.")
