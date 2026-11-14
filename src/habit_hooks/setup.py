from __future__ import annotations

import hashlib
import os
import sys
from importlib import invalidate_caches
from pathlib import Path

from . import resolve
from .initialise import plan
from .recommend import DEPENDENCY_DIRECTORIES


EXCLUDED_DIRECTORIES = DEPENDENCY_DIRECTORIES | {".git", "__pycache__"}


def _snapshot(project_dir: Path) -> dict[str, bytes]:
    result = {}
    for root, directories, files in os.walk(project_dir):
        directories[:] = [name for name in directories if name not in EXCLUDED_DIRECTORIES]
        for name in files:
            path = Path(root) / name
            if not path.is_symlink():
                result[path.relative_to(project_dir).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).digest()
    return result


def _changes(project_dir: Path, before: dict[str, bytes]) -> None:
    after = _snapshot(project_dir)
    for name in sorted(before.keys() | after.keys()):
        if name not in before:
            sys.stderr.write(f"  Added: {name}\n")
        elif name not in after:
            sys.stderr.write(f"  Removed: {name}\n")
        elif before[name] != after[name]:
            sys.stderr.write(f"  Modified: {name}\n")


def _refresh_plugins() -> None:
    invalidate_caches()
    for lookup in (resolve.installed_plugin_dirs, resolve.installed_plugin_distributions):
        clear = getattr(lookup, "cache_clear", None)
        if clear is not None:
            clear()


def _install(commands: tuple[str, ...], attempted: set[str]) -> bool:
    from .init_command import _succeeded

    pending = [command for command in commands if command not in attempted]
    if not pending:
        sys.stderr.write("habit-hooks setup failed: dependencies are still missing.\n")
        return False
    for command in pending:
        attempted.add(command)
        sys.stderr.write(f"Installing: {command}\n")
        if not _succeeded(command, diagnostics=True):
            sys.stderr.write(f"habit-hooks setup failed: {command}\n")
            return False
    _refresh_plugins()
    return True


def _ready(project_dir: Path) -> bool:
    from .init_command import _write_config

    attempted: set[str] = set()
    while True:
        planned = plan(project_dir)
        if not planned.uninstalled_plugins and not planned.missing_tools:
            if not planned.already_configured:
                _write_config(project_dir, planned.plugins)
            return True
        if not _install(planned.plugin_installs or planned.installs, attempted):
            return False


def configure(project_dir: Path) -> int:
    before = _snapshot(project_dir)
    ready = _ready(project_dir)
    if ready:
        sys.stderr.write("habit-hooks configured\n")
    _changes(project_dir, before)
    return 0 if ready else 1
