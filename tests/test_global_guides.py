from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from habit_hooks import mapper
from habit_hooks.project_paths import venv_executable
from habit_hooks.rendering import include_environment
from habit_hooks.resolve import CORE_GUIDES, Resolver, global_config_dir
from plugin_fixture import write_project_config


@pytest.fixture
def guide_resolver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Resolver:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "settings"))
    return Resolver(tmp_path / "project", {"first": tmp_path / "package-first", "second": tmp_path / "package-second"})


def _write(path: Path, text: str = "custom message") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("setting", [None, "", "relative/settings"])
def test_missing_empty_or_relative_xdg_uses_home(tmp_path, monkeypatch, setting):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if setting is None:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    else:
        monkeypatch.setenv("XDG_CONFIG_HOME", setting)

    assert global_config_dir() == tmp_path / ".config/habit-hooks"


def test_absolute_xdg_directory_is_used(guide_resolver):
    assert global_config_dir() == guide_resolver.project_dir.parent / "settings/habit-hooks"


def test_project_guides_outrank_global_and_packaged_guides(guide_resolver):
    _write(guide_resolver.package_dirs["first"] / "guides/example.md")
    _write(global_config_dir() / "first/guides/example.md")
    local = _write(guide_resolver.project_dir / ".habit-hooks/second/guides/example.md")

    assert guide_resolver.guide("example.md", ["first", "second"]) == local


def test_global_guides_outrank_packaged_guides(guide_resolver):
    _write(guide_resolver.package_dirs["first"] / "guides/example.md")
    override = _write(global_config_dir() / "second/guides/example.md")

    assert guide_resolver.guide("example.md", ["first", "second"]) == override


def test_global_plugin_order_matches_configured_order(guide_resolver):
    first = _write(global_config_dir() / "first/guides/example.md")
    second = _write(global_config_dir() / "second/guides/example.md")

    assert guide_resolver.guide("example.md", ["first", "second"]) == first
    assert guide_resolver.guide("example.md", ["second", "first"]) == second


def test_global_plugin_guides_outrank_global_core_guides(guide_resolver):
    _write(global_config_dir() / "guides/example.md")
    override = _write(global_config_dir() / "first/guides/example.md")

    assert guide_resolver.guide("example.md", ["first"]) == override


def test_global_core_guides_outrank_packaged_guides(guide_resolver):
    _write(guide_resolver.package_dirs["first"] / "guides/clean.md")
    override = _write(global_config_dir() / "guides/clean.md")

    assert guide_resolver.guide("clean.md", ["first"]) == override


def test_unconfigured_plugins_are_not_searched(guide_resolver):
    _write(global_config_dir() / "second/guides/example.md")

    assert guide_resolver.guide("example.md", ["first"]) is None


def test_packaged_guides_remain_the_fallback(guide_resolver):
    packaged = _write(guide_resolver.package_dirs["first"] / "guides/example.md")

    assert guide_resolver.guide("example.md", ["first"]) == packaged
    assert guide_resolver.guide("clean.md", []) == CORE_GUIDES / "clean.md"


def test_global_guides_are_read_again_after_edits(guide_resolver):
    guide = _write(global_config_dir() / "guides/example.md", "before")
    environment = include_environment([], guide_resolver)
    assert environment.get_template("example.md").render() == "before"

    guide.write_text("after", encoding="utf-8")

    assert include_environment([], guide_resolver).get_template("example.md").render() == "after"
    assert not guide_resolver.project_dir.exists()


def test_template_includes_use_global_guides(guide_resolver):
    _write(global_config_dir() / "first/guides/partial.md", "global partial")

    template = include_environment(["first"], guide_resolver).from_string('{% include "partial.md" %}')

    assert template.render() == "global partial"


def test_global_config_and_sensors_are_not_loaded(guide_resolver):
    _write(global_config_dir() / "first/config.toml", 'language = "unexpected"')
    _write(global_config_dir() / "first/sensors/example.toml", 'command = "unexpected"')

    assert not guide_resolver.has_plugin("first")
    assert guide_resolver.part(["first"], "sensors/example.toml") is None


def test_mapper_renders_global_clean_message(guide_resolver, capsys):
    _write(global_config_dir() / "guides/clean.md", "My global clean message")
    write_project_config(guide_resolver.project_dir, 'plugins = []')

    assert mapper.run([], guide_resolver.project_dir) == 0
    assert "My global clean message" in capsys.readouterr().out


def test_installed_mapper_uses_global_messages(guide_resolver, installed_habit_sensors):
    _write(global_config_dir() / "guides/clean.md", "Installed global message")
    write_project_config(guide_resolver.project_dir, 'plugins = []')
    command = venv_executable(installed_habit_sensors.parent.parent, "habit-mapper")

    result = subprocess.run([str(command)], input="[]", cwd=guide_resolver.project_dir, capture_output=True, encoding="utf-8", errors="replace")

    assert result.returncode == 0, result.stderr
    assert "Installed global message" in result.stdout
