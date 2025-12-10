import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from .constants import (
    DEFAULT_QT_CREATOR_OUTPUT_DIR,
    HELP_URLS,
    PACKAGE_NAMES,
    QT_CREATOR_EXECUTABLE_NAMES,
    ROOT,
)
from .utils import (
    compare_versions,
    fetch_latest_pdcurses_version,
    fetch_latest_qt_version,
    parse_version_from_path,
    parse_version_string,
    run_command,
)


def detect_qt_flavor(path: Path) -> Optional[str]:
    """Return 'mingw' or 'msvc' based on path segments (Windows-only heuristic)."""
    lower_parts = [part.lower() for part in path.parts]
    if any("mingw" in part for part in lower_parts):
        return "mingw"
    if any("msvc" in part for part in lower_parts):
        return "msvc"
    return None


def _vswhere_path() -> Optional[Path]:
    """Return vswhere.exe if present in the standard Visual Studio installer dir."""
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if not program_files_x86:
        return None
    path = (
        Path(program_files_x86)
        / "Microsoft Visual Studio"
        / "Installer"
        / "vswhere.exe"
    )
    return path if path.exists() else None


def _vswhere_install_help() -> str:
    return (
        "vswhere.exe not found. Install Visual Studio (or the free Build Tools 2022) "
        "so vswhere.exe is placed under Program Files (x86)/Microsoft Visual Studio/Installer, "
        "or add an existing vswhere.exe to PATH."
    )


_VSWHERE_HINT_EMITTED = False


def _maybe_warn_missing_vswhere() -> None:
    """Emit a one-time hint about installing vswhere when we cannot find it."""
    global _VSWHERE_HINT_EMITTED
    if _VSWHERE_HINT_EMITTED or not sys.platform.startswith("win"):
        return
    _VSWHERE_HINT_EMITTED = True
    print(_vswhere_install_help())


def _vswhere_info() -> Optional[tuple[Optional[str], Optional[str]]]:
    """
    Return (installationPath, installationVersion) for the latest Visual Studio.
    """
    if not sys.platform.startswith("win"):
        return None

    vswhere = _vswhere_path()
    if not vswhere:
        _maybe_warn_missing_vswhere()
        return None

    cmd = [
        str(vswhere),
        "-latest",
        "-products",
        "*",
        "-requires",
        "Microsoft.Component.MSBuild",
        "-format",
        "json",
    ]
    try:
        output = subprocess.check_output(cmd, text=True, encoding="utf-8").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return None

    if not data or not isinstance(data, list):
        return None

    entry = data[0] or {}
    install_path = entry.get("installationPath")
    install_version = entry.get("installationVersion")
    return install_path, install_version


def _has_visual_studio_install() -> bool:
    """
    Detect a Visual Studio toolchain even when cl.exe is not on PATH.
    This prefers MSVC over incidental MinGW tools (e.g., Strawberry Perl).
    """
    if any(os.environ.get(var) for var in ("VCToolsInstallDir", "VCINSTALLDIR", "VSINSTALLDIR")):
        return True

    vswhere = _vswhere_path()
    if not vswhere:
        _maybe_warn_missing_vswhere()
        return False

    cmd = [
        str(vswhere),
        "-latest",
        "-products",
        "*",
        "-requires",
        "Microsoft.Component.MSBuild",
        "-property",
        "installationVersion",
    ]
    try:
        output = subprocess.check_output(cmd, text=True, encoding="utf-8").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return bool(output)


def _detect_visual_studio_generator() -> Optional[str]:
    """
    Return a Visual Studio generator string (e.g., "Visual Studio 17 2022")
    based on the latest installed toolset reported by vswhere.
    """
    if not sys.platform.startswith("win"):
        return None

    info = _vswhere_info()
    if not info:
        return None
    _, version = info
    if not version:
        return None

    try:
        major = int(str(version).split(".", 1)[0])
    except ValueError:
        return None

    if major >= 17:
        return "Visual Studio 17 2022"
    if major == 16:
        return "Visual Studio 16 2019"
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

    if _has_visual_studio_install():
        return "msvc"

    cl_path = shutil.which("cl")
    if cl_path:
        return "msvc"
    gxx_path = shutil.which("g++")
    if gxx_path:
        return "mingw"
    return None


