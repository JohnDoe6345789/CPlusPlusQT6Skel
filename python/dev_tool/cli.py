#!/usr/bin/env python3
"""
Cross-platform helper for configuring, building, running, and testing this repo.

Typical usage:
    python dev_tool.py build
    python dev_tool.py run sample_cli -- --help
    python dev_tool.py test
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from .config import (
    USER_SETTINGS,
    _parse_setting_arg,
    _print_settings,
    apply_settings_to_args,
    edit_settings_interactive,
    set_settings,
)
from .constants import DEFAULT_BUILD_TYPE, DEFAULT_QT_CREATOR_OUTPUT_DIR, DEFAULT_SETTINGS
from .project import (
    build_targets,
    configure_project,
    find_built_binary,
    list_runnable_targets,
    run_tests,
)
from .qml import choose_qml_file, open_qml_in_qt_creator
from .qt import (
    check_library_updates,
    detect_compiler_flavor,
    detect_generator,
    download_qt_with_script,
    ensure_qt_prefix,
    enforce_qt_toolchain_match,
    verify_environment,
)
from .utils import prompt_for_choice, prompt_yes_no, run_command


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    def add_common_arguments(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--build-dir",
            type=Path,
            default=None,
            help="Build directory (default: settings file or ./build)",
        )
        p.add_argument(
            "--build-type",
            default=None,
            help="CMAKE_BUILD_TYPE for single-config generators (default: from settings or Debug)",
        )
        p.add_argument("--config", help="--config value for multi-config generators")
        p.add_argument("--qt-prefix", help="Path to Qt installation root")
        p.add_argument("--generator", help="CMake generator to use")
        p.add_argument(
            "--download-qt-if-missing",
            action="store_true",
            help="Automatically run download_qt6.py when Qt is not found.",
        )
        p.add_argument(
            "--download-qt-version",
            help="Qt version to fetch when auto-downloading (forwards to download_qt6.py).",
        )
        p.add_argument(
            "--download-qt-compiler",
            help="Qt compiler flavor/arch for auto-download (e.g. win64_mingw).",
        )
        p.add_argument(
            "--download-qt-output-dir",
            type=Path,
            default=None,
            help="Where to place auto-downloaded Qt (default: settings file or third_party/qt6).",
        )

    add_common_arguments(parser)

    subparsers = parser.add_subparsers(dest="command")

    build_parser = subparsers.add_parser(
        "build",
        help="Configure (if needed) and build the project",
    )
    add_common_arguments(build_parser)
    build_parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Specific targets to build (default: all)",
    )

    test_parser = subparsers.add_parser(
        "test",
        help="Build and run tests via ctest",
    )
    add_common_arguments(test_parser)
    test_parser.add_argument(
        "ctest_args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Arguments passed through to ctest",
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Build (unless --skip-build) and run a built target",
    )
    add_common_arguments(run_parser)
    run_parser.add_argument(
        "target",
        nargs="?",
        help="Executable target to run (omit to pick from detected list)",
    )
    run_parser.add_argument(
        "program_args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Arguments passed to the executable after '--'",
    )
    run_parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Run without rebuilding first",
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help="Check environment (compiler, cmake, generator, Qt prefix) and suggest fixes",
    )
    add_common_arguments(verify_parser)

    updates_parser = subparsers.add_parser(
        "check-updates",
        help="Check Qt and vendored libraries for newer upstream releases",
    )
    add_common_arguments(updates_parser)

    download_parser = subparsers.add_parser(
        "download-qt",
        help="Fetch Qt using the bundled download_qt6.py helper",
    )
    download_parser.add_argument("--qt-version", help="Qt version to download")
    download_parser.add_argument(
        "--compiler",
        help="Qt compiler flavor/arch (e.g. win64_mingw, win64_msvc2022_64)",
    )
    download_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Destination directory (default: settings file or third_party/qt6)",
    )
    download_parser.add_argument(
        "--base-url",
        help="Mirror base URL to pass through to download_qt6.py",
    )
    download_parser.add_argument(
        "--with-tools",
        action="store_true",
        help="Also download Ninja and CMake via Qt maintenance tool archives.",
    )

    qml_parser = subparsers.add_parser(
        "open-qml",
        help="Open a project QML file in Qt Creator",
    )
    qml_parser.add_argument(
        "qml_file",
        nargs="?",
        help="Path to QML file (default: choose from discovered project QML files)",
    )
    qml_parser.add_argument(
        "--ensure-qt-creator",
        dest="ensure_qt_creator",
        action="store_true",
        default=True,
        help="If Qt Creator is missing, download it (includes qml2puppet for Designer). Default: on.",
    )
    qml_parser.add_argument(
        "--no-ensure-qt-creator",
        dest="ensure_qt_creator",
        action="store_false",
        help="Skip auto-download of Qt Creator if it is missing.",
    )
    qml_parser.add_argument(
        "--qt-creator-version",
        help="Qt Creator version to download when --ensure-qt-creator is set (default: latest).",
    )
    qml_parser.add_argument(
        "--qt-creator-output-dir",
        type=Path,
        default=DEFAULT_QT_CREATOR_OUTPUT_DIR,
        help="Install location for auto-downloaded Qt Creator (default: third_party/qtcreator).",
    )

    settings_parser = subparsers.add_parser(
        "settings",
        help="View or edit persisted defaults",
    )
    settings_parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=f"Update a setting (valid keys: {', '.join(DEFAULT_SETTINGS.keys())})",
    )
    settings_parser.add_argument(
        "--unset",
        action="append",
        default=[],
        metavar="KEY",
        help="Reset a setting back to its built-in default",
    )
    settings_parser.add_argument(
        "--print",
        action="store_true",
        help="Print the current settings and exit",
    )

    menu_parser = subparsers.add_parser(
        "menu",
        help="Interactive mode to build, test, or run targets",
    )
    add_common_arguments(menu_parser)

    args = parser.parse_args(argv)
    if args.command is None:
        args.command = "menu" if sys.stdin.isatty() else "build"

    if args.command == "build" and not hasattr(args, "target"):
        args.target = []
    if args.command == "test" and not hasattr(args, "ctest_args"):
        args.ctest_args = []
    if args.command == "run":
        args.target = getattr(args, "target", None)
        args.program_args = getattr(args, "program_args", [])
        args.skip_build = getattr(args, "skip_build", False)

    args = apply_settings_to_args(args)

    if args.command == "settings":
        current = dict(USER_SETTINGS)
        try:
            set_pairs = dict(_parse_setting_arg(item) for item in args.set)
        except ValueError as exc:
            raise SystemExit(str(exc))

        updated = current
        if set_pairs or args.unset:
            updated = set_settings(set_pairs, unset=args.unset)
            print("Updated settings.")
        if args.print or set_pairs or args.unset:
            _print_settings(updated)
            return 0
        new_settings = edit_settings_interactive(updated)
        _print_settings(new_settings)
        return 0

    if args.command == "download-qt":
        compiler_arg = args.compiler
        if not compiler_arg and sys.platform.startswith("win"):
            flavor = detect_compiler_flavor(None)
            if flavor == "mingw":
                compiler_arg = "win64_mingw"
        download_qt_with_script(
            qt_version=args.qt_version,
            compiler=compiler_arg,
            output_dir=args.output_dir,
            base_url=args.base_url,
            with_tools=args.with_tools,
        )
        return 0

    build_dir = args.build_dir.resolve()
    generator = detect_generator(args.generator)
    generator_is_strict = bool(args.generator or os.environ.get("CMAKE_GENERATOR"))
    qt_prefix = ensure_qt_prefix(args=args, generator=generator)
    build_type = args.build_type or DEFAULT_BUILD_TYPE

    if args.command == "open-qml":
        qml_path = choose_qml_file(getattr(args, "qml_file", None))
        open_qml_in_qt_creator(
            qml_path,
            ensure_creator=getattr(args, "ensure_qt_creator", False),
            creator_version=getattr(args, "qt_creator_version", None),
            creator_output_dir=getattr(args, "qt_creator_output_dir", DEFAULT_QT_CREATOR_OUTPUT_DIR),
        )
        return 0

    if args.command == "check-updates":
        ok = check_library_updates(getattr(args, "qt_prefix", None))
        return 0 if ok else 1

    if args.command == "verify":
        ok = verify_environment(qt_prefix, generator, build_dir)
        return 0 if ok else 1

    if args.command == "build":
        enforce_qt_toolchain_match(qt_prefix, generator)
        generator = configure_project(
            build_dir,
            generator,
            build_type,
            qt_prefix,
            generator_is_strict=generator_is_strict,
        )
        build_targets(build_dir, generator, build_type, args.target, args.config)
        return 0

    if args.command == "test":
        enforce_qt_toolchain_match(qt_prefix, generator)
        generator = configure_project(
            build_dir,
            generator,
            build_type,
            qt_prefix,
            generator_is_strict=generator_is_strict,
        )
        build_targets(build_dir, generator, build_type, [], args.config)
        run_tests(build_dir, generator, build_type, args.config, args.ctest_args)
        return 0

    if args.command == "run":
        enforce_qt_toolchain_match(qt_prefix, generator)
        generator = configure_project(
            build_dir,
            generator,
            build_type,
            qt_prefix,
            generator_is_strict=generator_is_strict,
        )
        available_targets = list_runnable_targets(
            build_dir, generator, build_type, args.config
        )
        run_target = args.target
        if not run_target:
            run_target = prompt_for_choice(
                available_targets,
                prompt="Select target to run",
            )

        if not args.skip_build:
            build_targets(build_dir, generator, build_type, [run_target], args.config)
        exe_path = find_built_binary(
            build_dir, run_target, generator, build_type, args.config
        )
        run_command([str(exe_path), *args.program_args])
        return 0

    if args.command == "menu":
        actions = ["verify", "build", "test", "run", "open-qml", "check-updates", "settings", "quit"]
        choice = prompt_for_choice(actions, prompt="Select action")
        if choice == "verify":
            ok = verify_environment(args.qt_prefix, generator, build_dir)
            return 0 if ok else 1
        if choice == "build":
            enforce_qt_toolchain_match(qt_prefix, generator)
            generator = configure_project(
                build_dir,
                generator,
                build_type,
                qt_prefix,
                generator_is_strict=generator_is_strict,
            )
            build_targets(build_dir, generator, build_type, [], args.config)
            return 0
        if choice == "test":
            enforce_qt_toolchain_match(qt_prefix, generator)
            generator = configure_project(
                build_dir,
                generator,
                build_type,
                qt_prefix,
                generator_is_strict=generator_is_strict,
            )
            build_targets(build_dir, generator, build_type, [], args.config)
            run_tests(build_dir, generator, build_type, args.config, [])
            return 0
        if choice == "run":
            do_build = prompt_yes_no("Build before running?", default=True)
            enforce_qt_toolchain_match(qt_prefix, generator)
            generator = configure_project(
                build_dir,
                generator,
                build_type,
                qt_prefix,
                generator_is_strict=generator_is_strict,
            )
            available_targets = list_runnable_targets(
                build_dir, generator, build_type, args.config
            )
            target = prompt_for_choice(
                available_targets,
                prompt="Select target to run",
            )
            if do_build:
                build_targets(build_dir, generator, build_type, [target], args.config)
            exe_path = find_built_binary(
                build_dir, target, generator, build_type, args.config
            )
            run_command([str(exe_path)])
            return 0
        if choice == "open-qml":
            qml_path = choose_qml_file(None)
            open_qml_in_qt_creator(qml_path, ensure_creator=True)
            return 0
        if choice == "check-updates":
            check_library_updates(args.qt_prefix)
            return 0
        if choice == "settings":
            new_settings = edit_settings_interactive(USER_SETTINGS)
            _print_settings(new_settings)
            return 0
        return 0

    parser.error(f"Unhandled command {args.command}")
    return 1
