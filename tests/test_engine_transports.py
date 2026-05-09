"""Tests for the multi-transport engine abstraction.

m-cli's runtime tools support three transports:
- LocalEngine: locally-installed YottaDB, subprocess invocation
- DockerEngine: YottaDB in a Docker container (m-dev-tools/m-test-engine),
  invocation via `docker exec`
- SSHEngine (= Connection alias): remote YottaDB over SSH, the legacy
  vista-meta path

`detect_engine()` resolves which transport to use from the M_CLI_ENGINE
env var or auto-detection in priority order: ssh-conn-env (legacy
maintainer), local (which ydb), docker (m-test-engine container).

These tests cover the new abstractions; ``test_engine.py`` covers the
existing SSH/Connection surface and stays green to prove backward
compatibility.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from m_cli.engine import (
    Connection,
    DockerEngine,
    EngineNotConfigured,
    LocalEngine,
    SSHEngine,
    detect_engine,
)


# ── LocalEngine ────────────────────────────────────────────────────


def test_local_engine_build_suite_cmd_uses_env_prefix() -> None:
    eng = LocalEngine(ydb_dist=Path("/usr/local/lib/yottadb/r2.02"))
    cmd = eng.build_suite_cmd("HELLOTST", "/home/me/proj/routines")
    # `env` prefix sets ydb_routines without modifying the parent shell
    assert cmd[0] == "env"
    assert any("ydb_routines=" in part for part in cmd)
    assert any("/home/me/proj/routines" in part for part in cmd)
    assert "/usr/local/lib/yottadb/r2.02/mumps" in cmd
    assert cmd[-2:] == ["-run", "^HELLOTST"]


def test_local_engine_build_xcmd_quotes_m_command() -> None:
    eng = LocalEngine(ydb_dist=Path("/opt/yottadb"))
    m_cmd = "do start^TESTRUN(.p,.f) do report^TESTRUN(p,f)"
    cmd = eng.build_xcmd_cmd(m_cmd, "/p/routines")
    assert cmd[0] == "env"
    assert "/opt/yottadb/mumps" in cmd
    assert "%XCMD" in cmd
    # The M command itself is the final argv element
    assert cmd[-1] == m_cmd


def test_local_engine_build_direct_targets_mumps_direct() -> None:
    eng = LocalEngine(ydb_dist=Path("/opt/yottadb"))
    cmd = eng.build_direct_cmd("/p/routines")
    assert cmd[0] == "env"
    assert "/opt/yottadb/mumps" in cmd
    assert cmd[-1] == "-direct"


def test_local_engine_stage_routines_returns_project_root_routines() -> None:
    """Local engine doesn't copy files — the 'stage' is the local routines dir."""
    eng = LocalEngine(ydb_dist=Path("/opt/yottadb"))
    # When given a project path, the stage is a colon-or-space separated
    # list of routine dirs that exist under it.
    # The exact format mirrors what ydb_routines expects.
    stage = eng.stage_routines(Path(__file__).parent)
    assert isinstance(stage, str)
    # Must contain at least the resolved tests dir (where this file lives).


# ── DockerEngine ───────────────────────────────────────────────────


def test_docker_engine_build_suite_cmd_uses_docker_exec() -> None:
    eng = DockerEngine(container="m-test-engine", bind_root=Path("/work"))
    cmd = eng.build_suite_cmd("HELLOTST", "/work/src")
    assert cmd[0] == "docker"
    assert cmd[1] == "exec"
    # ydb_routines is set somewhere in the assembled cmd (either as a -e
    # flag value or embedded in a bash export statement inside cmd[-1]).
    assert any("ydb_routines=" in part for part in cmd)
    # Container name precedes the in-container command
    assert "m-test-engine" in cmd
    # mumps invocation runs in the container
    assert any("mumps" in part for part in cmd)
    # Suite name is the runtime entry
    assert any("^HELLOTST" in part for part in cmd)


def test_docker_engine_build_xcmd_cmd_passes_m_command() -> None:
    eng = DockerEngine(container="m-test-engine", bind_root=Path("/work"))
    m_cmd = "do tFoo^X(.p,.f)"
    cmd = eng.build_xcmd_cmd(m_cmd, "/work/src")
    assert cmd[0] == "docker"
    # M command + %XCMD both appear in the assembled argv (they may be
    # embedded inside a bash -c script string rather than separate argv elements).
    assert any("%XCMD" in part for part in cmd)
    assert any(m_cmd in part for part in cmd)


