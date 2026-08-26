from atheriz.commands.base_cmd import Command
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.globals.node import Node


class GiveCommand(Command):
    key = "give"
    desc = "Give an object to someone else."

    # pyrefly: ignore
    def setup_parser(self):
        self.parser.add_argument("args", nargs="*", help="object to give, optionally 'to <target>'")

    # pyrefly: ignore
    def run(self, caller: "Object", args):
        if not args:
            caller.msg(self.print_help())
            return

        loc: "Node" | None = caller.location
        if not loc:
            caller.msg("No.")
            return

        obj_name: str | None = None
        target_name: str | None = None
        raw_args = getattr(args, "args", None)
        if isinstance(raw_args, (list, tuple)) and raw_args:
            tokens = list(raw_args)
            to_idx = None
            for i, tok in enumerate(tokens):
                if isinstance(tok, str) and tok.lower() == "to":
                    to_idx = i
                    break
            if to_idx is not None:
                obj_parts = tokens[:to_idx]
                target_parts = tokens[to_idx + 1 :]
                if not obj_parts or not target_parts:
                    caller.msg("Give it to whom?")
                    return
                obj_name = " ".join(str(p) for p in obj_parts)
                target_name = " ".join(str(p) for p in target_parts)
            else:
                if len(tokens) < 2:
                    caller.msg("Give it to whom?")
                    return
                # No 'to' — ambiguous multi-word split. Try to find valid split via search.
                # Prefer split where caller has object and loc has target.
                found_split = None
                # Try all splits, preferring object existence
                for split in range(1, len(tokens)):
                    cand_obj = " ".join(str(p) for p in tokens[:split])
                    cand_tgt = " ".join(str(p) for p in tokens[split:])
                    if cand_obj.lower() == "all":
                        # 'all' is valid virtual object
                        if loc.search(cand_tgt, looker=caller):
                            found_split = (cand_obj, cand_tgt)
                            break
                        continue
                    if caller.search(cand_obj):
                        # Check target exists (or would be multiple) — accept if any match
                        if loc.search(cand_tgt, looker=caller):
                            found_split = (cand_obj, cand_tgt)
                            break
                if found_split:
                    obj_name, target_name = found_split
                else:
                    # Fallback: last token as target (preserves 'long sword' object without 'to')
                    # But if caller.search for that fails, try first token as object
                    cand_obj_last = " ".join(str(p) for p in tokens[:-1])
                    cand_tgt_last = str(tokens[-1])
                    if cand_obj_last.lower() == "all" or caller.search(cand_obj_last):
                        obj_name = cand_obj_last
                        target_name = cand_tgt_last
                    else:
                        # Try first-token object, rest target (covers test_give_multiple_matches)
                        cand_obj_first = str(tokens[0])
                        cand_tgt_rest = " ".join(str(p) for p in tokens[1:])
                        if caller.search(cand_obj_first) or cand_obj_first.lower() == "all":
                            obj_name = cand_obj_first
                            target_name = cand_tgt_rest
                        else:
                            obj_name = cand_obj_last
                            target_name = cand_tgt_last
                if not obj_name or not target_name:
                    caller.msg("Give it to whom?")
                    return
        else:
            legacy_obj = getattr(args, "object", None)
            if isinstance(legacy_obj, str):
                obj_name = legacy_obj.strip()
                target_raw = getattr(args, "target", None)
                if isinstance(target_raw, (list, tuple)):
                    filtered = [str(p) for p in target_raw if isinstance(p, str)]
                    # Filter stray 'to' keyword if present at start (legacy tests: ["to","bob"])
                    if filtered and filtered[0].lower() == "to":
                        filtered = filtered[1:]
                    target_name = " ".join(filtered).strip()
                elif isinstance(target_raw, str):
                    t = target_raw.strip()
                    if t.lower().startswith("to "):
                        t = t[3:].strip()
                    target_name = t
                else:
                    target_name = ""
                if not obj_name or not target_name:
                    # Legacy may also use args.target == [] for missing, handled below
                    if not target_name:
                        caller.msg("Give it to whom?")
                        return
                    caller.msg(self.print_help())
                    return
            else:
                # No recognizable args
                tokens = list(raw_args or [])
                if not tokens:
                    caller.msg("Give it to whom?")
                    return
                to_idx = None
                for i, tok in enumerate(tokens):
                    if isinstance(tok, str) and tok.lower() == "to":
                        to_idx = i
                        break
                if to_idx is not None:
                    obj_parts = tokens[:to_idx]
                    target_parts = tokens[to_idx + 1 :]
                else:
                    if len(tokens) < 2:
                        caller.msg("Give it to whom?")
                        return
                    obj_parts = tokens[:-1]
                    target_parts = tokens[-1:]
                if not obj_parts or not target_parts:
                    caller.msg("Give it to whom?")
                    return
                obj_name = " ".join(str(p) for p in obj_parts)
                target_name = " ".join(str(p) for p in target_parts)

        targets = loc.search(target_name, looker=caller)
        if not targets:
            caller.msg(f"Could not find '{target_name}' here.")
            return
        if len(targets) > 1:
            caller.msg(f"Multiple matches found for '{target_name}'.")
            return
        target = targets[0]

        if target.id == caller.id:
            caller.msg("You already have that!")
            return

        if not (target.is_container or target.is_npc or target.is_pc):
            caller.msg(f"You can't give anything to {target.get_display_name(caller)}.")
            return

        if obj_name == "all":
            objs_to_give = list(caller.contents)
        else:
            objs_to_give = caller.search(obj_name)

        if not objs_to_give:
            caller.msg("You don't have that.")
            return

        given_any = False
        for obj in list(objs_to_give):
            if obj.id == target.id:
                continue
            if not obj.at_pre_give(caller, target):
                continue
            if obj.move_to(target):
                given_any = True
                caller.msg(f"You give {obj.name} to {target.name}.")
                target.msg(f"{caller.name} gives you {obj.name}.")
                loc.msg_contents(
                    f"{caller.name} gives {obj.name} to {target.name}.",
                    from_obj=caller,
                    exclude=(caller, target),
                    msg_type="give",
                )
                obj.at_give(caller, target)
            else:
                caller.msg(f"You can't give {obj.name} to {target.name}.")

        if not given_any and obj_name == "all":
            caller.msg("You have nothing to give.")
