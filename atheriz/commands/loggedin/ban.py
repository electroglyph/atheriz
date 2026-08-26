from __future__ import annotations
from atheriz.commands.base_cmd import Command
from atheriz.globals.objects import ban_ip, filter_by, get, unban_ip
from atheriz import settings
from atheriz.logger import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atheriz.objects.base_obj import Object
    from atheriz.objects.base_account import Account


def _resolve_target(caller: "Object", name: str) -> "Object | None":
    """Resolve a player character by name or #id. Messages caller on failure."""
    if name.startswith("#"):
        try:
            obj_id = int(name[1:])
        except ValueError:
            caller.msg("Invalid ID format. Use #<number>.")
            return None
        results = get(obj_id)
        if not results:
            caller.msg(f"No object found with ID {obj_id}.")
            return None
        target = results[0]
        if not getattr(target, "is_pc", False):
            caller.msg("You can only ban player characters.")
            return None
        return target

    matches = filter_by(lambda x: getattr(x, "is_pc", False) and getattr(x, "name", "").lower() == name.lower())
    if not matches:
        caller.msg(f"No player character found named '{name}'.")
        return None
    if len(matches) > 1:
        caller.msg(f"Multiple matches for '{name}':")
        for m in matches:
            caller.msg(f"  #{m.id} {m.name}")
        return None
    return matches[0]


def _find_account(target: "Object") -> "Account | None":
    """Find the account owning a character. Online via session, else by scan."""
    sess = getattr(target, "session", None)
    acct = getattr(sess, "account", None) if sess else None
    if acct is not None:
        return acct
    accounts = filter_by(lambda x: getattr(x, "is_account", False) and target.id in getattr(x, "characters", []))
    return accounts[0] if accounts else None


def _target_ip(target: "Object") -> str | None:
    """Return the target's client host, or None if not connected."""
    sess = getattr(target, "session", None)
    conn = getattr(sess, "connection", None) if sess else None
    if conn is None:
        return None
    host = getattr(conn, "client_host", None)
    if not host or host == "?":
        return None
    return host


def _kick(target: "Object", reason: str | None, banned: bool) -> bool:
    sess = getattr(target, "session", None)
    conn = getattr(sess, "connection", None) if sess else None
    if conn is None:
        return True
    verb = "banned" if banned else "unbanned"
    msg = f"You have been {verb}."
    if reason:
        msg += f" Reason: {reason}"
    try:
        conn.msg(msg)
    except Exception as e:
        logger.debug(f"[Ban] Failed to message {getattr(target, 'name', '?')} ({getattr(target, 'id', '?')}): {e}")
    try:
        conn.close()
    except Exception as e:
        logger.warning(f"[Ban] Failed to close connection for {getattr(target, 'name', '?')} ({getattr(target, 'id', '?')}): {e}")
        return False
    return True


def _clear_char_reason(char: "Object") -> None:
    with char.lock:
        if "ban_reason" in vars(char):
            try:
                delattr(char, "ban_reason")
            except AttributeError:
                pass


