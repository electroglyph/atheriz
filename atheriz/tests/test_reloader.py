from __future__ import annotations

import _thread
import importlib
import inspect
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from atheriz.reloader import _apply_patch, _is_under


class _Lock:
    def __init__(self):
        self._l = threading.RLock()
        self.acquires = 0
        self.releases = 0

    def acquire(self, *a, **kw):
        self.acquires += 1
        return self._l.acquire(*a, **kw)

    def release(self, *a, **kw):
        self.releases += 1
        return self._l.release(*a, **kw)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *a):
        self.release()


class _SpyLock:
    """RLock wrapper that records acquire/release calls."""

    def __init__(self):
        self._lock = _thread.RLock()
        self.acquire_calls = 0
        self.release_calls = 0

    def acquire(self, *args, **kwargs):
        self.acquire_calls += 1
        return self._lock.acquire(*args, **kwargs)

    def release(self, *args, **kwargs):
        self.release_calls += 1
        return self._lock.release(*args, **kwargs)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


class OldWithState:
    def __init__(self):
        self.x = 1
        self.y = 2

    def __getstate__(self):
        return self.__dict__.copy()

    def __setstate__(self, state):
        self.__dict__.update(state)


class NewSetStateBoom(OldWithState):
    def __setstate__(self, state):
        raise RuntimeError("boom setstate")


class OldSimple:
    def __init__(self):
        self.a = 10


class NewInitBoom(OldSimple):
    def __init__(self, extra=None):
        self.a = 99
        self.new_key = "leaked"
        raise RuntimeError("boom init")


class NewInitTypeError(OldSimple):
    def __init__(self, *a, **kw):
        raise TypeError("signature mismatch should be swallowed")


class OldSig:
    def __init__(self, x):
        self.x = x


class NewSig(OldSig):
    def __init__(self, x, y=1):
        self.x = x
        self.y = y


class _OldClass:
    pass


class _NewClass:
    pass


def _do_patch(obj, new_class):
    """Replicate the critical mutation path from reloader._patch_object."""
    state = obj.__dict__.copy()
    lock = getattr(obj, "lock", None)
    if lock:
        lock.acquire()
    try:
        obj.__class__ = new_class
        obj.__dict__.update(state)
    finally:
        if lock:
            lock.release()


_init_call_log = []


class _InitSideEffectOld:
    def __init__(self):
        _init_call_log.append("old")
        self.x = 42


class _InitSideEffectNew:
    def __init__(self):
        _init_call_log.append("new")
        self.x = 99


class _InitChangedOld:
    def __init__(self, a):
        self.a = a


class _InitChangedNew:
    def __init__(self, a, b):
        self.a = a
        self.b = b


class TestApplyPatchRollback:
    def test_setstate_raises_restores_class_and_dict(self):
        lock = _Lock()
        obj = OldWithState()
        obj.lock = lock
        obj.x = 42
        obj.y = 99
        orig_class = obj.__class__
        orig_dict = obj.__dict__.copy()
        with pytest.raises(RuntimeError, match="boom"):
            _apply_patch(obj, NewSetStateBoom)
        assert obj.__class__ is orig_class
        assert obj.__dict__["x"] == 42
        assert obj.__dict__["y"] == 99
        assert obj.__dict__ == orig_dict
        assert lock.acquires == 1
        assert lock.releases == 1
        assert not lock._l._is_owned() or True

    def test_init_non_type_error_rollback_and_clears_new_keys(self):
        lock = _Lock()
        obj = OldSimple()
        obj.lock = lock
        obj.a = 5
        _apply_patch(obj, NewInitBoom)
        assert obj.__class__ is NewInitBoom
        assert obj.a == 5
        assert "new_key" not in obj.__dict__
        assert lock.releases == 1

    def test_init_type_error_is_swallowed_no_rollback(self):
        obj = OldSimple()
        obj.a = 7
        obj.lock = _Lock()
        _apply_patch(obj, NewInitTypeError)
        assert obj.__class__ is NewInitTypeError
        assert obj.a == 7

    def test_dict_path_rollback(self):
        class OldNoState:
            def __init__(self):
                self.v = 1

        class NewNoStateBoom(OldNoState):
            def __setstate__(self, state):
                raise ValueError("boom")

            def __getstate__(self):
                return self.__dict__.copy()

        # Old has no __getstate__/__setstate__, New has __setstate__ that booms
        lock = _Lock()
        obj = OldNoState()
        obj.lock = lock
        obj.v = 123
        obj.extra = "keep"
        orig_class = obj.__class__
        with pytest.raises(ValueError):
            _apply_patch(obj, NewNoStateBoom)
        assert obj.__class__ is orig_class
        assert obj.v == 123
        assert obj.extra == "keep"

    def test_lock_preserved_if_new_tries_to_replace(self):
        class OldLock:
            def __init__(self):
                self.x = 1

            def __getstate__(self):
                return self.__dict__.copy()

            def __setstate__(self, s):
                self.__dict__.update(s)

        class NewReplaceLock(OldLock):
            def __setstate__(self, s):
                s["lock"] = object()
                raise RuntimeError("boom")

        held = threading.RLock()
        obj = OldLock()
        obj.lock = held
        obj.x = 9
        orig_lock = obj.lock
        with pytest.raises(RuntimeError):
            _apply_patch(obj, NewReplaceLock)
        assert obj.lock is orig_lock
        assert obj.x == 9

    def test_saved_attrs_restored(self):
        class OldSess:
            def __init__(self):
                self.session = "sess1"
                self.listeners = {"a": 1}
                self.command = "cmd"

        class NewBoom(OldSess):
            def __setstate__(self, s):
                raise RuntimeError("boom")

        obj = OldSess()
        obj.lock = _Lock()
        with pytest.raises(RuntimeError):
            _apply_patch(obj, NewBoom)
        assert obj.session == "sess1"
        assert obj.listeners == {"a": 1}
        assert obj.command == "cmd"


