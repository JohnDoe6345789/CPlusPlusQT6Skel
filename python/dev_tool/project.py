import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Optional, Sequence

from .config import default_run_targets
from .constants import NON_RUN_TARGETS, ROOT
from .utils import prompt_yes_no, run_command


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

    cmd = ["cmake", "-S", str(ROOT), "-B", str(build_dir)]
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

    cmd: list[str] = ["cmake", "--build", str(build_dir)]
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

    cmd: list[str] = ["ctest", "--test-dir", str(build_dir)]
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
        build_dir / target / exe_name,
    ]
    if config:
        candidates.append(build_dir / config / exe_name)
        candidates.append(build_dir / config / target / exe_name)

    for candidate in candidates:
        if candidate.exists():
            return candidate

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

    seen = set()
    cleaned: list[str] = []
    for name in found + default_run_targets():
        if name in NON_RUN_TARGETS or name in seen:
            continue
        seen.add(name)
        cleaned.append(name)
    return cleaned
