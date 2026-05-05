"""Tests for ``m_cli.engine`` — connection contract, project root, command builders."""

from __future__ import annotations

from pathlib import Path

import pytest

from m_cli.engine import (
    Connection,
    EngineNotConfigured,
    build_direct_ssh_cmd,
    build_suite_ssh_cmd,
    build_xcmd_ssh_cmd,
    project_root,
    read_connection,
    remote_stage,
)

FAKE_CONN = Connection(host="vm-host", ssh_port=2222, ssh_user="vehu")


# ── read_connection ────────────────────────────────────────────────


def test_read_connection_parses_kv_pairs(tmp_path: Path) -> None:
    f = tmp_path / "conn.env"
    f.write_text(
        "# header comment\n"
        "VISTA_HOST=10.0.0.5\n"
        "VISTA_SSH_PORT=2222\n"
        "VISTA_SSH_USER=vehu\n"
        "VISTA_HTTP_RPC_PORT=9430\n"
    )
    conn = read_connection(f)
    assert conn.host == "10.0.0.5"
    assert conn.ssh_port == 2222
    assert conn.ssh_user == "vehu"
    assert conn.target == "vehu@10.0.0.5"


def test_read_connection_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(EngineNotConfigured):
        read_connection(tmp_path / "nope.env")


def test_read_connection_missing_key_raises(tmp_path: Path) -> None:
    f = tmp_path / "conn.env"
    f.write_text("VISTA_HOST=x\n")  # missing SSH_PORT and SSH_USER
    with pytest.raises(EngineNotConfigured):
        read_connection(f)


def test_read_connection_honors_env_var_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom = tmp_path / "alt.env"
    custom.write_text("VISTA_HOST=h\nVISTA_SSH_PORT=22\nVISTA_SSH_USER=u\n")
    monkeypatch.setenv("VISTA_CONN_FILE", str(custom))
    conn = read_connection()
    assert conn.host == "h"


# ── project_root + remote_stage ────────────────────────────────────


def test_project_root_finds_pyproject_toml(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "src").mkdir()
    leaf = tmp_path / "src" / "deep" / "FILE.m"
    leaf.parent.mkdir(parents=True)
    leaf.write_text("X\n")
    assert project_root(leaf) == tmp_path.resolve()


def test_project_root_finds_makefile(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text("")
    leaf = tmp_path / "routines" / "X.m"
    leaf.parent.mkdir()
    leaf.write_text("")
    assert project_root(leaf) == tmp_path.resolve()


def test_remote_stage_uses_project_dir_name(tmp_path: Path) -> None:
    proj = tmp_path / "my-proj"
    proj.mkdir()
    (proj / "Makefile").write_text("")
    leaf = proj / "X.m"
    leaf.write_text("")
    assert remote_stage(leaf) == "$HOME/export/seed/my-proj"


# ── command builders ──────────────────────────────────────────────


def test_build_suite_ssh_cmd_carries_routine_entry() -> None:
    cmd = build_suite_ssh_cmd(FAKE_CONN, "HELLOTST", "$HOME/export/seed/m-tools")
    assert cmd[0] == "ssh"
    assert "vehu@vm-host" in cmd
    # The remote-side script is the last element of argv.
    remote = cmd[-1]
    assert "^HELLOTST" in remote
    assert "ydb_routines=" in remote
    assert "$HOME/export/seed/m-tools" in remote


def test_build_xcmd_ssh_cmd_quotes_m_command() -> None:
    m_cmd = "do start^TESTRUN(.p,.f) do tFoo^X(.p,.f) do report^TESTRUN(p,f)"
    cmd = build_xcmd_ssh_cmd(FAKE_CONN, m_cmd, "$HOME/export/seed/m-stdlib")
    assert cmd[0] == "ssh"
    remote = cmd[-1]
    assert "%XCMD" in remote
    assert "tFoo^X" in remote


def test_build_direct_ssh_cmd_targets_mumps_direct() -> None:
    cmd = build_direct_ssh_cmd(FAKE_CONN, "$HOME/export/seed/m-cli")
    assert cmd[0] == "ssh"
    remote = cmd[-1]
    assert "mumps -direct" in remote
    assert "$HOME/export/seed/m-cli" in remote


def test_build_suite_ssh_cmd_uses_port_from_connection() -> None:
    conn = Connection(host="h", ssh_port=9999, ssh_user="u")
    cmd = build_suite_ssh_cmd(conn, "X", "/tmp")
    # ssh -p PORT comes early in argv
    assert "9999" in cmd[1:3]
