from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from habit_hooks.cli import ConfigError, ToolError
from habit_hooks.config_schema import read_toml, reject_unknown
from habit_hooks.project_paths import tool_executable

SELECTED_CODES = "C901,PLR0913,PLR0915,F841,F401,BLE001"


def settings_paths(project_dir: Path) -> tuple[Path, Path]:
    configured = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not configured.is_absolute():
        configured = Path.home() / ".config"
    return (
        configured / "habit-hooks/python/settings.toml",
        project_dir / ".habit-hooks/python/settings.toml",
    )


def project_rules(project_dir: Path) -> bool:
    enabled = False
    for path in settings_paths(project_dir):
        if path.is_file():
            enabled = _setting(path, enabled)
    return enabled


def _setting(path: Path, default: bool) -> bool:
    data = read_toml(path)
    reject_unknown({"ruff"}, data, str(path))
    ruff = data.get("ruff", {})
    if not isinstance(ruff, dict):
        raise ConfigError(f"{path}: 'ruff' must be a table")
    reject_unknown({"project_rules"}, ruff, f"{path} [ruff]")
    enabled = ruff.get("project_rules", default)
    if not isinstance(enabled, bool):
        raise ConfigError(f"{path}: 'project_rules' must be true or false")
    return enabled


def run_ruff(arguments: list[str], enabled: bool) -> subprocess.CompletedProcess[str]:
    tool, *arguments = arguments
    executable = tool_executable(tool, Path.cwd()) or tool
    separator = arguments.index("--")
    flags, files = arguments[:separator], arguments[separator + 1:]
    selected = [] if enabled else [f"--select={SELECTED_CODES}"]
    return subprocess.run(
        [executable, "check", "--output-format=json", *selected, *flags, "--", *files],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def emit(result: subprocess.CompletedProcess[str], enabled: bool) -> int:
    sys.stderr.write(result.stderr)
    if result.returncode not in (0, 1):
        sys.stdout.write(result.stdout)
        return result.returncode
    findings = json.loads(result.stdout)
    if enabled:
        for finding in findings:
            finding["habit_hooks_project_rules"] = True
    sys.stdout.write(json.dumps(findings))
    return result.returncode


def main(arguments: list[str]) -> int:
    try:
        enabled = project_rules(Path.cwd())
        return emit(run_ruff(arguments, enabled), enabled)
    except (ToolError, OSError, ValueError, TypeError) as error:
        sys.stderr.write(f"ruff sensor: {error}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
