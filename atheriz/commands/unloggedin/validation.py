from __future__ import annotations
import re
import atheriz.settings as settings

_NAME_RE = re.compile(r"^[A-Za-z0-9 _'\-]+$")

def validate_name(name: str, max_len: int) -> str | None:
    stripped = name.strip()
    if not stripped:
        return "Name cannot be empty."
    if len(stripped) < 3:
        return "Name must be at least 3 characters."
    if len(stripped) > max_len:
        return f"Name must be at most {max_len} characters."
    if "\x1b" in name or "\x00" in name:
        return "Name contains invalid characters."
    if not _NAME_RE.match(stripped):
        return "Name may only contain letters, digits, spaces, hyphens, underscores and apostrophes."
    if not any(c.isalpha() for c in stripped):
        return "Name must contain at least one letter."
    if "  " in stripped:
        return "Name cannot contain consecutive spaces."
    return None

def validate_account_name(name: str) -> str | None:
    return validate_name(name, settings.MAX_ACCOUNT_NAME_LENGTH)

def validate_character_name(name: str) -> str | None:
    return validate_name(name, settings.MAX_CHARACTER_NAME_LENGTH)

def validate_password(password: str) -> str | None:
    if not password:
        return "Password cannot be empty."
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        return f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters."
    if len(password) > settings.MAX_PASSWORD_LENGTH:
        return f"Password must be at most {settings.MAX_PASSWORD_LENGTH} characters."
    return None