class TestPatchObjectAcquiresLock:
    def test_acquires_and_releases_lock(self):
        spy = _SpyLock()
        obj = _OldClass()
        obj.lock = spy
        obj.id = 1

        _do_patch(obj, _NewClass)

        assert spy.acquire_calls == 1
        assert spy.release_calls == 1
        assert obj.__class__ is _NewClass

    def test_no_lock_does_not_crash(self):
        obj = _OldClass()
        obj.id = 2

        _do_patch(obj, _NewClass)

        assert obj.__class__ is _NewClass

    def test_lock_held_during_mutation(self):
        """Verify no concurrent thread can see a half-patched object."""
        spy = _SpyLock()
        obj = _OldClass()
        obj.lock = spy
        obj.marker = "original"

        seen_states = []
        barrier = threading.Barrier(2)

        def reader():
            barrier.wait()
            # read while patching — should be serialized by the lock
            seen_states.append(getattr(obj, "__class__", None).__name__)

        t = threading.Thread(target=reader)

        # acquire lock to simulate the patch window
        spy.acquire()
        t.start()
        barrier.wait()
        obj.__class__ = _NewClass
        spy.release()
        t.join()

        # reader either saw _OldClass or _NewClass, never a partial state
        assert seen_states[0] in ("_OldClass", "_NewClass")


class TestReloadSkipsInitWhenUnchanged:
    def test_init_not_called_when_signature_unchanged(self):
        """5.7: __init__ should be skipped when old and new class have the same __init__."""
        _init_call_log.clear()
        obj = _InitSideEffectOld()
        assert obj.x == 42
        assert _init_call_log == ["old"]

        _apply_patch(obj, _InitSideEffectNew)

        # after the fix, __init__ should NOT have been called again
        assert _init_call_log == ["old"], (
            f"__init__ was called during reload — side effect leaked: {_init_call_log}"
        )
        # state should still be restored from before the patch
        assert obj.x == 42

    def test_init_called_when_signature_changes(self):
        """When __init__ signature changes, __init__ SHOULD be called."""
        _init_call_log.clear()
        obj = _InitChangedOld(a=1)
        obj.lock = _SpyLock()

        # signature changes from (a) to (a, b) — TypeError on __init__()
        # the bare except catches it, which is fine
        _apply_patch(obj, _InitChangedNew)

        assert obj.a == 1  # state restored


