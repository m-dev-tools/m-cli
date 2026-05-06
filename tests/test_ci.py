"""Tests for `m ci init` — emit a GitHub Actions workflow."""

from __future__ import annotations

import argparse

from m_cli.ci import ci_command
from m_cli.ci.scaffold import render_workflow

# --------------------------------------------------------------- workflow body


def test_render_workflow_returns_yaml_with_expected_jobs():
    yml = render_workflow()
    # Top-level required keys
    assert "name:" in yml
    assert "on:" in yml
    assert "jobs:" in yml


def test_render_workflow_runs_each_gate_command():
    yml = render_workflow()
    # The four gate commands the §6.2 spec requires
    assert "m fmt --check" in yml
    assert "m lint --error-on=fatal" in yml
    assert "m test" in yml
    assert "m coverage --format=lcov" in yml


def test_render_workflow_uses_ydb_container_or_setup():
    yml = render_workflow()
    # Either a yottadb container image OR a setup step that installs ydb
    assert "yottadb" in yml.lower()


def test_render_workflow_triggers_on_push_and_pr():
    yml = render_workflow()
    assert "push:" in yml
    assert "pull_request:" in yml


def test_render_workflow_checks_out_with_actions_checkout():
    yml = render_workflow()
    assert "actions/checkout" in yml


# ---------------------------------------------------------- ci_command behaviour


def _ns(**kw) -> argparse.Namespace:
    base = {"path": None, "force": False, "quiet": True, "ci_action": "init"}
    base.update(kw)
    return argparse.Namespace(**base)


def test_ci_init_creates_workflow_file(tmp_path):
    rc = ci_command(_ns(path=tmp_path))
    assert rc == 0
    wf = tmp_path / ".github" / "workflows" / "m-ci.yml"
    assert wf.is_file()
    body = wf.read_text()
    assert "m fmt --check" in body


def test_ci_init_default_path_is_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = ci_command(_ns(path=None))
    assert rc == 0
    assert (tmp_path / ".github" / "workflows" / "m-ci.yml").is_file()


def test_ci_init_refuses_existing_file_without_force(tmp_path):
    wf = tmp_path / ".github" / "workflows" / "m-ci.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text("# existing content")
    rc = ci_command(_ns(path=tmp_path))
    assert rc != 0
    # Untouched
    assert wf.read_text() == "# existing content"


def test_ci_init_force_overwrites(tmp_path):
    wf = tmp_path / ".github" / "workflows" / "m-ci.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text("# existing content")
    rc = ci_command(_ns(path=tmp_path, force=True))
    assert rc == 0
    body = wf.read_text()
    assert "m fmt --check" in body
    assert "# existing content" not in body


def test_ci_init_creates_nested_directories(tmp_path):
    rc = ci_command(_ns(path=tmp_path / "deep" / "project"))
    assert rc == 0
    assert (tmp_path / "deep" / "project" / ".github" / "workflows" / "m-ci.yml").is_file()
