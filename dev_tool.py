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
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
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
    "qt_creator": "https://www.qt.io/product/development-tools",
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
    "qtcreator": {
        "apt": "qtcreator",
        "dnf": "qt-creator",
        "brew": "qt-creator",
        "choco": "qtcreator",
    },
    "qt": {
        "apt": "qt6-base-dev qt6-declarative-dev",
        "dnf": "qt6-qtbase-devel qt6-qtdeclarative-devel",
        "brew": "qt@6",
        "choco": "qt-lts-long-term-release",  # community package; may vary
    },
}
QML_EXCLUDE_DIRS = {".git", ".idea", ".vscode", "__pycache__", "build", "third_party"}
DEFAULT_QT_CREATOR_OUTPUT_DIR = ROOT / "third_party" / "qtcreator"
_VSWHERE_HINT_EMITTED = False

# User settings (persisted in XDG config dir on POSIX or %APPDATA% on Windows).
CONFIG_DIR_NAME = "CPlusPlusQT6Skel"
CONFIG_FILE_NAME = "settings.json"
DEFAULT_SETTINGS = {
    "build_dir": str(DEFAULT_BUILD_DIR),
    "build_type": DEFAULT_BUILD_TYPE,
    "qt_prefix": None,
    "generator": None,
    "download_qt_output_dir": str(ROOT / "third_party" / "qt6"),
    "download_qt_version": None,
    "download_qt_compiler": None,
    "default_run_targets": DEFAULT_RUN_TARGETS,
}

SETTING_DESCRIPTIONS: dict[str, str] = {
    "build_dir": "Build directory (default: settings file or ./build)",
    "build_type": "CMAKE_BUILD_TYPE for single-config generators (default: Debug)",
    "qt_prefix": "Path to Qt installation root",
    "generator": "CMake generator to use",
    "download_qt_output_dir": "Destination for auto-downloaded Qt (default: third_party/qt6)",
    "download_qt_version": "Qt version to fetch when automatically downloading",
    "download_qt_compiler": "Qt compiler flavor/arch used for downloads (e.g. win64_msvc2022_64)",
    "default_run_targets": "Default targets to offer when running or launching the menu",
}


def _config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / CONFIG_DIR_NAME
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / CONFIG_DIR_NAME
    return Path.home() / ".config" / CONFIG_DIR_NAME


def _config_path() -> Path:
    return _config_dir() / CONFIG_FILE_NAME


def _load_settings_file() -> dict:
    path = _config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _normalized_setting(key: str, value: object) -> object:
    if value is None:
        return None
    if key in {"build_dir", "qt_prefix", "download_qt_output_dir"}:
        return str(Path(str(value)).expanduser())
    if key == "default_run_targets":
        if isinstance(value, str):
            parts = [part.strip() for part in value.replace(";", ",").split(",")]
            return [p for p in parts if p]
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return DEFAULT_RUN_TARGETS
    return str(value)


def _merge_settings(user_values: dict) -> dict:
    merged = DEFAULT_SETTINGS.copy()
    for key, value in user_values.items():
        if key not in DEFAULT_SETTINGS:
            continue
        merged[key] = _normalized_setting(key, value)
    return merged


def save_settings(settings: dict) -> None:
    """Persist settings to disk and ensure parent dir exists."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = {
        key: settings.get(key, DEFAULT_SETTINGS[key])
        for key in DEFAULT_SETTINGS
    }
    path.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")


USER_SETTINGS = _merge_settings(_load_settings_file())


def reload_settings() -> dict:
    global USER_SETTINGS
    USER_SETTINGS = _merge_settings(_load_settings_file())
    return USER_SETTINGS


def get_setting(key: str) -> object:
    return USER_SETTINGS.get(key, DEFAULT_SETTINGS.get(key))


def set_settings(updates: dict, *, unset: Iterable[str] = ()) -> dict:
    current = dict(USER_SETTINGS)
    for key in unset:
        if key in DEFAULT_SETTINGS:
            current[key] = DEFAULT_SETTINGS[key]
    for key, value in updates.items():
        if key not in DEFAULT_SETTINGS:
            continue
        current[key] = _normalized_setting(key, value)
    USER_SETTINGS.update(current)
    save_settings(USER_SETTINGS)
    return USER_SETTINGS


def default_run_targets() -> list[str]:
    targets = get_setting("default_run_targets")
    if isinstance(targets, list) and targets:
        return [str(t) for t in targets]
    return DEFAULT_RUN_TARGETS


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


def parse_version_string(value: str) -> tuple[int, ...]:
    """Extract numeric components from a version-like string."""
    parts = [int(x) for x in re.findall(r"\d+", value)]
    return tuple(parts)


def compare_versions(lhs: Optional[str], rhs: Optional[str]) -> Optional[int]:
    """Return -1/0/1 if lhs is older/equal/newer than rhs; None when unknown."""
    if not lhs or not rhs:
        return None
    left = parse_version_string(lhs)
    right = parse_version_string(rhs)
    if not left or not right:
        return None
    return (left > right) - (left < right)


def _latest_version_string(versions: Iterable[str]) -> Optional[str]:
    """Pick the highest semantic-ish version from a sequence of strings."""
    cleaned = []
    for version in versions:
        tupled = parse_version_string(version)
        if not tupled:
            continue
        cleaned.append(version.rstrip("/"))
    if not cleaned:
        return None
    return max(cleaned, key=lambda v: parse_version_string(v))


def _fetch_url(url: str, *, timeout: float = 10.0) -> tuple[Optional[str], Optional[str]]:
    """Fetch text content from a URL, returning (body, error)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="ignore"), None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return None, str(exc)