def compiler_install_hint() -> str:
    if sys.platform == "darwin":
        return "Install the Xcode Command Line Tools: xcode-select --install"
    mgr = detect_package_manager()
    if mgr == "apt":
        return "sudo apt-get install build-essential"
    if mgr == "dnf":
        return "sudo dnf install gcc-c++"
    if mgr == "brew":
        return "brew install llvm"
    if mgr == "choco":
        return "Install Visual Studio Build Tools 2022 (Desktop C++ workload) or MinGW-w64."
    return "Install a C++ compiler (clang++/g++) and ensure it is on PATH."


def _compiler_search_dirs(compiler: str) -> list[Path]:
    """Best-effort search dirs via `<compiler> -print-search-dirs` (gcc/clang style)."""
    try:
        output = subprocess.check_output(
            [compiler, "-print-search-dirs"], text=True, encoding="utf-8"
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return []
    for line in output.splitlines():
        if line.lower().startswith("libraries:"):
            _, _, path_list = line.partition("=")
            return [
                Path(p).resolve()
                for p in path_list.strip().split(os.pathsep)
                if p.strip()
            ]
    return []


def _unique_existing_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def _msvc_library_dirs_from_root(root: Path) -> list[Path]:
    """Collect likely MSVC library directories from a VS install or tool root."""
    candidates: list[Path] = []
    vc_tools = root / "VC" / "Tools" / "MSVC"
    if vc_tools.exists():
        versions = sorted(vc_tools.iterdir(), key=lambda p: p.name)
        if versions:
            newest = versions[-1]
            for sub in (newest / "lib", newest / "lib" / "x64", newest / "lib" / "x86"):
                candidates.append(sub)
    for parent in root.parents:
        lib_dir = parent / "lib"
        candidates.append(lib_dir)
        candidates.append(lib_dir / "x64")
        candidates.append(lib_dir / "x86")
    return _unique_existing_paths(candidates)


def _compiler_library_dirs(compiler_path: Optional[str]) -> list[Path]:
    """Return likely library directories for the given compiler path."""
    if not compiler_path:
        return []
    compiler_path = str(compiler_path)
    libs = _compiler_search_dirs(compiler_path)
    if libs:
        return _unique_existing_paths(libs)
    path_obj = Path(compiler_path).resolve()
    candidates = [
        path_obj.parent / "lib",
        path_obj.parent.parent / "lib",
        path_obj.parent.parent / "lib64",
    ]
    return _unique_existing_paths(candidates)


def detect_compiler(
    generator: Optional[str],
) -> tuple[Optional[str], Optional[str], list[Path]]:
    """
    Locate a usable C++ compiler. Returns (description, hint/warning).
    The hint is non-empty when the compiler is missing or needs setup.
    """
    for env_var in ("CXX", "CC"):
        compiler = os.environ.get(env_var)
        if not compiler:
            continue
        resolved = shutil.which(compiler) or (
            str(Path(compiler)) if Path(compiler).exists() else None
        )
        if resolved:
            return f"{resolved} (from ${env_var})", None, _compiler_library_dirs(resolved)
        return None, f"${env_var} points to {compiler}, but it is not executable.", []

    if sys.platform.startswith("win"):
        flavor_hint = detect_compiler_flavor(generator)
        gxx_path = shutil.which("g++")
        cl_path = shutil.which("cl")
        vs_path = _vswhere_path()

        def _msvc_result() -> tuple[Optional[str], Optional[str]]:
            if cl_path:
                return "cl.exe", None
            if vs_path:
                return "Visual Studio toolchain (via vswhere)", None
            return None, None

        def _mingw_result() -> tuple[Optional[str], Optional[str]]:
            if gxx_path:
                return f"MinGW-w64 g++ at {gxx_path}", None
            return None, None

        if flavor_hint == "mingw":
            desc, note = _mingw_result()
            if desc:
                return desc, note, _compiler_library_dirs(gxx_path)
            desc, note = _msvc_result()
            if desc:
                libs = _msvc_library_dirs_from_root(Path(cl_path).resolve()) if cl_path else _msvc_library_dirs_from_root(Path(vs_path)) if vs_path else []
                return desc, note, libs
            desc, note = _mingw_result()
            if desc:
                return desc, note, _compiler_library_dirs(gxx_path)
            return None, "Install MSVC Build Tools or MinGW-w64 and ensure cl.exe/g++.exe is available.", []

        desc, note = _msvc_result()
        if desc:
            libs = _msvc_library_dirs_from_root(Path(cl_path).resolve()) if cl_path else _msvc_library_dirs_from_root(Path(vs_path)) if vs_path else []
            return desc, note, libs
        desc, note = _mingw_result()
        if desc:
            return desc, note, _compiler_library_dirs(gxx_path)

        return None, "Install MSVC Build Tools or MinGW-w64 and ensure cl.exe/g++.exe is available.", []

    for candidate in ("c++", "g++", "clang++"):
        path = shutil.which(candidate)
        if path:
            return f"{candidate} at {path}", None, _compiler_library_dirs(path)

    return None, compiler_install_hint(), []


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
    """Invoke download_qt6.py via the new python.download_qt6 module."""
    cmd: List[str] = [sys.executable, "-m", "python.download_qt6"]
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
        prefix = cmake_dir.parents[2]
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


def qt_library_dirs(prefix: Path) -> list[Path]:
    """Return candidate Qt library directories under the given prefix."""
    dirs: list[Path] = []
    for name in ("lib", "lib64", "Lib"):
        candidate = prefix / name
        if candidate.exists():
            dirs.append(candidate)
    return dirs


def find_pdcurses_paths(build_dir: Path) -> list[Path]:
    """List PDCursesMod locations: vendored source plus any built library dirs."""
    paths: list[Path] = []
    vendored = ROOT / "third_party" / "PDCursesMod"
    if vendored.exists():
        paths.append(vendored)

    if build_dir.exists():
        for ext in ("*.lib", "*.a", "*.so", "*.dylib", "*.dll"):
            for file in build_dir.rglob(ext):
                if "pdcurses" in file.name.lower():
                    parent = file.parent.resolve()
                    if parent not in paths:
                        paths.append(parent)
    return paths


def detect_local_qt_version(qt_prefix_value: Optional[str]) -> tuple[Optional[str], Optional[Path]]:
    """Return (version, prefix) for the local Qt install if found."""
    prefix = resolve_qt_prefix(str(qt_prefix_value) if qt_prefix_value else None)
    if not prefix:
        return None, None
    version_tuple = parse_version_from_path(prefix)
    version = ".".join(str(part) for part in version_tuple) if version_tuple else None
    return version, prefix


def detect_local_pdcurses_version() -> Optional[str]:
    """Read the PDCursesMod version macros from the vendored header."""
    header = ROOT / "third_party" / "PDCursesMod" / "curses.h"
    if not header.exists():
        return None

    text = header.read_text(encoding="utf-8", errors="ignore")

    def _macro_value(name: str) -> Optional[str]:
        match = re.search(rf"{name}\s+(\d+)", text)
        return match.group(1) if match else None

    major = _macro_value("PDC_VER_MAJOR")
    minor = _macro_value("PDC_VER_MINOR")
    patch = _macro_value("PDC_VER_CHANGE")
    if not all((major, minor, patch)):
        return None
    return f"{major}.{minor}.{patch}"


def detect_generator(cli_value: Optional[str]) -> Optional[str]:
    """
    Pick a sensible default generator:
    - CLI value wins
    - $CMAKE_GENERATOR if set
    - On Windows, prefer a Visual Studio generator (works without env setup)
    - Ninja if available
    - otherwise let CMake decide
    """
    if cli_value:
        return cli_value
    if os.environ.get("CMAKE_GENERATOR"):
        return os.environ["CMAKE_GENERATOR"]
    if sys.platform.startswith("win"):
        vs_generator = _detect_visual_studio_generator()
        if vs_generator:
            return vs_generator
    if shutil.which("ninja"):
        return "Ninja"
    return None


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
    if tool in pkg_map:
        return f"Install via your package manager ({' / '.join(pkg_map.keys())})"
    return "Install via your package manager"


def verify_environment(
    qt_prefix: Optional[Path], generator: Optional[str], build_dir: Path
) -> bool:
    """
    Check common requirements (compiler, cmake, generator availability, Qt prefix).
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

    compiler_desc, compiler_hint, compiler_libs = detect_compiler(detected_gen)
    if compiler_desc:
        print(f" - compiler: {compiler_desc}")
        if compiler_hint:
            print(f"   note: {compiler_hint}")
        if compiler_libs:
            print(f" - compiler libs: {', '.join(str(p) for p in compiler_libs)}")
    else:
        ok = False
        hint = compiler_hint or compiler_install_hint()
        print(f" - compiler: MISSING. {hint}")

    resolved_qt = resolve_qt_prefix(str(qt_prefix) if qt_prefix else None, detected_gen)
    compiler_flavor = detect_compiler_flavor(detected_gen)
    if resolved_qt:
        print(f" - Qt prefix: {resolved_qt}")
        libs = qt_library_dirs(resolved_qt)
        if libs:
            print(f" - Qt libs: {', '.join(str(p) for p in libs)}")
        else:
            ok = False
            print(" - Qt libs: not found under prefix (expected lib/lib64).")
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

    pdcurses_paths = find_pdcurses_paths(build_dir)
    if pdcurses_paths:
        print(f" - PDCursesMod: {', '.join(str(p) for p in pdcurses_paths)}")
    else:
        print(" - PDCursesMod: not found (expected under third_party/PDCursesMod or build outputs).")

    return ok


def check_library_updates(qt_prefix_value: Optional[str]) -> bool:
    """
    Check vendored/installed library versions against upstream releases.
    Returns True when all look queryable (even if updates are available).
    """
    print("\nChecking library updates (Qt 6, PDCursesMod):")
    ok = True

    local_qt_version, qt_prefix = detect_local_qt_version(qt_prefix_value)
    latest_qt_version, qt_source, qt_error = fetch_latest_qt_version()
    if qt_prefix:
        version_label = local_qt_version or "unknown version"
        print(f" - Qt local: {version_label} at {qt_prefix}")
    else:
        print(" - Qt local: not detected (set --qt-prefix / QT_PREFIX_PATH / CMAKE_PREFIX_PATH).")
    if latest_qt_version:
        comparison = compare_versions(local_qt_version, latest_qt_version)
        status = ""
        if comparison is not None:
            if comparison < 0:
                status = " (update available)"
            elif comparison == 0:
                status = " (up to date)"
        print(f" - Qt latest: {latest_qt_version} [{qt_source}]{status}")
        if comparison is not None and comparison < 0:
            print(
                f"   hint: run {HELP_URLS['download_script']} --qt-version {latest_qt_version} "
                "to refresh third_party/qt6."
            )
    else:
        ok = False
        print(f" - Qt latest: unavailable ({qt_error or 'unknown error'})")

    local_pdc_version = detect_local_pdcurses_version()
    latest_pdc_version, pdc_source, pdc_error = fetch_latest_pdcurses_version()
    if local_pdc_version:
        print(f" - PDCursesMod local: {local_pdc_version} (third_party/PDCursesMod)")
    else:
        print(" - PDCursesMod local: not found under third_party/PDCursesMod.")
    if latest_pdc_version:
        comparison = compare_versions(local_pdc_version, latest_pdc_version)
        status = ""
        if comparison is not None:
            if comparison < 0:
                status = " (update available)"
            elif comparison == 0:
                status = " (up to date)"
        print(f" - PDCursesMod latest: {latest_pdc_version} [{pdc_source}]{status}")
        if comparison is not None and comparison < 0:
            print("   hint: update the vendored PDCursesMod tree from the upstream release/tag.")
    else:
        ok = False
        print(f" - PDCursesMod latest: unavailable ({pdc_error or 'unknown error'})")

    return ok
