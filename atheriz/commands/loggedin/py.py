from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object


class PyCommand(Command):
    key = "py"
    desc = "Eval a Python expression and echo the result."
    category = "Building"
    use_parser = False

    # pyrefly: ignore
    def access(self, caller: Object) -> bool:
        return caller.is_superuser

    # pyrefly: ignore
    def run(self, caller: Object, args: str):
        if not args or not args.strip():
            caller.msg("Usage: py <expression>")
            return
        try:
            result = eval(args.strip())
            caller.msg(str(result))
        except SyntaxError:
            try:
                exec(args.strip())
                caller.msg("(no return value)")
            except Exception as e:
                caller.msg(f"Error: {type(e).__name__}: {e}")
        except Exception as e:
            caller.msg(f"Error: {type(e).__name__}: {e}")
