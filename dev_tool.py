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
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parent
DEFAULT_BUILD_DIR = ROOT / "build"
DEFAULT_BUILD_TYPE = "Debug"
DEFAULT_RUN_TARGETS = ["sample_app", "sample_cli"]
NON_RUN_TARGETS = {
    "all",
    "ALL_BUILD",
    "RUN_TESTS",
    "test",
    "install",
    "help",
    "clean",
    "ZERO_CHECK",
}
HELP_URLS = {
    "cmake": "https://cmake.org/download/",
    "ninja": "https://ninja-build.org/",
    "qt": "https://www.qt.io/download",
    "download_script": "python download_qt6.py",
}
PACKAGE_NAMES = {
    "ninja": {
        "apt": "ninja-build",
        "dnf": "ninja-build",
        "brew": "ninja",
        "choco": "ninja",
    },
    "cmake": {
        "apt": "cmake",
        "dnf": "cmake",
        "brew": "cmake",
        "choco": "cmake",
    },
    "qt": {
        "apt": "qt6-base-dev qt6-declarative-dev",
        "dnf": "qt6-qtbase-devel qt6-qtdeclarative-devel",
        "brew": "qt@6",
        "choco": "qt-lts-long-term-release",  # community package; may vary
    },
}


def run_command(cmd: Sequence[str], *, cwd: Optional[Path] = None) -> None:
    """Invoke a shell command and exit on failure."""
    display = " ".join(cmd)
    if cwd:
        display = f"(cd {cwd}) {display}"
    print(f"\n>>> {display}")
    subprocess.run(cmd, check=True, cwd=cwd)


def parse_version_from_path(path: Path) -> Tuple[int, ...]:
    """Extract a version tuple like (6, 10, 1) from a path component."""
    for part in reversed(path.parts):
        match = re.search(r"(\d+)\.(\d+)\.(\d+)", part)
        if match:
            return tuple(int(x) for x in match.groups())
    return tuple()


def detect_qt_flavor(path: Path) -> Optional[str]:
    """Return 'mingw' or 'msvc' based on path segments (Windows-only heuristic)."""
    lower_parts = [part.lower() for part in path.parts]
    if any("mingw" in part for part in lower_parts):
        return "mingw"
    if any("msvc" in part for part in lower_parts):
        return "msvc"
    return None


def detect_compiler_flavor(generator: Optional[str]) -> Optional[str]:
    """
    Best-effort guess of Windows toolchain flavor so we can match Qt binaries.
    Returns "msvc", "mingw", or None when unsure/not Windows.
    """
    if not sys.platform.startswith("win"):
        return None

    gen = (generator or os.environ.get("CMAKE_GENERATOR") or "").lower()
    if "visual studio" in gen or "msvc" in gen:
        return "msvc"
    if "mingw" in gen:
        return "mingw"

    for env_var in ("CXX", "CC"):
        compiler = os.environ.get(env_var)
        if not compiler:
            continue
        name = Path(compiler).name.lower()
        if name in {"cl", "cl.exe"} or "msvc" in name:
            return "msvc"
        if "mingw" in name or name.startswith("g++") or name.startswith("gcc"):
            return "mingw"

    cl_path = shutil.which("cl")
    if cl_path:
        return "msvc"
    gxx_path = shutil.which("g++")
    if gxx_path and "mingw" in gxx_path.lower():
        return "mingw"
    return None


def enforce_qt_toolchain_match(qt_prefix: Optional[Path], generator: Optional[str]) -> None:
    """
    Fail fast when the detected compiler flavor and Qt binaries obviously conflict.
    Avoids slow/cryptic linker errors when mixing MSVC Qt with MinGW (or vice versa).
    """
    if not qt_prefix or not sys.platform.startswith("win"):
        return
    compiler_flavor = detect_compiler_flavor(generator)
    qt_flavor = detect_qt_flavor(qt_prefix)
    if compiler_flavor and qt_flavor and compiler_flavor != qt_flavor:
        raise SystemExit(
            f"Qt install {qt_prefix} looks like {qt_flavor.upper()}, "
            f"but your compiler/generator looks like {compiler_flavor.upper()}.\n"
            "Use a matching Qt download (e.g. download_qt6.py --compiler win64_mingw) "
            "or switch to the corresponding toolchain/generator."
        )


