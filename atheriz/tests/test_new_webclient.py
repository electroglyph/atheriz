from pathlib import Path

from atheriz.new import copy_web_folder


def test_copy_web_folder_copies_compiled_webclient(tmp_path: Path):
    source = tmp_path / "package" / "web"
    compiled_index = source / "static" / "webclient" / "index.html"
    compiled_index.parent.mkdir(parents=True)
    compiled_index.write_text(
        '<script type="module" src="/assets/webclient.js"></script>'
    )
    draw_index = source / "static" / "atheriz_draw" / "index.html"
    draw_index.parent.mkdir(parents=True)
    draw_index.write_text("draw")

    destination = tmp_path / "game"
    copy_web_folder(destination, source)

    assert (destination / "web" / "static" / "webclient" / "index.html").read_text() == (
        compiled_index.read_text()
    )
    assert (destination / "web" / "static" / "atheriz_draw" / "index.html").read_text() == (
        "draw"
    )


def test_copy_web_folder_overwrites_compiled_webclient_index(tmp_path: Path):
    source = tmp_path / "package" / "web"
    compiled_index = source / "static" / "webclient" / "index.html"
    compiled_index.parent.mkdir(parents=True)
    compiled_index.write_text("new client")

    destination = tmp_path / "game"
    old_index = destination / "web" / "static" / "webclient" / "index.html"
    old_index.parent.mkdir(parents=True)
    old_index.write_text("old client")

    copy_web_folder(destination, source)

    assert old_index.read_text() == "new client"


def test_copy_web_folder_uses_packaged_compiled_webclient(tmp_path: Path):
    copy_web_folder(tmp_path)

    webclient_index = tmp_path / "web" / "static" / "webclient" / "index.html"
    draw_index = tmp_path / "web" / "static" / "atheriz_draw" / "index.html"

    assert webclient_index.is_file()
    assert "/assets/" in webclient_index.read_text()
    assert draw_index.is_file()
