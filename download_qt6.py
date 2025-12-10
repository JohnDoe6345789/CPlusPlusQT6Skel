#!/usr/bin/env python3
"""
Download prebuilt Qt 6 binaries for C++ development using the aqtinstall tool.

Typical usage (downloads Qt 6.7.2 MSVC 2019 x64 into third_party/qt6):
    python download_qt6.py

Customize the version/arch/output directory:
    python download_qt6.py --qt-version 6.6.3 --compiler win64_msvc2019_64 --output-dir vendor/qt6

List available versions: https://ddouthitt.medium.com/aqtinstall
More docs: https://aqtinstall.readthedocs.io/
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import Iterable, List


DEFAULT_MODULES = [
    # Core Qt needed for GUI apps
    "qtbase",
    "qtdeclarative",
    "qttools",
    "qtshadertools",
    # Commonly used extras; remove if you want a smaller download
    "qtimageformats",
    "qtmultimedia",
    "qt5compat",
    "qtquick3d",
    "qtquickcontrols",
]


def run(cmd: List[str], *, dry_run: bool) -> None:
    """Print and execute a command."""
    print(" ".join(cmd))
    if dry_run:
        return
    subprocess.check_call(cmd)


def ensure_aqtinstall(*, dry_run: bool) -> None:
    """Install aqtinstall if missing so we can fetch Qt archives."""
    if shutil.which("aqt"):
        return

    cmd = [sys.executable, "-m", "pip", "install", "aqtinstall>=3.1.0"]
    print("aqtinstall not found; installing it with pip...")
    run(cmd, dry_run=dry_run)


def build_install_qt_cmd(args: argparse.Namespace) -> List[str]:
    cmd = [
        sys.executable,
        "-m",
        "aqt",
        "install-qt",
        args.host,
        args.target,
        args.qt_version,
        args.compiler,
        "--outputdir",
        args.output_dir,
    ]

    # Restrict archives so you only download what you need.
    if args.modules:
        cmd.extend(["--archives", *args.modules])
    if args.base_url:
        cmd.extend(["--base", args.base_url])
    if args.timeout:
        cmd.extend(["--timeout", str(args.timeout)])

    return cmd


def build_install_tools_cmds(args: argparse.Namespace) -> Iterable[List[str]]:
    """Optionally pull in build helper tools (ninja + CMake) via Qt maintenance repo."""
    tools = ["tools_ninja", "tools_cmake"]
    for tool in tools:
        cmd = [
            sys.executable,
            "-m",
            "aqt",
            "install-tool",
            args.host,
            args.target,
            tool,
            "latest",
            "--outputdir",
            args.output_dir,
        ]
        if args.base_url:
            cmd.extend(["--base", args.base_url])
        if args.timeout:
            cmd.extend(["--timeout", str(args.timeout)])
        yield cmd


def build_install_src_cmd(args: argparse.Namespace) -> List[str]:
    """Download Qt source tree matching the binary version (useful for IDE navigation)."""
    cmd = [
        sys.executable,
        "-m",
        "aqt",
        "install-src",
        args.host,
        args.qt_version,
        "--outputdir",
        args.output_dir,
    ]
    if args.base_url:
        cmd.extend(["--base", args.base_url])
    if args.timeout:
        cmd.extend(["--timeout", str(args.timeout)])
    if args.src_archives:
        cmd.extend(["--archives", *args.src_archives])
    return cmd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Qt 6 binaries (and optional build tools) using aqtinstall."
    )
    parser.add_argument(
        "--qt-version",
        default="6.7.2",
        help="Qt version to download (e.g. 6.7.2).",
    )
    parser.add_argument(
        "--compiler",
        default="win64_msvc2019_64",
        help="Qt compiler flavor/arch (e.g. win64_msvc2019_64, win64_msvc2022_64, win64_mingw).",
    )
    parser.add_argument(
        "--host",
        default="windows",
        help="Host OS for binaries (windows, linux, mac).",
    )
    parser.add_argument(
        "--target",
        default="desktop",
        help="Target (desktop, android, ios).",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join("third_party", "qt6"),
        help="Where to place the downloaded Qt tree.",
    )
    parser.add_argument(
        "--modules",
        nargs="*",
        default=DEFAULT_MODULES,
        help="Archives to fetch; omit to download all available for the compiler.",
    )
    parser.add_argument(
        "--base-url",
        help="Mirror base URL; defaults to Qt CDN.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        help="Download timeout (seconds) forwarded to aqtinstall.",
    )
    parser.add_argument(
        "--with-tools",
        action="store_true",
        help="Also download ninja and CMake from Qt's tool repos.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing (useful for CI preview).",
    )
    parser.add_argument(
        "--with-src",
        action="store_true",
        help="Also download Qt source archives (good for IDE navigation; large download).",
    )
    parser.add_argument(
        "--src-archives",
        nargs="*",
        help="Specific source archives (omit to fetch the whole Qt source bundle).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    ensure_aqtinstall(dry_run=args.dry_run)

    install_qt_cmd = build_install_qt_cmd(args)
    run(install_qt_cmd, dry_run=args.dry_run)

    if args.with_tools:
        for cmd in build_install_tools_cmds(args):
            run(cmd, dry_run=args.dry_run)

    if args.with_src:
        install_src_cmd = build_install_src_cmd(args)
        run(install_src_cmd, dry_run=args.dry_run)

    print("Done. Qt is in:", os.path.abspath(args.output_dir))


if __name__ == "__main__":
    main()