def _extract_versions_from_listing(html: str, *, segments: Optional[int] = None) -> list[str]:
    """Collect version strings like 6.7.2 from a simple directory listing."""
    matches = re.findall(r'href="((?:\d+\.)+\d+)/"', html)
    versions: list[str] = []
    for match in matches:
        tupled = parse_version_string(match)
        if segments and len(tupled) != segments:
            continue
        versions.append(match.rstrip("/"))
    return versions


def fetch_latest_qt_version() -> tuple[Optional[str], str, Optional[str]]:
    """Return (version, source_url, error) for the newest Qt 6 release."""
    base_url = "https://download.qt.io/official_releases/qt/"
    listing, error = _fetch_url(base_url)
    if not listing:
        return None, base_url, error

    major_minor = [
        version
        for version in _extract_versions_from_listing(listing, segments=2)
        if version.startswith("6.")
    ]
    newest_major_minor = _latest_version_string(major_minor)
    if not newest_major_minor:
        return None, base_url, "No Qt 6 versions found in the release index."

    patch_listing, patch_error = _fetch_url(f"{base_url}{newest_major_minor}/")
    if patch_listing:
        patch_versions = [
            version
            for version in _extract_versions_from_listing(patch_listing, segments=3)
            if version.startswith(newest_major_minor)
        ]
        newest_patch = _latest_version_string(patch_versions)
        if newest_patch:
            return newest_patch, f"{base_url}{newest_major_minor}/", None

    return newest_major_minor, base_url, patch_error


def fetch_latest_pdcurses_version() -> tuple[Optional[str], str, Optional[str]]:
    """Return (version, source_url, error) for the latest PDCursesMod release."""
    api_url = "https://api.github.com/repos/Bill-Gray/PDCursesMod/releases/latest"
    payload, error = _fetch_url(api_url)
    if not payload:
        return None, api_url, error
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        return None, api_url, f"Failed to parse GitHub response: {exc}"

    tag = data.get("tag_name") or data.get("name")
    version = None
    if isinstance(tag, str):
        version = tag.lstrip("vV")
    html_url = data.get("html_url") or api_url
    if not version:
        return None, html_url, "Latest release tag not present in GitHub response."
    return version, html_url, None


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

    # Prefer a detected Visual Studio install even when cl.exe is not on PATH
    # (common when a MinGW toolchain comes earlier in PATH, e.g., Strawberry Perl).
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
    # Walk up from possible cl.exe location
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
        vs_path = os.environ.get("VSINSTALLDIR") or os.environ.get("VCINSTALLDIR")
        vs_info = _vswhere_info()
        if vs_info:
            vs_path = vs_path or vs_info[0]
            vs_version = vs_info[1]
        else:
            vs_version = None

        def _msvc_result() -> tuple[Optional[str], Optional[str]]:
            if cl_path:
                return f"cl.exe at {cl_path}", None
            if vs_path:
                version_label = ""
                if vs_version:
                    major = vs_version.split(".", 1)[0]
                    version_label = f" (VS {major})"
                return (
                    f"MSVC{version_label} at {vs_path}",
                    "MSVC found but cl.exe is not on PATH. Open an \"x64 Native Tools Command Prompt for VS\" (or run VsDevCmd.bat/vcvarsall.bat) so the compiler environment is initialized.",
                )
            if _has_visual_studio_install():
                return (
                    "MSVC detected (path unknown)",
                    "MSVC found but cl.exe is not on PATH. Open an \"x64 Native Tools Command Prompt for VS\" (or run VsDevCmd.bat/vcvarsall.bat) so the compiler environment is initialized.",
                )
            return None, None

        def _mingw_result() -> tuple[Optional[str], Optional[str]]:
            if gxx_path:
                label = "MinGW g++" if "mingw" in gxx_path.lower() else "g++"
                return f"{label} at {gxx_path}", None
            return None, None

        if flavor_hint == "msvc":
            desc, note = _msvc_result()
            if desc:
                libs = _msvc_library_dirs_from_root(Path(cl_path).resolve()) if cl_path else _msvc_library_dirs_from_root(Path(vs_path)) if vs_path else []
                return desc, note, libs
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


