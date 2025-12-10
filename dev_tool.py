#!/usr/bin/env python3
"""Entry point that delegates to the consolidated python.dev_tool package."""

import shutil
import subprocess

from python.dev_tool import (
    DEFAULT_BUILD_DIR,
    USER_SETTINGS,
    detect_generator,
    find_built_binary,
    get_setting,
    list_runnable_targets,
    main,
    prompt_for_choice,
    resolve_qt_prefix,
    run_command,
    set_settings,
)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"\nCommand failed with exit code {exc.returncode}")
        raise