def download_qt_with_script(
    *,
    qt_version: Optional[str],
    compiler: Optional[str],
    output_dir: Path,
    base_url: Optional[str] = None,
    with_tools: bool = False,
) -> None:
    """Invoke download_qt6.py with a small, typed surface."""
    script = ROOT / "download_qt6.py"
    if not script.exists():
        raise SystemExit(f"download_qt6.py not found at {script}")
    cmd: List[str] = [sys.executable, str(script)]
    if qt_version:
        cmd += ["--qt-version", qt_version]
    if compiler:
        cmd += ["--compiler", compiler]
    if output_dir:
        cmd += ["--output-dir", str(output_dir)]
    if base_url:
        cmd += ["--base-url", base_url]
    if with_tools:
        cmd.append("--with-tools")
    print("Qt not found; downloading with download_qt6.py...")
    run_command(cmd)


def ensure_qt_prefix(
    *,
    args: argparse.Namespace,
    generator: Optional[str],
) -> Optional[Path]:
    """Resolve Qt prefix; optionally auto-download when missing."""
    def _resolve() -> Optional[Path]:
        return resolve_qt_prefix(args.qt_prefix, generator)

    qt_prefix = _resolve()
    if qt_prefix or not getattr(args, "download_qt_if_missing", False):
        return qt_prefix

    compiler_arg = args.download_qt_compiler
    if not compiler_arg and sys.platform.startswith("win"):
        flavor = detect_compiler_flavor(generator)
        if flavor == "mingw":
            compiler_arg = "win64_mingw"
        # For MSVC, let download_qt6.py auto-detect via vswhere.

    download_qt_with_script(
        qt_version=args.download_qt_version,
        compiler=compiler_arg,
        output_dir=args.download_qt_output_dir,
    )
    return _resolve()


def autodetect_qt_prefix(preferred_flavor: Optional[str] = None) -> Optional[Path]:
    """
    Try to guess a Qt prefix by looking under third_party/qt6/**/lib/cmake/Qt6.
    Picks the highest semantic version it can find, preferring a flavor that
    matches the detected compiler (msvc vs mingw) when on Windows.
    """
    qt_root = ROOT / "third_party" / "qt6"
    if not qt_root.exists():
        return None

    candidates: list[tuple[Tuple[int, ...], Optional[str], Path]] = []
    for cmake_dir in qt_root.rglob("lib/cmake/Qt6"):
        prefix = cmake_dir.parents[2]  # lib/cmake/Qt6 -> lib -> <prefix>
        candidates.append((parse_version_from_path(prefix), detect_qt_flavor(prefix), prefix))

    if not candidates:
        return None

    def pick_best(items: list[tuple[Tuple[int, ...], Optional[str], Path]]) -> Optional[Path]:
        if not items:
            return None
        items.sort(key=lambda tup: tup[0])
        return items[-1][2]

    if preferred_flavor:
        matching = [item for item in candidates if item[1] == preferred_flavor]
        chosen = pick_best(matching)
        if chosen:
            return chosen

    return pick_best(candidates)


def resolve_qt_prefix(cli_value: Optional[str], generator: Optional[str] = None) -> Optional[Path]:
    """
    Resolve the Qt prefix directory, honoring CLI, env, or auto-detection.
    Returns None if nothing is found so CMake can still try system Qt installs.
    """
    candidates: Iterable[Optional[str]] = (
        cli_value,
        os.environ.get("QT_PREFIX_PATH"),
    )

    cmake_prefixes = os.environ.get("CMAKE_PREFIX_PATH")
    if cmake_prefixes:
        first_prefix = cmake_prefixes.split(os.pathsep)[0]
        candidates = (*candidates, first_prefix)

    for value in candidates:
        if not value:
            continue
        path = Path(value).expanduser()
        if path.exists():
            return path

    preferred_flavor = detect_compiler_flavor(generator)
    return autodetect_qt_prefix(preferred_flavor)


def detect_generator(cli_value: Optional[str]) -> Optional[str]:
    """
    Pick a sensible default generator:
    - CLI value wins
    - $CMAKE_GENERATOR if set
    - Ninja if available
    - otherwise let CMake decide
    """
    if cli_value:
        return cli_value
    if os.environ.get("CMAKE_GENERATOR"):
        return os.environ["CMAKE_GENERATOR"]
    if shutil.which("ninja"):
        return "Ninja"
    return None