def apply_settings_to_args(args: argparse.Namespace) -> argparse.Namespace:
    """Fill in defaults from settings when CLI arguments are omitted."""
    def _path_from_setting(key: str, fallback: Path) -> Path:
        value = get_setting(key)
        return Path(value) if value else fallback

    if getattr(args, "build_dir", None) is None:
        args.build_dir = _path_from_setting("build_dir", DEFAULT_BUILD_DIR)
    if getattr(args, "build_type", None) is None:
        args.build_type = str(get_setting("build_type") or DEFAULT_BUILD_TYPE)
    if getattr(args, "qt_prefix", None) is None:
        args.qt_prefix = get_setting("qt_prefix")
    if getattr(args, "generator", None) is None:
        args.generator = get_setting("generator")
    if getattr(args, "download_qt_output_dir", None) is None:
        args.download_qt_output_dir = _path_from_setting("download_qt_output_dir", ROOT / "third_party" / "qt6")
    if hasattr(args, "output_dir") and getattr(args, "output_dir", None) is None:
        args.output_dir = args.download_qt_output_dir
    if getattr(args, "download_qt_version", None) is None:
        args.download_qt_version = get_setting("download_qt_version")
    if hasattr(args, "qt_version") and getattr(args, "qt_version", None) is None:
        args.qt_version = args.download_qt_version
    if getattr(args, "download_qt_compiler", None) is None:
        args.download_qt_compiler = get_setting("download_qt_compiler")
    if hasattr(args, "compiler") and getattr(args, "compiler", None) is None:
        args.compiler = args.download_qt_compiler
    return args


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


def _clear_build_dir(build_dir: Path) -> None:
    """Remove an existing build directory to allow reconfiguration."""
    if not build_dir.exists():
        return
    print(f"Clearing existing build directory: {build_dir}")
    shutil.rmtree(build_dir)


def _resolve_generator_for_build_dir(
    build_dir: Path,
    requested_generator: Optional[str],
    *,
    generator_is_strict: bool,
) -> Optional[str]:
    """
    Reconcile a requested generator with any existing CMake cache.

    If the build directory already has a cache configured with a different
    generator, either reuse the cached one (for auto-detected generators) or
    prompt/abort when the user explicitly requested a new generator.
    """
    cached = read_generator_from_cache(build_dir)
    if cached and not requested_generator:
        print(
            f"Reusing cached CMake generator '{cached}' from build directory {build_dir}"
        )
        return cached

    if cached and requested_generator and cached != requested_generator:
        message = (
            f"Build directory {build_dir} was configured with generator '{cached}', "
            f"but '{requested_generator}' was requested."
        )
        if not generator_is_strict:
            print(f"{message} Reusing cached generator.")
            return cached

        if prompt_yes_no(
            "Clear the existing build directory to switch generators?", default=False
        ):
            _clear_build_dir(build_dir)
            return requested_generator

        raise SystemExit(
            message
            + " Delete or choose a different --build-dir to switch generators, "
            "or rerun without --generator to reuse the cached generator."
        )

    return requested_generator


def configure_project(
    build_dir: Path,
    generator: Optional[str],
    build_type: str,
    qt_prefix: Optional[Path],
    *,
    generator_is_strict: bool = False,
) -> Optional[str]:
    if build_dir.exists() and not build_dir.is_dir():
        raise SystemExit(f"Build path exists and is not a directory: {build_dir}")

    generator = _resolve_generator_for_build_dir(
        build_dir, generator, generator_is_strict=generator_is_strict
    )

    build_dir.mkdir(parents=True, exist_ok=True)

    cmd: List[str] = ["cmake", "-S", str(ROOT), "-B", str(build_dir)]
    if generator:
        cmd += ["-G", generator]
    if qt_prefix:
        cmd.append(f"-DCMAKE_PREFIX_PATH={qt_prefix}")
    if build_type:
        cmd.append(f"-DCMAKE_BUILD_TYPE={build_type}")

    run_command(cmd)
    return generator


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
    for name in found + default_run_targets():
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


