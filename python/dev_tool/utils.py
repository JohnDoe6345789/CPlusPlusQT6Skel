import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple


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