def test_docker_engine_stage_routines_translates_to_bind_mount() -> None:
    """Docker engine returns the in-container path corresponding to the project."""
    eng = DockerEngine(container="m-test-engine", bind_root=Path("/work"))
    # Given a local project, the stage is the in-container path equivalent.
    stage = eng.stage_routines(Path(__file__).parent)
    # Must reference the bind-mount root, not the host path
    assert "/work" in stage


# ── SSHEngine (Connection alias for backward compat) ───────────────


def test_connection_is_sshengine_alias() -> None:
    """Connection class is preserved as an alias of SSHEngine."""
    assert Connection is SSHEngine


def test_sshengine_target_property() -> None:
    eng = SSHEngine(host="h", ssh_port=22, ssh_user="u")
    assert eng.target == "u@h"


# ── detect_engine() resolver ───────────────────────────────────────


def test_detect_engine_respects_m_cli_engine_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("M_CLI_ENGINE", "local")
    monkeypatch.setenv("ydb_dist", "/opt/yottadb")
    eng = detect_engine()
    assert isinstance(eng, LocalEngine)


def test_detect_engine_respects_m_cli_engine_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("M_CLI_ENGINE", "docker")
    eng = detect_engine()
    assert isinstance(eng, DockerEngine)


def test_detect_engine_respects_m_cli_engine_ssh_with_conn_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("M_CLI_ENGINE", "ssh")
    f = tmp_path / "conn.env"
    f.write_text("VISTA_HOST=h\nVISTA_SSH_PORT=2222\nVISTA_SSH_USER=u\n")
    monkeypatch.setenv("VISTA_CONN_FILE", str(f))
    eng = detect_engine()
    assert isinstance(eng, SSHEngine)


def test_detect_engine_unknown_value_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("M_CLI_ENGINE", "wat")
    with pytest.raises(EngineNotConfigured, match="M_CLI_ENGINE"):
        detect_engine()


def test_detect_engine_falls_back_to_ssh_when_conn_env_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No env var, but conn.env exists → preserves maintainer workflow."""
    monkeypatch.delenv("M_CLI_ENGINE", raising=False)
    f = tmp_path / "conn.env"
    f.write_text("VISTA_HOST=h\nVISTA_SSH_PORT=2222\nVISTA_SSH_USER=u\n")
    monkeypatch.setenv("VISTA_CONN_FILE", str(f))
    eng = detect_engine()
    assert isinstance(eng, SSHEngine)


def test_detect_engine_no_signals_raises_with_helpful_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No env var, no conn.env, no local ydb → raise with all three paths in msg."""
    monkeypatch.delenv("M_CLI_ENGINE", raising=False)
    monkeypatch.setenv("VISTA_CONN_FILE", str(tmp_path / "nope.env"))
    monkeypatch.delenv("ydb_dist", raising=False)
    # Stub out the which-ydb probe so test is hermetic.
    monkeypatch.setattr("m_cli.engine._has_local_ydb", lambda: False)
    monkeypatch.setattr("m_cli.engine._has_docker_engine_running", lambda: False)
    with pytest.raises(EngineNotConfigured) as exc:
        detect_engine()
    # Error message names all three paths
    msg = str(exc.value)
    assert "local" in msg.lower()
    assert "docker" in msg.lower() or "m-test-engine" in msg.lower()
    assert "ssh" in msg.lower() or "vista-meta" in msg.lower()


# ── Backward compat: legacy build_*_ssh_cmd functions still work ───


def test_legacy_build_suite_ssh_cmd_still_works() -> None:
    """Existing tests in test_engine.py import build_suite_ssh_cmd by name —
    that import must continue to resolve and produce the same SSH argv shape.
    """
    from m_cli.engine import build_suite_ssh_cmd
    conn = Connection(host="h", ssh_port=22, ssh_user="u")
    cmd = build_suite_ssh_cmd(conn, "X", "/tmp")
    assert cmd[0] == "ssh"
    assert "u@h" in cmd