def is_multi_config(generator: Optional[str], build_dir: Path) -> bool:
    if generator and (
        "Visual Studio" in generator
        or "Xcode" in generator
        or "Multi-Config" in generator
    ):
        return True
    cache = build_dir / "CMakeCache.txt"
    if cache.exists():
        text = cache.read_text(encoding="utf-8", errors="ignore")
        if "CMAKE_CONFIGURATION_TYPES" in text:
            return True
    return False


def configure_project(
    build_dir: Path,
    generator: Optional[str],
    build_type: str,
    qt_prefix: Optional[Path],
) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)

    cmd: List[str] = ["cmake", "-S", str(ROOT), "-B", str(build_dir)]
    if generator:
        cmd += ["-G", generator]
    if qt_prefix:
        cmd.append(f"-DCMAKE_PREFIX_PATH={qt_prefix}")
    if build_type:
        cmd.append(f"-DCMAKE_BUILD_TYPE={build_type}")

    run_command(cmd)


def build_targets(
    build_dir: Path,
    generator: Optional[str],
    build_type: str,
    targets: Sequence[str],
    config_override: Optional[str],
) -> None:
    multi = is_multi_config(generator, build_dir)
    config = config_override or (build_type if multi else None)

    cmd: List[str] = ["cmake", "--build", str(build_dir)]
    if targets:
        cmd += ["--target", *targets]
    if config:
        cmd += ["--config", config]

    run_command(cmd)


def run_tests(
    build_dir: Path,
    generator: Optional[str],
    build_type: str,
    config_override: Optional[str],
    extra_ctest: Sequence[str],
) -> None:
    multi = is_multi_config(generator, build_dir)
    config = config_override or (build_type if multi else None)

    cmd: List[str] = ["ctest", "--test-dir", str(build_dir)]
    if config:
        cmd += ["-C", config]
    cmd += list(extra_ctest)

    run_command(cmd)


def find_built_binary(
    build_dir: Path,
    target: str,
    generator: Optional[str],
    build_type: str,
    config_override: Optional[str],
) -> Path:
    exe_name = target + (".exe" if os.name == "nt" else "")
    multi = is_multi_config(generator, build_dir)
    config = config_override or (build_type if multi else None)

    candidates = [
        build_dir / exe_name,
        build_dir / target / exe_name,  # e.g. Xcode can nest products
    ]
    if config:
        candidates.append(build_dir / config / exe_name)
        candidates.append(build_dir / config / target / exe_name)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Fallback to a search if layout is unexpected.
    matches = list(build_dir.rglob(exe_name))
    if matches:
        return matches[0]

    raise FileNotFoundError(f"Executable for target '{target}' not found in {build_dir}")


def read_generator_from_cache(build_dir: Path) -> Optional[str]:
    cache = build_dir / "CMakeCache.txt"
    if not cache.exists():
        return None
    for line in cache.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("CMAKE_GENERATOR:INTERNAL="):
            return line.partition("=")[2].strip()
    return None


def list_targets_with_ninja(build_dir: Path) -> list[str]:
    if not shutil.which("ninja"):
        return []
    try:
        output = subprocess.check_output(
            ["ninja", "-C", str(build_dir), "-t", "targets", "all"],
            text=True,
        )
    except subprocess.CalledProcessError:
        return []
    targets: list[str] = []
    for line in output.splitlines():
        name = line.split(":", 1)[0].strip()
        if name and name not in NON_RUN_TARGETS:
            targets.append(name)
    return targets


def list_targets_with_cmake(build_dir: Path, config: Optional[str]) -> list[str]:
    cmd = ["cmake", "--build", str(build_dir), "--target", "help"]
    if config:
        cmd += ["--config", config]
    try:
        output = subprocess.check_output(cmd, text=True)
    except subprocess.CalledProcessError:
        return []

    targets: list[str] = []
    for line in output.splitlines():
        # Common patterns across generators.
        if line.startswith("..."):
            candidate = line[3:].strip().split(" ")[0]
        elif ":" in line:
            candidate = line.split(":", 1)[0].strip()
        else:
            continue
        if candidate and candidate not in NON_RUN_TARGETS:
            targets.append(candidate)
    return targets