def find_qml_files(root: Path) -> list[Path]:
    """
    Locate QML files under the project while skipping generated/vendor trees.
    Avoids crawling heavy third_party/build directories to keep menus snappy.
    """
    qml_files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune unwanted directories in-place so os.walk does not descend.
        dirnames[:] = [
            d for d in dirnames if d not in QML_EXCLUDE_DIRS and not d.startswith(".")
        ]
        for filename in filenames:
            if filename.lower().endswith(".qml"):
                qml_files.append(Path(dirpath) / filename)
    return sorted(qml_files, key=lambda p: p.relative_to(root))


def _ensure_aqt() -> None:
    """Ensure the aqtinstall package is available for downloading Qt Creator."""
    try:
        import aqt  # type: ignore  # noqa: F401
        return
    except ImportError:
        print("Installing aqtinstall (needed to download Qt Creator)...")
        run_command([sys.executable, "-m", "pip", "install", "--upgrade", "aqtinstall"])


def download_qt_creator(version: Optional[str], output_dir: Path) -> Path:
    """
    Download Qt Creator (includes qml2puppet) via aqtinstall and return the executable path.
    """
    _ensure_aqt()
    host = "windows" if sys.platform.startswith("win") else ("mac" if sys.platform == "darwin" else "linux")
    version_arg = version or "latest"
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "aqt",
        "install-tool",
        host,
        "desktop",
        "qtcreator",
        version_arg,
        "--outputdir",
        str(output_dir),
    ]
    run_command(cmd)

    exe_names = ["qtcreator.exe", "qtcreator", "Qt Creator"]
    for name in exe_names:
        found = list(output_dir.rglob(name))
        if found:
            return found[0]
    raise SystemExit(
        f"Downloaded Qt Creator to {output_dir}, but could not locate the executable. "
        "Please check the download contents manually."
    )


def locate_qt_creator(
    *,
    allow_download: bool = False,
    download_version: Optional[str] = None,
    download_output_dir: Path = DEFAULT_QT_CREATOR_OUTPUT_DIR,
) -> Optional[Path]:
    """
    Best-effort lookup for Qt Creator binary via PATH, env hints, and defaults.
    """
    exe_names = ["qtcreator.exe", "qtcreator", "Qt Creator"]
    env_candidates = [
        os.environ.get("QT_CREATOR_BIN"),
        os.environ.get("QT_CREATOR_PATH"),
    ]
    for value in env_candidates:
        if not value:
            continue
        candidate = Path(value)
        if candidate.is_dir():
            for name in exe_names:
                exe = candidate / name
                if exe.exists():
                    return exe
        if candidate.exists():
            return candidate

    for name in exe_names:
        found = shutil.which(name)
        if found:
            return Path(found)

    common_paths: list[Path] = []
    choco_root = os.environ.get("ChocolateyInstall") or os.environ.get("CHOCOLATEYINSTALL")
    choco_tools = os.environ.get("ChocolateyToolsLocation") or os.environ.get("CHOCOLATEYTOOLsLOCATION")
    if choco_root:
        common_paths.extend(
            [
                Path(choco_root) / "bin" / "qtcreator.exe",  # shim
                Path(choco_root) / "lib" / "qtcreator" / "tools" / "qtcreator" / "bin" / "qtcreator.exe",
            ]
        )
    if choco_tools:
        common_paths.append(Path(choco_tools) / "qtcreator" / "bin" / "qtcreator.exe")
    if sys.platform.startswith("win"):
        common_paths = [
            *common_paths,
            Path("C:/Qt/Tools/QtCreator/bin/qtcreator.exe"),
            Path("C:/Program Files/Qt/QtCreator/bin/qtcreator.exe"),
            Path("C:/Program Files/QtCreator/bin/qtcreator.exe"),
        ]
    elif sys.platform == "darwin":
        common_paths = [
            Path("/Applications/Qt Creator.app/Contents/MacOS/Qt Creator"),
        ]
    else:
        common_paths = [
            Path("/usr/bin/qtcreator"),
            Path("/usr/local/bin/qtcreator"),
        ]

    for candidate in common_paths:
        if candidate.exists():
            return candidate
    if allow_download:
        return download_qt_creator(download_version, download_output_dir)
    return None


def qt_creator_install_help() -> str:
    hint = package_install_hint("qtcreator")
    return (
        "Qt Creator not found. Set QT_CREATOR_BIN to the executable or install it "
        f"(Qt online installer: {HELP_URLS['qt_creator']}; package manager e.g. \"{hint}\")."
    )


