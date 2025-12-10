import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from .constants import (
    DEFAULT_QT_CREATOR_OUTPUT_DIR,
    HELP_URLS,
    QT_CREATOR_EXECUTABLE_NAMES,
    QML_EXCLUDE_DIRS,
    ROOT,
)
from .utils import prompt_for_choice, run_command


def find_qml_files(root: Path) -> list[Path]:
    """
    Locate QML files under the project while skipping generated/vendor trees.
    Avoids crawling heavy third_party/build directories to keep menus snappy.
    """
    qml_files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
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


def _find_qt_creator_in_tree(root: Path) -> Optional[Path]:
    """Return the first Qt Creator executable found inside the provided directory."""
    if not root or not root.exists():
        return None
    for name in QT_CREATOR_EXECUTABLE_NAMES:
        for candidate in root.rglob(name):
            if candidate.is_file():
                return candidate
    return None


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

    found = _find_qt_creator_in_tree(output_dir)
    if found:
        return found
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
    if download_output_dir:
        downloaded = _find_qt_creator_in_tree(download_output_dir)
        if downloaded:
            return downloaded

    env_candidates = [
        os.environ.get("QT_CREATOR_BIN"),
        os.environ.get("QT_CREATOR_PATH"),
    ]
    for value in env_candidates:
        if not value:
            continue
        candidate = Path(value)
        if candidate.is_dir():
            for name in QT_CREATOR_EXECUTABLE_NAMES:
                exe = candidate / name
                if exe.exists():
                    return exe
        if candidate.exists():
            return candidate

    for name in QT_CREATOR_EXECUTABLE_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)

    common_paths: list[Path] = []
    choco_root = os.environ.get("ChocolateyInstall") or os.environ.get("CHOCOLATEYINSTALL")
    choco_tools = os.environ.get("ChocolateyToolsLocation") or os.environ.get("CHOCOLATEYTOOLsLOCATION")
    if choco_root:
        common_paths.extend(
            [
                Path(choco_root) / "bin" / "qtcreator.exe",
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
    from .constants import PACKAGE_NAMES  # deferred to avoid import loops

    ref = PACKAGE_NAMES.get("qtcreator", {})
    hint = "Install via your package manager"
    if ref:
        hint = f"Install via your package manager ({' / '.join(ref.keys())})"
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
            print(
                f"{note} Downloading Qt Creator into {creator_output_dir} to fetch the missing qml2puppet tool."
            )
            creator = download_qt_creator(creator_version, creator_output_dir)
            puppet = find_qml2puppet(creator)
            if not puppet:
                raise SystemExit(
                    note
                    + f" Try reinstalling Qt Creator or checking {creator_output_dir} for a qml2puppet binary."
                )
        else:
            print(f"Warning: {note}")

    run_command([str(creator), str(qml_path)])
