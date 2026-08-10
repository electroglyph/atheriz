#!/usr/bin/env python3
"""Stage the built frontend into an AtheriZ runtime web directory.

This script intentionally uses only the Python standard library. It copies an
already-built ``dist`` directory; building the frontend remains an npm/Vite
step performed before this script runs.
"""

from __future__ import annotations

import argparse
import shutil
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


def clean_generated_output(static_root: Path) -> None:
    """Remove only paths owned by this build, not arbitrary game assets."""
    for relative in (
        "assets",
        "atheriz_draw",
        "chafa.wasm",
        "gfonts",
    ):
        remove_path(static_root / relative)
    remove_path(static_root / "webclient" / "index.html")


def deploy(static_root: Path, clean: bool) -> None:
    if not DIST_ROOT.is_dir():
        raise FileNotFoundError(
            f"Build output not found at {DIST_ROOT}; run `npm run build` first"
        )

    static_root.mkdir(parents=True, exist_ok=True)
    if clean:
        clean_generated_output(static_root)

    copy_tree(DIST_ROOT / "assets", static_root / "assets")
    copy_tree(PROJECT_ROOT / "fonts", static_root / "fonts")
    copy_file(
        DIST_ROOT / "webclient" / "index.html",
        static_root / "webclient" / "index.html",
    )
    copy_file(
        DIST_ROOT / "index.html",
        static_root / "atheriz_draw" / "index.html",
    )
    copy_file(DIST_ROOT / "chafa.wasm", static_root / "chafa.wasm")
    copy_tree(DIST_ROOT / "gfonts", static_root / "gfonts")
    copy_file(
        DIST_ROOT / "art.ans",
        static_root / "atheriz_draw" / "art.ans",
    )

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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.target == "package":
        static_root = PACKAGE_STATIC_ROOT
    else:
        if args.web_root is None:
            raise SystemExit("The `game` target requires --web-root <game/web>")
        static_root = args.web_root.resolve() / "static"
    deploy(static_root, clean=not args.no_clean)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