def list_runnable_targets(
    build_dir: Path,
    generator: Optional[str],
    build_type: str,
    config_override: Optional[str],
) -> list[str]:
    gen = generator or read_generator_from_cache(build_dir) or ""
    config = config_override or (build_type if is_multi_config(gen, build_dir) else None)

    if "Ninja" in gen:
        found = list_targets_with_ninja(build_dir)
    else:
        found = list_targets_with_cmake(build_dir, config)

    # Deduplicate while preserving order.
    seen = set()
    cleaned: list[str] = []
    for name in found + DEFAULT_RUN_TARGETS:
        if name in NON_RUN_TARGETS or name in seen:
            continue
        seen.add(name)
        cleaned.append(name)
    return cleaned


def detect_package_manager() -> Optional[str]:
    if sys.platform.startswith("win"):
        return "choco"
    if sys.platform == "darwin":
        return "brew"
    if shutil.which("apt-get"):
        return "apt"
    if shutil.which("dnf"):
        return "dnf"
    if shutil.which("yum"):
        return "dnf"
    return None


def package_install_hint(tool: str) -> str:
    mgr = detect_package_manager()
    pkg_map = PACKAGE_NAMES.get(tool, {})
    if mgr and mgr in pkg_map:
        pkg = pkg_map[mgr]
        if mgr == "apt":
            return f"sudo apt-get install {pkg}"
        if mgr == "dnf":
            return f"sudo dnf install {pkg}"
        if mgr == "brew":
            return f"brew install {pkg}"
        if mgr == "choco":
            return f"choco install {pkg} -y"
    # Fallback generic guidance.
    if tool in pkg_map:
        return f"Install via your package manager ({' / '.join(pkg_map.keys())})"
    return "Install via your package manager"


def verify_environment(
    qt_prefix: Optional[Path], generator: Optional[str]
) -> bool:
    """
    Check common requirements (cmake, generator availability, Qt prefix).
    Returns True when everything looks ok, False otherwise.
    """
    print("\nEnvironment verification:")
    ok = True

    cmake_path = shutil.which("cmake")
    if cmake_path:
        print(f" - cmake: found at {cmake_path}")
    else:
        ok = False
        hint = package_install_hint("cmake")
        print(f" - cmake: MISSING. Try \"{hint}\" or download {HELP_URLS['cmake']}.")

    detected_gen = detect_generator(generator)
    if detected_gen:
        print(f" - generator: {detected_gen} (set via CLI/env/auto)")
    else:
        ok = False
        ninja_hint = package_install_hint("ninja")
        print(
            f" - generator: none detected. Install Ninja ({HELP_URLS['ninja']}) "
            f"e.g. \"{ninja_hint}\" or set CMAKE_GENERATOR/--generator."
        )

    resolved_qt = resolve_qt_prefix(str(qt_prefix) if qt_prefix else None, detected_gen)
    compiler_flavor = detect_compiler_flavor(detected_gen)
    if resolved_qt:
        print(f" - Qt prefix: {resolved_qt}")
        qt_flavor = detect_qt_flavor(resolved_qt)
        if compiler_flavor and qt_flavor and compiler_flavor != qt_flavor:
            ok = False
            print(
                f" - Qt/toolchain mismatch: Qt looks like {qt_flavor.upper()} but "
                f"your compiler/generator looks like {compiler_flavor.upper()}. "
                "Download a matching Qt build or switch toolchains."
            )
    else:
        ok = False
        qt_hint = package_install_hint("qt")
        print(
            " - Qt prefix: not found. Set --qt-prefix / QT_PREFIX_PATH / CMAKE_PREFIX_PATH "
            f"or fetch Qt with \"{HELP_URLS['download_script']}\" "
            f"(binaries: {HELP_URLS['qt']}; package manager e.g. \"{qt_hint}\")."
        )

    return ok


def prompt_for_choice(options: Sequence[str], *, prompt: str) -> str:
    """Simple interactive selector for small option lists."""
    if not sys.stdin.isatty():
        raise ValueError("No target provided and input is not interactive.")
    for idx, opt in enumerate(options, start=1):
        print(f"[{idx}] {opt}")
    while True:
        choice = input(f"{prompt} [1-{len(options)}]: ").strip()
        if not choice:
            return options[0]
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        print("Invalid selection, try again.")


