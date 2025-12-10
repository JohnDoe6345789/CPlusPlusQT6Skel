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
import importlib.util
import os
import shutil
import subprocess
import sys
from typing import Iterable, List, Optional, Tuple


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

DEFAULT_QT_VERSION = "6.7.2"
DEFAULT_COMPILER = "win64_msvc2019_64"


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
        default=None,
        help="Qt version to download (e.g. 6.7.2). If omitted, the latest available is used.",
    )
    parser.add_argument(
        "--compiler",
        default=None,
        help="Qt compiler flavor/arch (e.g. win64_msvc2019_64, win64_msvc2022_64, win64_mingw). "
        "If omitted on Windows, the newest installed Visual Studio dictates the default.",
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


def _vswhere_path() -> Optional[str]:
    """Return vswhere.exe path if present."""
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if not program_files_x86:
        return None
    path = os.path.join(
        program_files_x86,
        "Microsoft Visual Studio",
        "Installer",
        "vswhere.exe",
    )
    return path if os.path.exists(path) else None


def detect_msvc_compiler() -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """Detect latest installed MSVC toolset and map it to a Qt arch string.

    Returns (compiler_arch, major_version, raw_version_str).
    """
    vswhere = _vswhere_path()
    if not vswhere:
        return None, None, None

    cmd = [
        vswhere,
        "-latest",
        "-products",
        "*",
        "-requires",
        "Microsoft.Component.MSBuild",
        "-property",
        "installationVersion",
    ]

    try:
        raw_version = (
            subprocess.check_output(cmd, text=True, encoding="utf-8").strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, None, None

    try:
        major = int(raw_version.split(".", 1)[0])
    except (ValueError, IndexError):
        return None, None, raw_version

    # Map Visual Studio major version to the corresponding Qt arch identifier.
    if major >= 17:
        return "win64_msvc2022_64", major, raw_version
    if major >= 16:
        return "win64_msvc2019_64", major, raw_version
    return None, major, raw_version


def detect_latest_qt_version(
    *,
    host: str,
    target: str,
    base_url: Optional[str],
    timeout: Optional[int],
) -> Optional[str]:
    """Ask aqt for the newest Qt version available for the given host/target."""

    if importlib.util.find_spec("aqt") is None:
        return None

    def _build_cmd() -> List[str]:
        cmd = [sys.executable, "-m", "aqt", "list-qt", host, target]
        if base_url:
            cmd.extend(["--base", base_url])
        if timeout:
            cmd.extend(["--timeout", str(timeout)])
        return cmd

    commands = [
        _build_cmd() + ["--latest-version"],
        _build_cmd(),
    ]

    for cmd in commands:
        try:
            output = subprocess.check_output(
                cmd,
                text=True,
                encoding="utf-8",
                timeout=timeout if timeout else None,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            continue

        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines:
            continue
        # Both list outputs end with the most recent version.
        return lines[-1]

    return None


def main() -> None:
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    ensure_aqtinstall(dry_run=args.dry_run)

    if args.compiler is None:
        detected_compiler, detected_major, raw_vs_version = detect_msvc_compiler()
        if detected_compiler:
            if detected_major:
                print(
                    f"Detected Visual Studio {detected_major} (version {raw_vs_version}); "
                    f"using compiler: {detected_compiler}"
                )
            else:
                print(f"Detected Visual Studio toolset; using compiler: {detected_compiler}")
            args.compiler = detected_compiler
        else:
            if detected_major is not None and detected_major < 16:
                print(
                    "Detected Visual Studio appears older than 2019 "
                    "(Qt 6 binaries target MSVC 2019/2022). "
                    "Please upgrade Visual Studio for best compatibility."
                )
            else:
                print("Could not detect Visual Studio.")
            print(f"Defaulting to {DEFAULT_COMPILER}")
            args.compiler = DEFAULT_COMPILER

    if args.qt_version is None:
        detected_qt = detect_latest_qt_version(
            host=args.host,
            target=args.target,
            base_url=args.base_url,
            timeout=args.timeout,
        )
        if detected_qt:
            print(f"Detected latest Qt version: {detected_qt}")
            args.qt_version = detected_qt
        else:
            print(f"Could not detect latest Qt version; defaulting to {DEFAULT_QT_VERSION}")
            args.qt_version = DEFAULT_QT_VERSION

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
