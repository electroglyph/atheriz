#!/usr/bin/env python3
"""Build the frontend and stage it into an AtheriZ runtime web directory.

The script uses only the Python standard library. By default it first runs
``npm run build`` (so Node.js must be on PATH) and then stages the resulting
``dist`` directory. Pass ``--no-build`` to stage an already-built ``dist``
without touching npm.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DIST_ROOT = PROJECT_ROOT / "dist"
PACKAGE_STATIC_ROOT = PROJECT_ROOT.parent / "atheriz" / "web" / "static"


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Missing build directory: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Missing build file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _patch_html_assets(html_path: Path) -> None:
    if not html_path.is_file():
        return
    try:
        text = html_path.read_text(encoding="utf-8")
    except Exception:
        return
    original = text
    text = text.replace('href="/assets/', 'href="/static/assets/')
    text = text.replace('src="/assets/', 'src="/static/assets/')
    text = text.replace('url("/assets/', 'url("/static/assets/')
    text = text.replace("url('/assets/", "url('/static/assets/")
    text = text.replace('href="/fonts/', 'href="/static/fonts/')
    text = text.replace('src="/fonts/', 'src="/static/fonts/')
    text = text.replace('href="/chafa.wasm', 'href="/static/chafa.wasm')
    text = text.replace('src="/chafa.wasm', 'src="/static/chafa.wasm')
    text = text.replace('"/chafa.wasm"', '"/static/chafa.wasm"')
    text = text.replace("'/chafa.wasm'", "'/static/chafa.wasm'")
    text = text.replace('"/gfonts/', '"/static/gfonts/')
    text = text.replace("'/gfonts/", "'/static/gfonts/")
    if text != original:
        html_path.write_text(text, encoding="utf-8")


def clean_generated_output(
    static_root: Path, *, remove_legacy_webclient: bool = False
) -> None:
    """Remove only paths owned by this build, not arbitrary game assets."""
    for relative in (
        "assets",
        "atheriz_draw",
        "chafa.wasm",
        "gfonts",
    ):
        remove_path(static_root / relative)
    if remove_legacy_webclient:
        remove_path(static_root / "webclient")
    else:
        remove_path(static_root / "webclient" / "index.html")


def deploy(
    static_root: Path, clean: bool, *, remove_legacy_webclient: bool = False
) -> None:
    if not DIST_ROOT.is_dir():
        raise FileNotFoundError(
            f"Build output not found at {DIST_ROOT}; run `npm run build` first"
        )

    static_root.mkdir(parents=True, exist_ok=True)
    if clean:
        clean_generated_output(
            static_root, remove_legacy_webclient=remove_legacy_webclient
        )

    copy_tree(DIST_ROOT / "assets", static_root / "assets")
    if (PROJECT_ROOT / "fonts").is_dir():
        copy_tree(PROJECT_ROOT / "fonts", static_root / "fonts")
    copy_file(
        DIST_ROOT / "webclient" / "index.html",
        static_root / "webclient" / "index.html",
    )
    copy_file(
        DIST_ROOT / "index.html",
        static_root / "atheriz_draw" / "index.html",
    )
    chafa_src = DIST_ROOT / "chafa.wasm"
    if chafa_src.is_file():
        copy_file(chafa_src, static_root / "chafa.wasm")
    elif not (static_root / "chafa.wasm").exists():
        candidates = list((DIST_ROOT / "assets").glob("chafa*.wasm"))
        if candidates:
            copy_file(candidates[0], static_root / "chafa.wasm")
    gfonts_src = DIST_ROOT / "gfonts"
    if gfonts_src.is_dir():
        copy_tree(gfonts_src, static_root / "gfonts")

    for html_name in ["webclient/index.html", "atheriz_draw/index.html"]:
        _patch_html_assets(static_root / html_name)

    print(f"Deployed frontend artifacts to {static_root}")
    print(f"  webclient: {static_root / 'webclient' / 'index.html'}")
    print(f"  draw:     {static_root / 'atheriz_draw' / 'index.html'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        choices=("package", "game"),
        default="package",
        help="stage into the installed package source or a game web root",
    )
    parser.add_argument(
        "--web-root",
        type=Path,
        help="AtheriZ game web directory for the `game` target",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="preserve generated output from an earlier deployment",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="stage the existing dist/ directory without running npm run build",
    )
    return parser.parse_args()


def build_frontend() -> None:
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit(
            "npm was not found on PATH; install Node.js or pass --no-build "
            "to stage an already-built dist/"
        )
    subprocess.run([npm, "run", "build"], cwd=PROJECT_ROOT, check=True, shell=(os.name == "nt"))


def main() -> int:
    args = parse_args()
    if not args.no_build:
        build_frontend()
    if args.target == "package":
        static_root = PACKAGE_STATIC_ROOT
    else:
        if args.web_root is None:
            raise SystemExit("The `game` target requires --web-root <game/web>")
        static_root = args.web_root.resolve() / "static"
    deploy(
        static_root,
        clean=not args.no_clean,
        remove_legacy_webclient=args.target == "package",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
