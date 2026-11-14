from __future__ import annotations

import subprocess

from habit_hooks.project_paths import venv_executable


def test_installed_init_yes_configures_without_input(ready_project, installed_habit_sensors):
    command = venv_executable(installed_habit_sensors.parent.parent, "habit-hooks")

    result = subprocess.run([str(command), "init", "--yes"], cwd=ready_project, input="", capture_output=True, encoding="utf-8", errors="replace")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "habit-hooks configured" in result.stderr
    assert "Added: .habit-hooks/config.toml" in result.stderr
    assert (ready_project / ".habit-hooks/config.toml").read_text(encoding="utf-8") == 'plugins = ["python", "generic"]\n'
