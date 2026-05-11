"""Tests for the ``m engine`` subcommand surface.

The CLI module is a thin argparse + dispatch layer over
:class:`~m_cli.engine_driver.EngineDriver`. Tests inject a fake driver
via ``set_driver_factory`` so no docker calls fire.

Phase 2 of the m-engine plan
(see m-test-engine/docs/m-engine-implementation-plan.md §2.1).
"""

from __future__ import annotations

import argparse
import json

import pytest

from m_cli.engine_cli import set_driver_factory
from m_cli.engine_driver import EngineStatus


class FakeDriver:
    """Records every verb invocation. Verbs return a configurable rc."""

    name = "docker"

    def __init__(self, *, status_payload: EngineStatus | None = None, rc: int = 0):
        self.calls: list[tuple[str, tuple, dict]] = []
        self.rc = rc
        self._status = status_payload or EngineStatus(
            driver="docker",
            installed=True,
            daemon_reachable=True,
            image_present=True,
            container_running=True,
            container_healthy=None,
            image_ref="ghcr.io/example:v1",
            container="m-test-engine",
        )

    def _record(self, name, *args, **kw):
        self.calls.append((name, args, kw))
        return self.rc

    def status(self):
        self.calls.append(("status", (), {}))
        return self._status

    def install(self):
        return self._record("install")

    def start(self):
        return self._record("start")

    def stop(self):
        return self._record("stop")

    def restart(self):
        return self._record("restart")

    def logs(self, follow=False):
        return self._record("logs", follow=follow)

    def shell(self):
        return self._record("shell")

    def exec(self, m_cmd):
        return self._record("exec", m_cmd)

    def version(self, *, as_json=False):
        return self._record("version", as_json=as_json)

    def reset(self, *, confirm=False):
        return self._record("reset", confirm=confirm)


@pytest.fixture
def fake_driver():
    drv = FakeDriver()
    set_driver_factory(lambda: drv)
    try:
        yield drv
    finally:
        # restore default factory
        from m_cli.engine_cli import _default_driver_factory

        set_driver_factory(_default_driver_factory)


def _ns(**kw) -> argparse.Namespace:
    return argparse.Namespace(**kw)


# ── status ───────────────────────────────────────────────────────────


def test_engine_status_text_output_shows_container_up(fake_driver, capsys):
    from m_cli.engine_cli import _cmd_status

    rc = _cmd_status(_ns(json=False))
    out = capsys.readouterr().out
    assert rc == 0  # container_running=True in default fake status
    assert "m-test-engine" in out
    assert "ghcr.io/example:v1" in out


def test_engine_status_returns_one_when_container_down(capsys):
    from m_cli.engine_cli import _cmd_status

    drv = FakeDriver(
        status_payload=EngineStatus(
            driver="docker",
            installed=True,
            daemon_reachable=True,
            image_present=True,
            container_running=False,
            container_healthy=None,
            image_ref="x:y",
            container="m-test-engine",
        )
    )
    set_driver_factory(lambda: drv)
    try:
        rc = _cmd_status(_ns(json=False))
        assert rc == 1
    finally:
        from m_cli.engine_cli import _default_driver_factory

        set_driver_factory(_default_driver_factory)


def test_engine_status_json_output(fake_driver, capsys):
    from m_cli.engine_cli import _cmd_status

    rc = _cmd_status(_ns(json=True))
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["driver"] == "docker"
    assert payload["container"] == "m-test-engine"
    assert payload["container_running"] is True
    assert rc == 0


# ── install / start / stop / restart ─────────────────────────────────


def test_engine_install_invokes_driver_install(fake_driver):
    from m_cli.engine_cli import _cmd_install

    rc = _cmd_install(_ns())
    assert rc == 0
    assert any(c[0] == "install" for c in fake_driver.calls)


def test_engine_start_invokes_driver_start(fake_driver):
    from m_cli.engine_cli import _cmd_start

    _cmd_start(_ns())
    assert any(c[0] == "start" for c in fake_driver.calls)


def test_engine_stop_invokes_driver_stop(fake_driver):
    from m_cli.engine_cli import _cmd_stop

    _cmd_stop(_ns())
    assert any(c[0] == "stop" for c in fake_driver.calls)


def test_engine_restart_invokes_driver_restart(fake_driver):
    from m_cli.engine_cli import _cmd_restart

    _cmd_restart(_ns())
    assert any(c[0] == "restart" for c in fake_driver.calls)


# ── logs / shell / exec / version ────────────────────────────────────


def test_engine_logs_forwards_follow_flag(fake_driver):
    from m_cli.engine_cli import _cmd_logs

    _cmd_logs(_ns(follow=True))
    call = next(c for c in fake_driver.calls if c[0] == "logs")
    assert call[2]["follow"] is True


def test_engine_shell_invokes_driver_shell(fake_driver):
    from m_cli.engine_cli import _cmd_shell

    _cmd_shell(_ns())
    assert any(c[0] == "shell" for c in fake_driver.calls)


def test_engine_exec_passes_m_command(fake_driver):
    from m_cli.engine_cli import _cmd_exec

    _cmd_exec(_ns(m_cmd="write 1+2,!"))
    call = next(c for c in fake_driver.calls if c[0] == "exec")
    assert call[1] == ("write 1+2,!",)


def test_engine_version_invokes_driver_version(fake_driver):
    from m_cli.engine_cli import _cmd_version

    _cmd_version(_ns(json=False))
    call = next(c for c in fake_driver.calls if c[0] == "version")
    assert call[2]["as_json"] is False


def test_engine_version_passes_json_flag(fake_driver):
    from m_cli.engine_cli import _cmd_version

    _cmd_version(_ns(json=True))
    call = next(c for c in fake_driver.calls if c[0] == "version")
    assert call[2]["as_json"] is True


# ── reset (destructive) ──────────────────────────────────────────────


def test_engine_reset_forwards_confirm_flag(fake_driver):
    from m_cli.engine_cli import _cmd_reset

    _cmd_reset(_ns(confirm=True))
    call = next(c for c in fake_driver.calls if c[0] == "reset")
    assert call[2]["confirm"] is True


def test_engine_reset_without_confirm_still_forwards_false(fake_driver):
    from m_cli.engine_cli import _cmd_reset

    _cmd_reset(_ns(confirm=False))
    call = next(c for c in fake_driver.calls if c[0] == "reset")
    assert call[2]["confirm"] is False


# ── capabilities ─────────────────────────────────────────────────────


def test_engine_capabilities_emits_manifest_summary(capsys):
    from m_cli.engine_cli import _cmd_capabilities

    rc = _cmd_capabilities(_ns())
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 0
    assert payload["namespace"] == "engine"
    assert payload["driver"] == "docker"
    assert "manifest" in payload
    assert payload["manifest"]["protocol"] == 1
    verbs = {v["name"]: v for v in payload["verbs"]}
    assert verbs["status"]["read_only"] is True
    assert verbs["reset"]["destructive"] is True
    assert verbs["reset"].get("requires_confirm") is True
    # removed verbs must not reappear
    assert "upgrade" not in verbs
    assert "watch" not in verbs


# ── argparse wiring (top-level dispatch) ─────────────────────────────


def test_main_dispatches_engine_status_via_argparse(monkeypatch, capsys):
    from m_cli.cli import main

    drv = FakeDriver()
    set_driver_factory(lambda: drv)
    try:
        rc = main(["engine", "status", "--json"])
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert rc == 0
        assert payload["container_running"] is True
    finally:
        from m_cli.engine_cli import _default_driver_factory

        set_driver_factory(_default_driver_factory)


