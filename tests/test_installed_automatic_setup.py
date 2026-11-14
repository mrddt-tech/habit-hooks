from __future__ import annotations

import subprocess

from habit_hooks.project_paths import venv_executable
from plugin_fixture import write_plugin


def test_installed_command_configures_then_checks_a_new_file(installed_habit_sensors, tmp_path):
    write_plugin(tmp_path, "generic", {"config.toml": "detectors = []\n"})
    write_plugin(tmp_path, "python", {"config.toml": 'files = ["**/*.py"]\ndetectors = []\nsensors = ["check"]\n', "sensors/check.toml": 'command = "echo []"\n'})
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    command = venv_executable(installed_habit_sensors.parent.parent, "habit-hooks")

    first = subprocess.run([str(command), "--file", "app.py"], cwd=tmp_path, capture_output=True, encoding="utf-8", errors="replace")
    second = subprocess.run([str(command), "--file", "app.py"], cwd=tmp_path, capture_output=True, encoding="utf-8", errors="replace")

    assert first.returncode == 0, first.stderr + first.stdout
    assert "habit-hooks configured" in first.stderr
    assert "Added: .habit-hooks/config.toml" in first.stderr
    assert "automated checks passed" in first.stdout
    assert second.returncode == 0, second.stderr + second.stdout
    assert "habit-hooks configured" not in second.stderr
