from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class QuellCommand(Command):
    key = "quell"
    aliases = ["q"]
    category = "Building"
    desc = "Quell your privileges to the level of a normal player."
    use_parser = False

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    # pyrefly: ignore
    def run(self, caller: Object, args):
        with caller.lock:
            q = caller.quelled
        if q:
            caller.msg(f"You are already quelled!")
        else:
            caller.quelled = True
            caller.msg(f"You are now quelled.")


class UnquellCommand(Command):
    key = "unquell"
    aliases = ["unq"]
    category = "Building"
    desc = "Unquell your privileges."
    use_parser = False

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_builder

    # pyrefly: ignore
    def run(self, caller: Object, args):
        with caller.lock:
            q = caller.quelled
        if not q:
            caller.msg(f"You are not quelled!")
        else:
            caller.quelled = False
            caller.msg(f"You are now unquelled.")