class BanCommand(Command):
    key = "ban"
    category = "Building"
    desc = "Ban a player character, optionally their account and/or IP."
    use_parser = True

    # pyrefly: ignore
    def access(self, caller: "Object") -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("target", help="Player character to ban (name or #id).")
        self.parser.add_argument("-r", "--reason", default=None, help="Reason for the ban.")
        self.parser.add_argument(
            "--account",
            action="store_true",
            help="Ban the entire account and all its characters.",
        )
        self.parser.add_argument(
            "--ip",
            action="store_true",
            help="Also ban the target's IP (requires an online target).",
        )

    # pyrefly: ignore
    def run(self, caller: "Object", args):
        if not args or not args.target:
            caller.msg(self.print_help())
            return

        target = _resolve_target(caller, args.target)
        if target is None:
            return

        if target.privilege_level >= caller.privilege_level:
            caller.msg("You cannot ban someone of equal or higher privilege.")
            return

        reason = args.reason
        scope = "account" if args.account else "character"
        account = None
        if args.account:
            account = _find_account(target)
            if account is None:
                caller.msg(f"Could not find the account owning {target.name}; banning character only.")
                scope = "character"
            else:
                # Check all characters on the account — banning a Guest alt must not ban its Admin
                account_chars = get(account.characters) if account.characters else []
                for ch in account_chars:
                    try:
                        if getattr(ch, "privilege_level", 0) >= caller.privilege_level:
                            caller.msg("You cannot ban someone of equal or higher privilege.")
                            return
                    except Exception:
                        continue

        ip_host = None
        if args.ip:
            ip_host = _target_ip(target)

        if scope == "account" and account is not None:
            kick_targets = get(account.characters)
        else:
            kick_targets = [target]

        if scope == "account" and account is not None:
            with account.lock:
                account.is_banned = True
                account.ban_reason = reason or ""
            for c in kick_targets:
                with c.lock:
                    c.is_banned = True
                    if reason:
                        setattr(c, "ban_reason", reason)
        else:
            with target.lock:
                target.is_banned = True
                if reason:
                    setattr(target, "ban_reason", reason)

        kicked_ip = None
        if args.ip:
            if ip_host is None:
                caller.msg("Target is not online; cannot ban IP.")
            else:
                ban_ip(ip_host)
                kicked_ip = ip_host

        failed = []
        for t in kick_targets:
            if not _kick(t, reason, banned=True):
                failed.append(t.name)

        msg = f"Banned {target.name} ({scope}"
        if reason:
            msg += f", reason: {reason}"
        msg += ")."
        if kicked_ip:
            msg += f" IP {kicked_ip} banned until server restart."
        if failed:
            msg += f" Kick failed for: {', '.join(failed)}."
        caller.msg(msg)


class UnbanCommand(Command):
    key = "unban"
    category = "Building"
    desc = "Unban a player character, optionally their account and/or IP."
    use_parser = True

    # pyrefly: ignore
    def access(self, caller: "Object") -> bool:
        return caller.is_builder

    def setup_parser(self):
        self.parser.add_argument("target", help="Player character to unban (name or #id).")
        self.parser.add_argument(
            "--account",
            action="store_true",
            help="Unban the entire account and all its characters.",
        )
        self.parser.add_argument(
            "--ip",
            action="store_true",
            help="Also clear an IP ban for the target's host (requires an online target).",
        )

    # pyrefly: ignore
    def run(self, caller: "Object", args):
        if not args or not args.target:
            caller.msg(self.print_help())
            return

        target = _resolve_target(caller, args.target)
        if target is None:
            return

        if target.privilege_level >= caller.privilege_level:
            caller.msg("You cannot unban someone of equal or higher privilege.")
            return

        scope = "account" if args.account else "character"
        account = None
        if args.account:
            account = _find_account(target)
            if account is None:
                caller.msg(f"Could not find the account owning {target.name}; unbanning character only.")
                scope = "character"
            else:
                account_chars_check = get(account.characters) if account.characters else []
                for ch in account_chars_check:
                    try:
                        if getattr(ch, "privilege_level", 0) >= caller.privilege_level:
                            caller.msg("You cannot unban someone of equal or higher privilege.")
                            return
                    except Exception:
                        continue

        ip_host = None
        if args.ip:
            ip_host = _target_ip(target)

        account_chars = get(account.characters) if scope == "account" and account is not None else None

        if scope == "account" and account is not None:
            with account.lock:
                account.is_banned = False
                account.ban_reason = ""
            for c in account_chars:
                with c.lock:
                    c.is_banned = False
                _clear_char_reason(c)
        else:
            with target.lock:
                target.is_banned = False
            _clear_char_reason(target)

        if args.ip:
            if ip_host is None:
                caller.msg("Target is not online; cannot clear IP ban by reference.")
            else:
                unban_ip(ip_host)

        caller.msg(f"Unbanned {target.name} ({scope}).")
