from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

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
        "choco": "qt-lts-long-term-release",
    },
}
QML_EXCLUDE_DIRS = {".git", ".idea", ".vscode", "__pycache__", "build", "third_party"}
DEFAULT_QT_CREATOR_OUTPUT_DIR = ROOT / "third_party" / "qtcreator"
QT_CREATOR_EXECUTABLE_NAMES = ["qtcreator.exe", "qtcreator", "Qt Creator"]

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