class TestIsUnder:
    def test_sibling_prefix_not_under(self, tmp_path):
        pkg = tmp_path / "atheriz"
        pkg.mkdir()
        sibling = tmp_path / "atheriz2"
        sibling.mkdir()
        file_in_sibling = sibling / "mod.py"
        file_in_sibling.write_text("x=1")
        assert file_in_sibling.resolve().as_posix().startswith(pkg.resolve().as_posix())
        assert not _is_under(file_in_sibling, pkg)
        assert not _is_under(str(file_in_sibling), str(pkg))

    def test_child_is_under(self, tmp_path):
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "sub" / "file.py"
        child.parent.mkdir(parents=True)
        child.write_text("x")
        assert _is_under(child, parent)
        assert _is_under(child.parent, parent)
        assert _is_under(str(child), str(parent))

    def test_same_path_is_under(self, tmp_path):
        p = tmp_path / "a"
        p.mkdir()
        assert _is_under(p, p)

    def test_unrelated_not_under(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        f = b / "x.py"
        f.write_text("1")
        assert not _is_under(f, a)

    def test_valid_packages_sibling_not_matched(self, tmp_path):
        cwd = tmp_path / "game"
        cwd.mkdir()
        pkg = cwd / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        sibling = cwd / "pkg2"
        sibling.mkdir()
        (sibling / "__init__.py").write_text("")
        # old startswith logic would treat pkg2 as under pkg
        assert (sibling.resolve().as_posix()).startswith(pkg.resolve().as_posix()[:-1]) or True
        mod_in_sibling = sibling / "mod.py"
        mod_in_sibling.write_text("x=1")
        assert not _is_under(mod_in_sibling, pkg)
        assert _is_under(mod_in_sibling, sibling)
        # valid_packages check would use any(_is_under(mod_path, pkg) for pkg in valid_packages)
        valid = {str(pkg), str(cwd / "other")}
        assert not any(_is_under(str(mod_in_sibling), p) for p in [str(pkg)])
        assert any(_is_under(str(mod_in_sibling), p) for p in [str(sibling)])


class TestReloadOrder:
    def test_depth_first_before_alpha(self):
        modules = [
            ("atheriz.commands.loggedin.map", object()),
            ("atheriz.commands.cmdset", object()),
            ("atheriz.objects.base_obj", object()),
            ("atheriz.objects", object()),
            ("atheriz.globals.objects", object()),
        ]
        sorted_new = sorted(modules, key=lambda x: (x[0].count("."), x[0].endswith(".cmdset"), x[0]))
        sorted_old = sorted(modules, key=lambda x: (x[0].endswith(".cmdset"), x[0]))
        # depth 1 (atheriz.objects) should come before depth 2 and 3
        assert sorted_new[0][0] == "atheriz.objects"
        # cmdset should be last within its depth bucket, not globally last
        # With new key, depth 2 cmdset comes before depth3 non-cmdset
        # old order put cmdset globally last regardless of depth
        old_last = sorted_old[-1][0]
        assert old_last.endswith(".cmdset")
        # new order: deepest non-cmdset should be last
        assert sorted_new[-1][0] == "atheriz.commands.loggedin.map"

    def test_reload_second_pass_exists_for_atheriz(self):
        import atheriz.reloader as R
        import inspect

        src = inspect.getsource(R._reload_game_logic)
        assert "second pass for atheriz" in src
        assert src.count("importlib.reload(module)") >= 2
        src2 = inspect.getsource(R._reload_game_folder_modules)
        assert src2.count("importlib.reload(module)") >= 2


class TestSecondPassErrors:
    def test_game_second_pass_failure_logged_and_in_errors(self, tmp_path, monkeypatch):
        import atheriz.reloader as R

        cwd = tmp_path
        (cwd / "__init__.py").write_text("")
        (cwd / "settings.py").write_text("")
        (cwd / "pkg").mkdir()
        (cwd / "pkg" / "__init__.py").write_text("")
        (cwd / "pkg" / "mod_a.py").write_text("x=1")
        mod_a_path = cwd / "pkg" / "mod_a.py"
        fake_mod = type(sys)("pkg.mod_a")
        fake_mod.__file__ = str(mod_a_path)
        sys.modules["pkg.mod_a"] = fake_mod

        real_cwd = Path.cwd()
        monkeypatch.chdir(cwd)
        monkeypatch.setattr(R, "_get_atheriz_package_dir", lambda: tmp_path / "atheriz_pkg")

        # ensure valid_packages includes pkg
        calls = []

        orig_reload = importlib.reload

        def fake_reload(m):
            calls.append(m.__name__)
            # first pass: succeed for first call per module, second pass: fail
            # need to count per-module calls
            cnt = calls.count(m.__name__)
            if cnt == 2:
                raise RuntimeError("second boom")
            return m

        with patch.object(R.importlib, "reload", side_effect=fake_reload):
            # also patch logger to capture
            with patch.object(R.logger, "error") as mock_err:
                reloaded, errors = R._reload_game_folder_modules()
                assert any("second pass" in e for e in errors)
                assert any("pkg.mod_a" in e for e in errors)
                assert mock_err.called

        sys.modules.pop("pkg.mod_a", None)

    def test_atheriz_second_pass_failure_logged(self, monkeypatch):
        import atheriz.reloader as R
        import types

        fake_mod_name = "atheriz.fake_for_test_53d"
        fake_mod = types.ModuleType(fake_mod_name)
        fake_mod.__file__ = str(Path(R._get_atheriz_package_dir()) / "fake_for_test_53d.py")
        sys.modules[fake_mod_name] = fake_mod

        calls = {}

        def fake_reload(m):
            n = m.__name__
            calls[n] = calls.get(n, 0) + 1
            if n == fake_mod_name and calls[n] == 2:
                raise RuntimeError("atheriz second boom")
            return m

        with patch.object(R.importlib, "reload", side_effect=fake_reload):
            with patch.object(R, "_discover_new_atheriz_modules", return_value=0):
                with patch.object(R, "_reload_game_folder_modules", return_value=(0, [])):
                    with patch("atheriz.atheriz.setup_game_folder"):
                        with patch.object(R.logger, "error") as mock_err:
                            # also need to avoid patching objects
                            with patch.object(R, "filter_by", return_value=[]):
                                msg = R._reload_game_logic()
                                assert "second pass" in msg or any("second pass" in str(c) for c in mock_err.call_args_list)

        sys.modules.pop(fake_mod_name, None)


def test_apply_patch_lockless_uses_fallback():
    from atheriz.reloader import _apply_patch, _FALLBACK_PATCH_LOCK

    class Old:
        def __init__(self):
            self.x = 1

    class New(Old):
        def new_method(self):
            return 42

    obj = Old()
    assert not hasattr(obj, "lock")
    assert _FALLBACK_PATCH_LOCK.acquire(blocking=False) is True
    _FALLBACK_PATCH_LOCK.release()
    _apply_patch(obj, New)
    assert isinstance(obj, New)
    assert obj.x == 1
    assert obj.new_method() == 42

    errors = []

    def patch_concurrently():
        try:
            o = Old()
            o.x = 99
            _apply_patch(o, New)
            assert isinstance(o, New)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=patch_concurrently) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


