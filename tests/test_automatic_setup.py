from __future__ import annotations

from pathlib import Path

import pytest
from attrs import evolve
from habit_hooks import hooks, init_command, setup
from habit_hooks.detectors import Detector
from habit_hooks.initialise import plan
from plugin_fixture import write_plugin


@pytest.fixture
def source_project(init_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    write_plugin(init_project, "python", {"config.toml": "detectors = []\n"})
    (init_project / "app.py").write_text("print('hello')\n", encoding="utf-8")
    monkeypatch.chdir(init_project)
    return init_project


def test_first_file_run_configures_before_scanning(source_project, monkeypatch, capsys):
    scanned = []
    monkeypatch.setattr(hooks, "_pipeline", lambda args: scanned.append(args) or 0)

    assert hooks.main(["--file", "app.py"]) == 0

    config = source_project / ".habit-hooks/config.toml"
    assert config.read_text(encoding="utf-8") == 'plugins = ["python", "generic"]\n'
    assert scanned == [["--file", "app.py"]]
    output = capsys.readouterr()
    assert output.out == ""
    assert "habit-hooks configured" in output.err
    assert "Added: .habit-hooks/config.toml" in output.err


def test_existing_config_is_not_changed(source_project, monkeypatch, capsys):
    config = source_project / ".habit-hooks/config.toml"
    config.write_text('plugins = ["generic"]\n', encoding="utf-8")
    monkeypatch.setattr(hooks, "_pipeline", lambda args: 0)

    assert hooks.main(["--file", "app.py"]) == 0
    assert config.read_text(encoding="utf-8") == 'plugins = ["generic"]\n'
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("args", [["--all"], ["--file", "absent.py"], ["--file", "notes.txt"], ["--file", "app.py", "--config", "custom.toml"]])
def test_other_runs_do_not_configure(source_project, monkeypatch, args):
    (source_project / "notes.txt").write_text("hello\n", encoding="utf-8")
    monkeypatch.setattr(hooks, "_pipeline", lambda args: 0)

    assert hooks.main(args) == 0
    assert not (source_project / ".habit-hooks/config.toml").exists()


def test_init_yes_uses_shared_setup_without_prompting(source_project, capsys):
    assert init_command.run(["--yes"]) == 0
    assert "habit-hooks configured" in capsys.readouterr().err


def test_setup_installs_plugins_then_their_tools(source_project, monkeypatch):
    ready = plan(source_project, ["app.py"])
    plugins_missing = evolve(ready, uninstalled_plugins=("python",), plugin_installs=("install-plugin",))
    tools_missing = evolve(ready, missing_tools=(Detector("ruff", "command", "install-tool"),))
    stages = iter((plugins_missing, tools_missing, ready))
    monkeypatch.setattr(setup, "plan", lambda *args: next(stages))
    installed = []

    def install(command, **kwargs):
        installed.append(command)
        (source_project / "package.json").write_text(command, encoding="utf-8")
        return True

    monkeypatch.setattr(init_command, "_succeeded", install)
    assert setup.configure(source_project, ["app.py"]) == 0
    assert installed == ["install-plugin", "install-tool"]


@pytest.mark.parametrize("success", [False, True])
def test_failed_or_ineffective_install_stops_the_scan(source_project, monkeypatch, success):
    missing = evolve(plan(source_project, ["app.py"]), missing_tools=(Detector("missing", "command", "install-missing"),))
    monkeypatch.setattr(setup, "plan", lambda *args: missing)
    monkeypatch.setattr(init_command, "_succeeded", lambda *args, **kwargs: success)
    monkeypatch.setattr(hooks, "_pipeline", lambda args: pytest.fail("must not scan"))

    assert hooks.main(["--file", "app.py"]) == 1
    assert not (source_project / ".habit-hooks/config.toml").exists()


def test_setup_reports_modified_project_files(source_project, monkeypatch, capsys):
    ready = plan(source_project, ["app.py"])
    missing = evolve(ready, missing_tools=(Detector("missing", "command", "install-missing"),))
    stages = iter((missing, ready))
    monkeypatch.setattr(setup, "plan", lambda *args: next(stages))

    def install(*args, **kwargs):
        (source_project / "app.py").write_text("print('updated')\n", encoding="utf-8")
        return True

    monkeypatch.setattr(init_command, "_succeeded", install)
    assert setup.configure(source_project, ["app.py"]) == 0
    assert "Modified: app.py" in capsys.readouterr().err
