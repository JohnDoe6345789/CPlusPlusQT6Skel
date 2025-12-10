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
import re
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
DEFAULT_WINDOWS_COMPILER = "win64_msvc2019_64"
DEFAULT_COMPILERS = {
    "windows": DEFAULT_WINDOWS_COMPILER,
    "linux": "linux_gcc_64",
    "mac": "clang_64",
}


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


def detect_host() -> str:
    """Map Python platform markers to the aqt host string."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "mac"
    return "windows"


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
        default=None,
        help="Host OS for binaries (windows, linux, mac). If omitted, detected from the running OS.",
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
    parser.add_argument(
        "--check-build-deps",
        action="store_true",
        help="Verify native build prerequisites for the host (Linux/macOS).",
    )
    parser.add_argument(
        "--install-build-deps",
        action="store_true",
        help="Attempt to install missing build prerequisites using apt/dnf/brew. Implies --check-build-deps.",
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
    compiler: Optional[str],
) -> Optional[str]:
    """Ask aqt for the newest Qt version available for the given host/target, validating availability."""

    if importlib.util.find_spec("aqt") is None:
        return None

    def _build_cmd(extra: Optional[str] = None) -> List[str]:
        cmd = [sys.executable, "-m", "aqt", "list-qt", host, target]
        if extra:
            cmd.append(extra)
        if base_url:
            cmd.extend(["--base", base_url])
        if timeout:
            cmd.extend(["--timeout", str(timeout)])
        return cmd

    def _version_key(v: str) -> Tuple[int, ...]:
        # Keep only numeric components to allow simple sorting (e.g., 6.10.1).
        parts = re.split(r"[^\d]+", v)
        nums = []
        for p in parts:
            if p == "":
                continue
            try:
                nums.append(int(p))
            except ValueError:
                nums.append(0)
        return tuple(nums)

    def _list_versions() -> List[str]:
        try:
            output = subprocess.check_output(
                _build_cmd(),
                text=True,
                encoding="utf-8",
                timeout=timeout if timeout else None,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return []
        versions: List[str] = []
        for line in output.splitlines():
            for token in line.strip().split():
                if token:
                    versions.append(token)
        return versions

    def _version_has_archives(version: str) -> bool:
        # Validate by asking aqt for available architectures for the version; if it errors, skip it.
        cmd = [sys.executable, "-m", "aqt", "list-qt", host, target, "--arch", version]
        if base_url:
            cmd.extend(["--base", base_url])
        if timeout:
            cmd.extend(["--timeout", str(timeout)])
        try:
            output = subprocess.check_output(
                cmd,
                text=True,
                encoding="utf-8",
                timeout=timeout if timeout else None,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
        if not output.strip():
            return False
        if compiler:
            archs = {token for line in output.splitlines() for token in line.strip().split() if token}
            if compiler not in archs:
                return False
        return True

    versions = _list_versions()
    for version in sorted(versions, key=_version_key, reverse=True):
        if _version_has_archives(version):
            return version

    return None


def _read_os_release() -> Tuple[Optional[str], Optional[str]]:
    """Return (id, version_id) from /etc/os-release if present."""
    path = "/etc/os-release"
    if not os.path.exists(path):
        return None, None
    data: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "=" not in line:
                continue
            key, value = line.strip().split("=", 1)
            data[key] = value.strip('"')
    return data.get("ID"), data.get("VERSION_ID")


def _command_exists(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def check_build_dependencies(
    *,
    host: str,
    install: bool,
    dry_run: bool,
) -> None:
    """Validate and optionally install native build toolchains for Linux/macOS."""

    def maybe_install(cmd: List[str]) -> None:
        if install:
            run(cmd, dry_run=dry_run)
        else:
            print("Missing dependency; rerun with --install-build-deps to install:")
            print(" ", " ".join(cmd))

    if host == "mac":
        print("Checking macOS build tools (Xcode Command Line Tools, Homebrew, CMake, Ninja)...")
        try:
            subprocess.check_output(["xcode-select", "-p"])
            xcode_ok = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            xcode_ok = False

        if not xcode_ok:
            print("Xcode Command Line Tools not found.")
            maybe_install(["xcode-select", "--install"])
        brew_ok = _command_exists("brew")
        if not brew_ok:
            print("Homebrew not found.")
            print("Install Homebrew first: https://brew.sh/")
        for tool in ("cmake", "ninja"):
            if _command_exists(tool):
                continue
            if brew_ok:
                maybe_install(["brew", "install", tool])
            else:
                print(f"{tool} missing and Homebrew not available.")
        return

    if host == "linux":
        distro_id, version_id = _read_os_release()
        print(f"Detected Linux distro: {distro_id or 'unknown'} {version_id or ''}".strip())
        if distro_id in {"ubuntu", "debian"}:
            required = ["build-essential", "libgl1-mesa-dev", "libxkbcommon-x11-0", "ninja-build", "cmake"]
            for cmd in (["sudo", "apt-get", "update"], ["sudo", "apt-get", "install", "-y", *required]):
                maybe_install(cmd)
            return
        if distro_id in {"fedora", "rhel", "centos", "rocky", "almalinux"}:
            required = ["mesa-libGL-devel", "libxkbcommon-devel", "ninja-build", "cmake"]
            for cmd in (
                ["sudo", "dnf", "groupinstall", "-y", "Development Tools"],
                ["sudo", "dnf", "install", "-y", *required],
            ):
                maybe_install(cmd)
            return
        print("Unknown Linux distro; ensure you have a C++ toolchain, CMake, Ninja, and OpenGL headers installed.")
        return

    print("Skipping build dependency check for host:", host)


def resolve_compiler(args: argparse.Namespace) -> str:
    """Pick a compiler tuple based on host and optional detection."""
    if args.compiler:
        return args.compiler

    if args.host == "windows":
        detected_compiler, detected_major, raw_vs_version = detect_msvc_compiler()
        if detected_compiler:
            if detected_major:
                print(
                    f"Detected Visual Studio {detected_major} (version {raw_vs_version}); "
                    f"using compiler: {detected_compiler}"
                )
            else:
                print(f"Detected Visual Studio toolset; using compiler: {detected_compiler}")
            return detected_compiler

        if detected_major is not None and detected_major < 16:
            print(
                "Detected Visual Studio appears older than 2019 "
                "(Qt 6 binaries target MSVC 2019/2022). "
                "Please upgrade Visual Studio for best compatibility."
            )
        else:
            print("Could not detect Visual Studio.")

    fallback = DEFAULT_COMPILERS.get(args.host, DEFAULT_WINDOWS_COMPILER)
    print(f"Defaulting to {fallback}")
    return fallback


def main() -> None:
    args = parse_args()
    user_supplied_qt_version = args.qt_version is not None
    auto_detected_qt_version: Optional[str] = None
    os.makedirs(args.output_dir, exist_ok=True)

    ensure_aqtinstall(dry_run=args.dry_run)

    if args.host is None:
        args.host = detect_host()
        print(f"Detected host OS: {args.host}")

    if args.check_build_deps or args.install_build_deps:
        check_build_dependencies(
            host=args.host,
            install=args.install_build_deps,
            dry_run=args.dry_run,
        )

    args.compiler = resolve_compiler(args)

    if args.qt_version is None:
        detected_qt = detect_latest_qt_version(
            host=args.host,
            target=args.target,
            base_url=args.base_url,
            timeout=args.timeout,
            compiler=args.compiler,
        )
        if detected_qt:
            print(f"Detected latest Qt version: {detected_qt}")
            args.qt_version = detected_qt
            auto_detected_qt_version = detected_qt
        else:
            print(f"Could not detect latest Qt version; defaulting to {DEFAULT_QT_VERSION}")
            args.qt_version = DEFAULT_QT_VERSION

    install_qt_cmd = build_install_qt_cmd(args)
    try:
        run(install_qt_cmd, dry_run=args.dry_run)
    except subprocess.CalledProcessError:
        if (
            not user_supplied_qt_version
            and auto_detected_qt_version
            and auto_detected_qt_version != DEFAULT_QT_VERSION
        ):
            print(
                f"Failed to install detected Qt version {auto_detected_qt_version}; "
                f"falling back to {DEFAULT_QT_VERSION}."
            )
            args.qt_version = DEFAULT_QT_VERSION
            install_qt_cmd = build_install_qt_cmd(args)
            run(install_qt_cmd, dry_run=args.dry_run)
        else:
            raise

    if args.with_tools:
        for cmd in build_install_tools_cmds(args):
            run(cmd, dry_run=args.dry_run)

    if args.with_src:
        install_src_cmd = build_install_src_cmd(args)
        run(install_src_cmd, dry_run=args.dry_run)

    print("Done. Qt is in:", os.path.abspath(args.output_dir))


if __name__ == "__main__":
    main()
