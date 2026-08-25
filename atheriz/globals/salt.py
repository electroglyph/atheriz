from __future__ import annotations
import os
import secrets
import threading
from atheriz import settings
from pathlib import Path
from atheriz.utils import is_in_game_folder

_SALT: str | None = None
_SALT_LOCK = threading.Lock()


def get_salt() -> str:
    """
    Get the global salt value.
    If save/salt.txt exists, cache and return that value.
    Otherwise generate a random 64-bit number, write it to salt.txt, cache and return.
    """
    global _SALT
    if _SALT is not None:
        return _SALT

    with _SALT_LOCK:
        if _SALT is not None:
            return _SALT

        secret_path = Path(settings.SECRET_PATH)
        salt_file = secret_path / "salt.txt"

        # Only create/read salt.txt if it's an absolute path (meaning it was explicitly set,
        # likely by atheriz new) or if we are clearly in a game folder.
        if secret_path.is_absolute() or is_in_game_folder():
            if salt_file.exists():
                try:
                    salt_file.chmod(0o600)
                except OSError:
                    pass
                raw = salt_file.read_text(encoding="utf-8").strip()
                if not raw:
                    raise RuntimeError(
                        f"Corrupt salt file {salt_file}: empty/whitespace. "
                        f"Restore secret/salt.txt from backup; deleting it invalidates all password hashes."
                    )
                _SALT = raw
                return _SALT

            salt_val = str(secrets.randbits(64))
            salt_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                salt_file.parent.chmod(0o700)
            except OSError:
                pass
            try:
                fd = os.open(str(salt_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    os.write(fd, salt_val.encode())
                finally:
                    os.close(fd)
            except FileExistsError:
                raw = salt_file.read_text(encoding="utf-8").strip()
                if not raw:
                    raise RuntimeError(f"Corrupt salt file {salt_file} after concurrent create.")
                _SALT = raw
                return _SALT
            except OSError:
                salt_file.write_text(salt_val, encoding="utf-8")
                try:
                    salt_file.chmod(0o600)
                except OSError:
                    pass
            _SALT = salt_val
            return _SALT

        raise RuntimeError(
            f"Cannot determine salt: SECRET_PATH ({settings.SECRET_PATH}) is not absolute "
            "and we're not in a game folder. Run 'atheriz new' or set SECRET_PATH."
        )