def find_qml2puppet(creator_exe: Path) -> Optional[Path]:
    """
    Look for qml2puppet alongside a Qt Creator install; Designer needs this binary.
    """
    search_roots = [
        creator_exe.parent,
        creator_exe.parent.parent,
        creator_exe.parent.parent.parent,
    ]
    names = ["qml2puppet.exe", "qml2puppet"]
    for root in search_roots:
        for name in names:
            candidate = root / name
            if candidate.exists():
                return candidate
        for candidate in root.glob("qml2puppet*"):
            if candidate.is_file():
                return candidate
    return None


def choose_qml_file(cli_value: Optional[str]) -> Path:
    if cli_value:
        provided = Path(cli_value)
        if not provided.is_absolute():
            provided = ROOT / provided
        if not provided.exists():
            raise SystemExit(f"QML file not found: {provided}")
        return provided

    qml_files = find_qml_files(ROOT)
    if not qml_files:
        raise SystemExit("No QML files found under project (excluding build/third_party).")

    labels = [str(path.relative_to(ROOT)) for path in qml_files]
    chosen = prompt_for_choice(labels, prompt="Select QML file to open in Qt Creator")
    return ROOT / chosen


def open_qml_in_qt_creator(
    qml_path: Path,
    *,
    ensure_creator: bool = False,
    creator_version: Optional[str] = None,
    creator_output_dir: Path = DEFAULT_QT_CREATOR_OUTPUT_DIR,
) -> None:
    creator = locate_qt_creator(
        allow_download=ensure_creator,
        download_version=creator_version,
        download_output_dir=creator_output_dir,
    )
    if not creator:
        raise SystemExit(qt_creator_install_help())
    if not qml_path.exists():
        raise SystemExit(f"QML file does not exist: {qml_path}")

    puppet = find_qml2puppet(creator)
    if not puppet:
        note = (
            "qml2puppet was not found near your Qt Creator installation. "
            "Qt Quick Designer may not render live previews until it is available."
        )
        if ensure_creator:
            raise SystemExit(
                note
                + f" Try reinstalling Qt Creator or checking {creator_output_dir} for a qml2puppet binary."
            )
        print(f"Warning: {note}")

    run_command([str(creator), str(qml_path)])


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


def _print_settings(settings: dict) -> None:
    print("Settings file:", _config_path())
    for key in sorted(DEFAULT_SETTINGS.keys()):
        print(f"  {key}: {settings.get(key)!r}")


def _parse_setting_arg(arg: str) -> tuple[str, str]:
    if "=" not in arg:
        raise ValueError("Must be KEY=VALUE")
    key, value = arg.split("=", 1)
    return key.strip(), value.strip()


def edit_settings_interactive(settings: dict) -> dict:
    """TTY-driven settings menu."""
    if not sys.stdin.isatty():
        print("Interactive edit requires a TTY. Use --set KEY=VALUE instead.")
        return settings

    keys = list(DEFAULT_SETTINGS)
    draft = dict(settings)
    updates: dict[str, Optional[str]] = {}

    print(
        "Select a setting to edit from the numbered list below. "
        "Press Enter without a selection to finish, or type 'q' to quit."
    )
    print("Type 'none' (or 'null') when you want to clear an optional value.\n")

    while True:
        print()
        print("Settings file:", _config_path())
        for idx, key in enumerate(keys, start=1):
            desc = SETTING_DESCRIPTIONS.get(key)
            value = draft.get(key)
            desc_text = f" - {desc}" if desc else ""
            print(f"[{idx}] {key}{desc_text} (current: {value!r})")
        choice = input(f"Select [1-{len(keys)}] (Enter to finish): ").strip()
        if not choice:
            break
        if choice.lower() in {"q", "quit", "exit"}:
            break
        if not choice.isdigit():
            print("Invalid selection, enter a number or 'q'.")
            continue
        index = int(choice)
        if not (1 <= index <= len(keys)):
            print(f"Invalid number (1-{len(keys)}).")
            continue
        key = keys[index - 1]
        current_value = draft.get(key)
        new_value = input(
            f"New value for {key} [{current_value!r}] (Enter to keep): "
        ).strip()
        if not new_value:
            continue
        if new_value.lower() in {"none", "null"}:
            draft[key] = None
            updates[key] = None
            continue
        draft[key] = new_value
        updates[key] = new_value

    if updates:
        return set_settings(updates)
    return settings


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
        # No set/unset: enter interactive editor.
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
        # Choose high-level action.
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


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\nCommand failed with exit code {exc.returncode}")
        raise