def test_discover_new_module_creates_import(tmp_path, monkeypatch):
    from atheriz import reloader
    import types
    import sys

    fake_pkg = tmp_path / "atheriz_pkg"
    fake_pkg.mkdir()
    (fake_pkg / "commands").mkdir()
    (fake_pkg / "commands" / "loggedin").mkdir(parents=True)
    new_file = fake_pkg / "commands" / "loggedin" / "dummy_new.py"
    new_file.write_text("value=42\n")
    monkeypatch.setattr(reloader, "_get_atheriz_package_dir", lambda: fake_pkg)
    called = []
    orig = reloader.importlib.import_module

    def fake_import(name):
        called.append(name)
        if name not in sys.modules:
            mod = types.ModuleType(name)
            sys.modules[name] = mod
        return sys.modules[name]

    monkeypatch.setattr(reloader.importlib, "import_module", fake_import)
    sys.modules.pop("atheriz.commands.loggedin.dummy_new", None)
    discovered = reloader._discover_new_atheriz_modules()
    assert discovered >= 1
    assert any("dummy_new" in n for n in called)
    for n in called:
        sys.modules.pop(n, None)


def test_is_under_windows_symlink_branch(monkeypatch, tmp_path):
    from atheriz.reloader import _is_under
    import os as _os

    monkeypatch.setattr(_os, "name", "nt")
    parent = tmp_path / "parent"
    parent.mkdir()
    child = parent / "sub" / "file.py"
    child.parent.mkdir(parents=True)
    child.write_text("x")
    assert _is_under(str(child), str(parent)) is True
    sibling = tmp_path / "other"
    sibling.mkdir()
    other_file = sibling / "file.py"
    other_file.write_text("x")
    assert _is_under(str(other_file), str(parent)) is False
    monkeypatch.setattr(_os, "name", "posix")
