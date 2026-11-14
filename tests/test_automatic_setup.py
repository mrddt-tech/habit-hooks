from __future__ import annotations

import pytest
from attrs import evolve

from habit_hooks import hooks, init_command, setup
from habit_hooks.detectors import Detector
from habit_hooks.initialise import plan


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


@pytest.mark.parametrize("success", [False, True])
def test_failed_or_ineffective_install_stops_the_scan(source_project, monkeypatch, success):
    missing = evolve(plan(source_project, ["app.py"]), missing_tools=(Detector("missing", "command", "install-missing"),))
    monkeypatch.setattr(setup, "plan", lambda *args: missing)
    monkeypatch.setattr(init_command, "_succeeded", lambda *args, **kwargs: success)
    monkeypatch.setattr(hooks, "_pipeline", lambda args: pytest.fail("must not scan"))

    assert hooks.main(["--file", "app.py"]) == 1
    assert not (source_project / ".habit-hooks/config.toml").exists()
