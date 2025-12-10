import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable, Optional

from .constants import (
    CONFIG_DIR_NAME,
    CONFIG_FILE_NAME,
    DEFAULT_BUILD_DIR,
    DEFAULT_BUILD_TYPE,
    DEFAULT_QT_CREATOR_OUTPUT_DIR,
    DEFAULT_SETTINGS,
    DEFAULT_RUN_TARGETS,
    ROOT,
    SETTING_DESCRIPTIONS,
)


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
        args.download_qt_output_dir = _path_from_setting(
            "download_qt_output_dir",
            ROOT / "third_party" / "qt6",
        )
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
