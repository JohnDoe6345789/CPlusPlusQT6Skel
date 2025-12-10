import argparse
import os
import subprocess
from typing import Optional, Sequence

from .downloader import (
    DEFAULT_MODULES,
    DEFAULT_QT_VERSION,
    build_install_qt_cmd,
    build_install_src_cmd,
    build_install_tools_cmds,
    check_build_dependencies,
    detect_host,
    detect_latest_qt_version,
    ensure_aqtinstall,
    resolve_compiler,
    run,
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
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
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
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
