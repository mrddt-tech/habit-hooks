from __future__ import annotations

import pytest
from attrs import evolve

from habit_hooks import init_command, setup
from habit_hooks.detectors import Detector
from habit_hooks.initialise import plan


def test_init_yes_uses_shared_setup_without_prompting(ready_project, capsys):
    assert init_command.run(["--yes"]) == 0
    assert "habit-hooks configured" in capsys.readouterr().err


def test_setup_installs_plugins_then_their_tools(ready_project, monkeypatch):
    ready = plan(ready_project)
    plugins_missing = evolve(ready, uninstalled_plugins=("python",), plugin_installs=("install-plugin",))
    tools_missing = evolve(ready, missing_tools=(Detector("ruff", "command", "install-tool"),))
    stages = iter((plugins_missing, tools_missing, ready))
    monkeypatch.setattr(setup, "plan", lambda *args: next(stages))
    installed = []

    def install(command, **kwargs):
        installed.append(command)
        (ready_project / "package.json").write_text(command, encoding="utf-8")
        return True

    monkeypatch.setattr(init_command, "_succeeded", install)
    assert init_command.run(["--yes"]) == 0
    assert installed == ["install-plugin", "install-tool"]


def test_setup_reports_modified_project_files(ready_project, monkeypatch, capsys):
    ready = plan(ready_project)
    missing = evolve(ready, missing_tools=(Detector("missing", "command", "install-missing"),))
    stages = iter((missing, ready))
    monkeypatch.setattr(setup, "plan", lambda *args: next(stages))

    def install(*args, **kwargs):
        (ready_project / "app.py").write_text("print('updated')\n", encoding="utf-8")
        return True

    monkeypatch.setattr(init_command, "_succeeded", install)
    assert init_command.run(["--yes"]) == 0
    assert "Modified: app.py" in capsys.readouterr().err


@pytest.mark.parametrize("success", [False, True])
def test_failed_or_ineffective_install_returns_failure(ready_project, monkeypatch, success):
    missing = evolve(plan(ready_project), missing_tools=(Detector("missing", "command", "install-missing"),))
    monkeypatch.setattr(setup, "plan", lambda *args: missing)
    monkeypatch.setattr(init_command, "_succeeded", lambda *args, **kwargs: success)

    assert init_command.run(["--yes"]) == 1
    assert not (ready_project / ".habit-hooks/config.toml").exists()


def test_init_yes_preserves_existing_configuration(ready_project):
    config = ready_project / ".habit-hooks/config.toml"
    content = 'plugins = ["generic"]\n\n'
    config.write_text(content, encoding="utf-8")

    assert init_command.run(["--yes"]) == 0
    assert config.read_text(encoding="utf-8") == content


def test_init_yes_reports_added_files(ready_project, capsys):
    assert init_command.run(["--yes"]) == 0

    output = capsys.readouterr()
    assert output.out == ""
    assert "Added: .habit-hooks/config.toml" in output.err
    assert "[y/N]" not in output.err