def prompt_yes_no(question: str, *, default: bool = True) -> bool:
    """TTY-only yes/no prompt with default."""
    if not sys.stdin.isatty():
        return default
    suffix = "Y/n" if default else "y/N"
    while True:
        choice = input(f"{question} ({suffix}): ").strip().lower()
        if not choice:
            return default
        if choice in ("y", "yes"):
            return True
        if choice in ("n", "no"):
            return False
        print("Please enter y or n.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    def add_common_arguments(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--build-dir",
            type=Path,
            default=DEFAULT_BUILD_DIR,
            help="Build directory (default: ./build)",
        )
        p.add_argument(
            "--build-type",
            default=DEFAULT_BUILD_TYPE,
            help="CMAKE_BUILD_TYPE for single-config generators (default: Debug)",
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
            default=ROOT / "third_party" / "qt6",
            help="Where to place auto-downloaded Qt (default: third_party/qt6).",
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
        help="Check environment (cmake, generator, Qt prefix) and suggest fixes",
    )
    add_common_arguments(verify_parser)

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
        default=ROOT / "third_party" / "qt6",
        help="Destination directory (default: third_party/qt6)",
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

    menu_parser = subparsers.add_parser(
        "menu",
        help="Interactive mode to build, test, or run targets",
    )
    add_common_arguments(menu_parser)

    args = parser.parse_args(argv)
    if args.command is None:
        # Default to interactive menu if available, otherwise fall back to build.
        args.command = "menu" if sys.stdin.isatty() else "build"

    # Provide subcommand defaults when command was implied.
    if args.command == "build" and not hasattr(args, "target"):
        args.target = []
    if args.command == "test" and not hasattr(args, "ctest_args"):
        args.ctest_args = []
    if args.command == "run":
        args.target = getattr(args, "target", None)
        args.program_args = getattr(args, "program_args", [])
        args.skip_build = getattr(args, "skip_build", False)

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
    qt_prefix = ensure_qt_prefix(args=args, generator=generator)
    build_type = args.build_type or DEFAULT_BUILD_TYPE

    if args.command == "verify":
        ok = verify_environment(qt_prefix, generator)
        return 0 if ok else 1

    if args.command == "build":
        enforce_qt_toolchain_match(qt_prefix, generator)
        configure_project(build_dir, generator, build_type, qt_prefix)
        build_targets(build_dir, generator, build_type, args.target, args.config)
        return 0

    if args.command == "test":
        enforce_qt_toolchain_match(qt_prefix, generator)
        configure_project(build_dir, generator, build_type, qt_prefix)
        build_targets(build_dir, generator, build_type, [], args.config)
        run_tests(build_dir, generator, build_type, args.config, args.ctest_args)
        return 0

    if args.command == "run":
        enforce_qt_toolchain_match(qt_prefix, generator)
        configure_project(build_dir, generator, build_type, qt_prefix)
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
        # Choose high-level action.
        actions = ["verify", "build", "test", "run", "quit"]
        choice = prompt_for_choice(actions, prompt="Select action")
        if choice == "verify":
            ok = verify_environment(args.qt_prefix, generator)
            return 0 if ok else 1
        if choice == "build":
            enforce_qt_toolchain_match(qt_prefix, generator)
            configure_project(build_dir, generator, build_type, qt_prefix)
            build_targets(build_dir, generator, build_type, [], args.config)
            return 0
        if choice == "test":
            enforce_qt_toolchain_match(qt_prefix, generator)
            configure_project(build_dir, generator, build_type, qt_prefix)
            build_targets(build_dir, generator, build_type, [], args.config)
            run_tests(build_dir, generator, build_type, args.config, [])
            return 0
        if choice == "run":
            do_build = prompt_yes_no("Build before running?", default=True)
            enforce_qt_toolchain_match(qt_prefix, generator)
            configure_project(build_dir, generator, build_type, qt_prefix)
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
        return 0

    parser.error(f"Unhandled command {args.command}")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\nCommand failed with exit code {exc.returncode}")
        raise
