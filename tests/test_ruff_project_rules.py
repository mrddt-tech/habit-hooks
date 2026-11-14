from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from habit_hooks import mapper
from habit_hooks.cli import ConfigError
from habit_hooks.config import SensorOverride, load_config
from habit_hooks.project_paths import venv_executable
from habit_hooks.scope import Scope
from habit_hooks.sensors import Execution, PluginLoader
from habit_hooks.resolve import Resolver
from habit_hooks_python.sensors import ruff_sensor


@pytest.fixture
def ruff_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".habit-hooks").mkdir()
    (tmp_path / ".habit-hooks/config.toml").write_text('plugins = ["python"]\n[sensors.comment]\ndisabled = true\n[sensors.deptry]\ndisabled = true\n', encoding="utf-8")
    (tmp_path / "ruff.toml").write_text("", encoding="utf-8")
    (tmp_path / "example.py").write_text("import os\nprint(undefined_test_name)\n", encoding="utf-8")
    return tmp_path


def _settings(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"[ruff]\nproject_rules = {value}\n", encoding="utf-8")


def _enabled(project: Path) -> None:
    _settings(ruff_sensor.settings_paths(project)[0], "true")


def _findings(project: Path, flags: tuple[str, ...] = ()) -> list[dict]:
    config = load_config(project)
    config.sensors["ruff"] = SensorOverride(args=list(flags))
    plugin = PluginLoader(Resolver.discover(project), config).load_plugin("python")
    sensor = next(sensor for sensor in plugin.sensors if sensor.name == "ruff")
    return Execution(project, Scope(["example.py"])).run_sensor(sensor)


def test_default_selection_is_unchanged(ruff_project):
    assert [finding["smell"] for finding in _findings(ruff_project)] == ["unused-import"]


def test_global_option_enables_default_ruff_rules(ruff_project):
    _enabled(ruff_project)
    findings = _findings(ruff_project)

    assert {finding["smell"] for finding in findings} == {"unused-import", "F821"}
    assert next(f for f in findings if f["smell"] == "F821")["details"] == {"diagnostic": True, "tool": "ruff"}


def test_project_false_overrides_global_true(ruff_project):
    _enabled(ruff_project)
    _settings(ruff_sensor.settings_paths(ruff_project)[1], "false")

    assert [finding["smell"] for finding in _findings(ruff_project)] == ["unused-import"]


def test_project_true_overrides_global_false(ruff_project):
    global_path, local_path = ruff_sensor.settings_paths(ruff_project)
    _settings(global_path, "false")
    _settings(local_path, "true")

    assert "F821" in {finding["smell"] for finding in _findings(ruff_project)}


def test_project_ruff_selection_is_not_extended_with_coaching_rules(ruff_project):
    _enabled(ruff_project)
    (ruff_project / "ruff.toml").write_text('lint.select = ["F821"]\n', encoding="utf-8")

    assert [finding["smell"] for finding in _findings(ruff_project)] == ["F821"]


def test_project_ruff_ignores_are_respected(ruff_project):
    _enabled(ruff_project)
    (ruff_project / "ruff.toml").write_text('lint.ignore = ["F401", "F821"]\n', encoding="utf-8")

    assert _findings(ruff_project) == []


@pytest.mark.parametrize("flags", [("--select", "F401"), ("--select=F401",), ("--ignore", "F821")])
def test_explicit_flags_follow_native_precedence(ruff_project, flags):
    _enabled(ruff_project)

    assert [finding["smell"] for finding in _findings(ruff_project, flags)] == ["unused-import"]


def test_explicit_select_uses_native_aggregation_when_disabled(ruff_project):
    findings = _findings(ruff_project, ("--select=F821",))

    assert {finding["smell"] for finding in findings} == {"F821", "unused-import"}
    assert all(finding["details"] == {} for finding in findings)


def test_explicit_extend_select_keeps_automatic_rules_when_disabled(ruff_project):
    assert {f["smell"] for f in _findings(ruff_project, ("--extend-select=F821",))} == {"unused-import", "F821"}


def test_explicit_config_uses_native_ruff_precedence(ruff_project):
    _enabled(ruff_project)
    alternate = ruff_project / "alternate.toml"
    alternate.write_text('lint.select = ["F821"]\n', encoding="utf-8")

    assert [finding["smell"] for finding in _findings(ruff_project, ("--config", str(alternate)))] == ["F821"]


def test_coaching_precedes_remaining_findings_without_duplicates(ruff_project, capsys):
    _enabled(ruff_project)

    assert mapper.run(_findings(ruff_project), ruff_project) == 1

    output = capsys.readouterr().out
    assert output.index("── unused-import") < output.index("── ruff")
    assert output.count("ruff:F821") == 1
    assert "example.py:2:7:" in output
    assert "uncoached" not in output


def test_diagnostics_alone_fail_even_if_uncoached_findings_are_ignored(ruff_project, capsys):
    _enabled(ruff_project)
    (ruff_project / "example.py").write_text("print(undefined_test_name)\n", encoding="utf-8")
    (ruff_project / ".habit-hooks/config.toml").write_text('plugins = ["python"]\nuncoached = "ignore"\n', encoding="utf-8")

    assert mapper.run(_findings(ruff_project), ruff_project) == 1
    output = capsys.readouterr().out
    assert "ruff:F821" in output
    assert "checks passed" not in output


@pytest.mark.parametrize("value", ['"true"', "1", "[]"])
def test_invalid_settings_are_rejected(ruff_project, value):
    _settings(ruff_sensor.settings_paths(ruff_project)[0], value)

    with pytest.raises(ConfigError, match="true or false"):
        ruff_sensor.project_rules(ruff_project)


@pytest.mark.parametrize("configured", ["", "relative/config"])
def test_xdg_requires_an_absolute_directory(tmp_path, monkeypatch, configured):
    monkeypatch.setenv("XDG_CONFIG_HOME", configured)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert ruff_sensor.settings_paths(tmp_path)[0] == tmp_path / ".config/habit-hooks/python/settings.toml"


def test_installed_command_coaches_then_displays_remaining_findings(ruff_project, installed_habit_sensors):
    command = venv_executable(installed_habit_sensors.parent.parent, "habit-hooks")
    args = [str(command), "--file", "example.py"]
    default = subprocess.run(args, cwd=ruff_project, capture_output=True, encoding="utf-8", errors="replace")
    _enabled(ruff_project)
    enabled = subprocess.run(args, cwd=ruff_project, capture_output=True, encoding="utf-8", errors="replace")

    assert default.returncode == enabled.returncode == 1
    assert "F821" not in default.stdout
    assert enabled.stdout.index("── unused-import") < enabled.stdout.index("── ruff")
    assert enabled.stdout.count("ruff:F821") == 1
    assert "incomplete-run" not in enabled.stdout
