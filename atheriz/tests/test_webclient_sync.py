"""Tests for atheriz.atheriz — webclient sync check helpers."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from atheriz import settings
from atheriz.atheriz import (
    check_webclient_sync,
    format_webclient_sync_warning,
)


_EMPTY_SUMMARY = {
    "templates": {"missing": [], "different": [], "extra": []},
    "static": {"missing": [], "different": [], "extra": []},
}


def _make_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


ENGINE_FILES = {
    "templates": {
        "webclient/index.html": "<html>server</html>",
        "webclient/fonts/font.css": "css",
    },
    "static": {
        "webclient/js/webclient.js": "js()",
        "webclient/fonts/font.ttf": "binary",
        "webclient/audio/tone.mp3": "mp3",
    },
}


def _engine(tmp_path: Path) -> Path:
    engine = tmp_path / "engine" / "web"
    for area, files in ENGINE_FILES.items():
        _make_tree(engine / area, files)
    return engine


def _game(tmp_path: Path, files: dict[str, dict[str, str]] | None = None) -> Path:
    game = tmp_path / "game"
    for area, area_files in (files or {}).items():
        _make_tree(game / "web" / area, area_files)
    return game


class TestCheckWebclientSync:
    def test_identical_trees_returns_none(self, tmp_path):
        engine = _engine(tmp_path)
        game = _game(tmp_path, ENGINE_FILES)
        summary = check_webclient_sync(game, engine_web=engine)
        assert summary is None

    def test_game_without_web_dir_returns_none(self, tmp_path):
        engine = _engine(tmp_path)
        game = tmp_path / "plain"
        game.mkdir()
        assert check_webclient_sync(game, engine_web=engine) is None

    def test_respects_sync_check_setting(self, tmp_path, monkeypatch):
        engine = _engine(tmp_path)
        game = _game(tmp_path, ENGINE_FILES)
        monkeypatch.setattr(settings, "WEBCLIENT_SYNC_CHECK", False)
        assert check_webclient_sync(game, engine_web=engine) is None

    def test_missing_different_extra_classified(self, tmp_path):
        engine = _engine(tmp_path)
        game = _game(
            tmp_path,
            {
                "templates": {
                    "webclient/index.html": "<html>game</html>",
                    "webclient/custom.html": "custom",
                },
                "static": {},
            },
        )
        summary = check_webclient_sync(game, engine_web=engine)
        t = summary["templates"]
        assert [str(p) for p in t["different"]] == ["index.html"]
        assert [str(p) for p in t["missing"]] == ["fonts/font.css"]
        assert [str(p) for p in t["extra"]] == ["custom.html"]
        s = summary["static"]
        assert [str(p) for p in s["missing"]] == sorted(
            ["js/webclient.js", "fonts/font.ttf", "audio/tone.mp3"]
        )

    def test_empty_game_web_dir_flags_everything_missing(self, tmp_path):
        engine = _engine(tmp_path)
        game = _game(tmp_path)
        game_webclient = game / "web" / "static" / "webclient"
        game_webclient.mkdir(parents=True)
        summary = check_webclient_sync(game, engine_web=engine)
        assert summary is not None
        assert len(summary["templates"]["missing"]) == 2
        assert summary["templates"]["different"] == []
        assert summary["templates"]["extra"] == []
        assert len(summary["static"]["missing"]) == 3


class TestFormatWebclientSyncWarning:
    def test_posix_copy_commands(self, tmp_path):
        engine = _engine(tmp_path)
        game = _game(tmp_path, ENGINE_FILES)
        summary = _EMPTY_SUMMARY
        msg = format_webclient_sync_warning(summary, game, os_name="posix", engine_web=engine)
        assert "cp -r" in msg
        assert 'cp -r "../engine/web/templates/webclient" "web/templates/"' in msg
        assert 'cp -r "../engine/web/static/webclient" "web/static/"' in msg

    def test_windows_xcopy_commands(self, tmp_path):
        engine = _engine(tmp_path)
        game = _game(tmp_path, ENGINE_FILES)
        msg = format_webclient_sync_warning(
            _EMPTY_SUMMARY, game, os_name="nt", engine_web=engine
        )
        assert "xcopy" in msg
        assert '"web\\templates\\webclient\\" /E /Y /I' in msg
        assert '"web\\static\\webclient\\" /E /Y /I' in msg

    def test_summary_line_and_examples(self, tmp_path):
        engine = _engine(tmp_path)
        game = _game(
            tmp_path,
            {
                "templates": {
                    "webclient/index.html": "<html>changed</html>",
                    "webclient/new.html": "new",
                },
                "static": {},
            },
        )
        summary = check_webclient_sync(game, engine_web=engine)
        msg = format_webclient_sync_warning(summary, game, os_name="posix", engine_web=engine)
        assert "1 modified" in msg
        assert "1 missing" in msg
        assert "1 extra" in msg
        assert "index.html" in msg

    def test_identical_summary_prints_only_header_and_commands(self, tmp_path):
        engine = _engine(tmp_path)
        game = _game(tmp_path, ENGINE_FILES)
        msg = format_webclient_sync_warning(
            _EMPTY_SUMMARY, game, os_name="posix", engine_web=engine
        )
        assert "modified" not in msg
        assert "missing" not in msg
        assert "extra" not in msg


def test_compiled_webclient_ignores_preserved_legacy_files(tmp_path):
    engine = tmp_path / "engine" / "web"
    _make_tree(
        engine / "templates",
        ENGINE_FILES["templates"],
    )
    _make_tree(
        engine / "static",
        {"webclient/index.html": "compiled"},
    )
    game = _game(
        tmp_path,
        {
            "templates": ENGINE_FILES["templates"],
            "static": {
                "webclient/index.html": "compiled",
                "webclient/js/webclient.js": "legacy",
                "webclient/css/xterm.css": "legacy",
            },
        },
    )

    assert check_webclient_sync(game, engine_web=engine) is None


def test_compiled_webclient_warning_uses_deploy_command(tmp_path):
    engine = tmp_path / "engine" / "web"
    _make_tree(
        engine / "templates",
        ENGINE_FILES["templates"],
    )
    _make_tree(
        engine / "static",
        {"webclient/index.html": "compiled"},
    )
    game = _game(
        tmp_path,
        {
            "templates": ENGINE_FILES["templates"],
            "static": {"webclient/index.html": "stale"},
        },
    )

    summary = check_webclient_sync(game, engine_web=engine)
    msg = format_webclient_sync_warning(summary, game, engine_web=engine)

    assert "deploy.py" in msg
    assert f'game --web-root "{game / "web"}"' in msg
    assert "npm run" not in msg
    assert "cp -r" not in msg
