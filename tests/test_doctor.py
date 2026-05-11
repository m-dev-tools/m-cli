"""Tests for m doctor — environment diagnostics.

`m doctor` reports the health of the M development environment:
- `$ydb_dist` set and points at a real directory with a `ydb` binary
- `$ydb_routines` set
- tree-sitter-m parser available (can parse a trivial routine)
- m-standard keyword TSV files load
- `ydb` binary resolvable

Each check returns a `Check` record with status `ok` / `warn` / `fail`,
a one-line message, and an optional hint. The command exits 1 if any
check is `fail`, 0 otherwise (`warn` does not fail the run).
"""

from __future__ import annotations

import argparse
import json

import pytest

from m_cli.doctor import doctor_command
from m_cli.doctor.checks import (
    Check,
    Fix,
    Status,
    check_docker_daemon,
    check_docker_installed,
    check_engine_bind_mount,
    check_engine_container,
    check_engine_image,
    check_keywords,
    check_parser,
    check_ydb_binary,
    check_ydb_dist,
    check_ydb_routines,
    run_all_checks,
)

# ---------------------------------------------------------------- Check shape


def test_check_dataclass_carries_status_and_message():
    c = Check(name="ydb_dist", status=Status.OK, message="set", hint=None)
    assert c.name == "ydb_dist"
    assert c.status is Status.OK
    assert c.message == "set"
    assert c.hint is None


def test_status_enum_has_four_levels():
    # SKIPPED is added in Phase 1b for prerequisite-failed downstream
    # checks (root-cause grouping in m doctor).
    assert {Status.OK, Status.WARN, Status.FAIL, Status.SKIPPED} == set(Status)


def test_fix_dataclass_carries_command_and_destructive_flag():
    f = Fix(command=("docker", "pull", "x"), destructive=False)
    assert f.command == ("docker", "pull", "x")
    assert f.destructive is False
    # Destructive defaults to False
    f2 = Fix(command=("docker", "stop", "y"))
    assert f2.destructive is False


def test_check_accepts_optional_prerequisites_and_fix():
    c = Check(
        name="x",
        status=Status.WARN,
        message="m",
        prerequisites=("y",),
        fix=Fix(command=("a", "b")),
    )
    assert c.prerequisites == ("y",)
    assert c.fix is not None
    assert c.fix.command == ("a", "b")
    # Existing call sites without these fields still work
    c2 = Check(name="x", status=Status.OK, message="m")
    assert c2.prerequisites == ()
    assert c2.fix is None


# ------------------------------------------------------------- Per-check tests


def test_check_ydb_dist_unset_is_warn(monkeypatch):
    monkeypatch.delenv("ydb_dist", raising=False)
    c = check_ydb_dist()
    assert c.name == "ydb_dist"
    assert c.status is Status.WARN
    assert c.hint is not None  # actionable


def test_check_ydb_dist_points_at_missing_dir_is_fail(monkeypatch, tmp_path):
    bogus = tmp_path / "does-not-exist"
    monkeypatch.setenv("ydb_dist", str(bogus))
    c = check_ydb_dist()
    assert c.status is Status.FAIL
    assert "does-not-exist" in c.message or "missing" in c.message.lower()


def test_check_ydb_dist_dir_without_ydb_binary_is_warn(monkeypatch, tmp_path):
    monkeypatch.setenv("ydb_dist", str(tmp_path))
    c = check_ydb_dist()
    # Directory exists but no `ydb` binary inside — warn, not fail
    assert c.status is Status.WARN
    assert c.hint is not None


def test_check_ydb_dist_with_binary_is_ok(monkeypatch, tmp_path):
    binary = tmp_path / "ydb"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    monkeypatch.setenv("ydb_dist", str(tmp_path))
    c = check_ydb_dist()
    assert c.status is Status.OK


def test_check_ydb_routines_unset_is_warn(monkeypatch):
    monkeypatch.delenv("ydb_routines", raising=False)
    c = check_ydb_routines()
    assert c.status is Status.WARN
    assert c.hint is not None


def test_check_ydb_routines_set_is_ok(monkeypatch):
    monkeypatch.setenv("ydb_routines", ".")
    c = check_ydb_routines()
    assert c.status is Status.OK


def test_check_parser_returns_ok_when_parser_works():
    # The parser ships in this repo — should always work.
    c = check_parser()
    assert c.status is Status.OK


def test_check_keywords_returns_ok_when_tsvs_load():
    c = check_keywords()
    assert c.status is Status.OK
    # Message includes some count
    assert any(ch.isdigit() for ch in c.message)


def test_check_ydb_binary_missing_is_warn(monkeypatch, tmp_path):
    # Empty PATH, no ydb_dist
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("ydb_dist", raising=False)
    monkeypatch.delenv("YDB", raising=False)
    c = check_ydb_binary()
    assert c.status is Status.WARN


def test_check_ydb_binary_via_explicit_YDB(monkeypatch, tmp_path):
    binary = tmp_path / "myydb"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    monkeypatch.setenv("YDB", str(binary))
    c = check_ydb_binary()
    assert c.status is Status.OK
    assert "myydb" in c.message


# ----------------------------------------------------------- run_all_checks()


def test_run_all_checks_returns_list_of_checks():
    checks = run_all_checks()
    assert isinstance(checks, list)
    assert all(isinstance(c, Check) for c in checks)
    # At least the five named checks
    names = {c.name for c in checks}
    assert {
        "ydb_dist",
        "ydb_routines",
        "parser",
        "keywords",
        "ydb_binary",
    }.issubset(names)


# ------------------------------------------------------------- CLI / exit code


def _ns(format: str = "text", **kw) -> argparse.Namespace:
    ns = argparse.Namespace(format=format)
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def test_doctor_cli_exits_zero_when_all_ok(monkeypatch, tmp_path, capsys):
    # Force every check to OK by setting a clean env.
    binary = tmp_path / "ydb"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    monkeypatch.setenv("ydb_dist", str(tmp_path))
    monkeypatch.setenv("ydb_routines", ".")
    monkeypatch.setenv("PATH", str(tmp_path))
    rc = doctor_command(_ns())
    out = capsys.readouterr().out
    assert rc == 0
    assert "ydb_dist" in out
    assert "OK" in out  # human format shows status


def test_doctor_cli_exits_one_when_any_fail(monkeypatch, tmp_path, capsys):
    bogus = tmp_path / "no-such-dir"
    monkeypatch.setenv("ydb_dist", str(bogus))
    rc = doctor_command(_ns())
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out


def test_doctor_cli_warn_does_not_fail_run(monkeypatch, capsys):
    # Unset ydb_dist → WARN, but no FAIL anywhere.
    monkeypatch.delenv("ydb_dist", raising=False)
    monkeypatch.delenv("ydb_routines", raising=False)
    monkeypatch.delenv("YDB", raising=False)
    rc = doctor_command(_ns())
    assert rc == 0  # warns only


def test_doctor_cli_json_format(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ydb_dist", str(tmp_path))
    monkeypatch.setenv("ydb_routines", ".")
    rc = doctor_command(_ns(format="json"))
    out = capsys.readouterr().out

    payload = json.loads(out)
    assert isinstance(payload, list)
    assert all("name" in c and "status" in c for c in payload)
    assert rc in (0, 1)


# ─────────────────────────────────────────────────────────────────
# Phase 1b — Docker engine checks driven by the vendored manifest
# ─────────────────────────────────────────────────────────────────


@pytest.fixture
def docker_world(monkeypatch):
    """Inject all five Docker-runtime probes with controllable defaults.

    Tests adjust individual probes via ``world.set(...)`` to model the
    cell of the truth table they're exercising. No actual docker /
    filesystem calls fire.
    """
    from m_cli.doctor import _runtime

    state = {
        "docker_available": True,
        "docker_daemon_reachable": True,
        "docker_image_present": True,
        "docker_container_running": True,
        "path_exists": True,
    }

    def _set(**kw):
        state.update(kw)

    monkeypatch.setattr(_runtime, "docker_available", lambda: state["docker_available"])
    monkeypatch.setattr(
        _runtime,
        "docker_daemon_reachable",
        lambda: state["docker_daemon_reachable"],
    )
    monkeypatch.setattr(
        _runtime,
        "docker_image_present",
        lambda ref: state["docker_image_present"],
    )
    monkeypatch.setattr(
        _runtime,
        "docker_container_running",
        lambda name: state["docker_container_running"],
    )
    monkeypatch.setattr(_runtime, "path_exists", lambda p: state["path_exists"])

    class _World:
        set = staticmethod(_set)

    return _World()


def test_check_docker_installed_ok_when_present(docker_world):
    docker_world.set(docker_available=True)
    c = check_docker_installed()
    assert c.status is Status.OK


def test_check_docker_installed_warn_with_hint_when_missing(docker_world):
    docker_world.set(docker_available=False)
    c = check_docker_installed()
    assert c.status is Status.WARN
    assert c.hint is not None  # must be actionable


def test_check_docker_daemon_ok_when_reachable(docker_world):
    c = check_docker_daemon()
    assert c.status is Status.OK


def test_check_docker_daemon_warn_with_fix_when_unreachable(docker_world):
    docker_world.set(docker_daemon_reachable=False)
    c = check_docker_daemon()
    assert c.status is Status.WARN
    assert c.fix is not None
    cmd = " ".join(c.fix.command)
    # Linux daemon start: systemctl. Mac: starts Docker Desktop. Either
    # way the fix command is non-destructive.
    assert "docker" in cmd or "systemctl" in cmd
    assert c.fix.destructive is False


def test_check_engine_image_ok_when_present(docker_world):
    c = check_engine_image()
    assert c.status is Status.OK


def test_check_engine_image_warn_with_pull_fix_when_missing(docker_world):
    from m_cli.engine_manifest import load_engine_manifest

    docker_world.set(docker_image_present=False)
    c = check_engine_image()
    assert c.status is Status.WARN
    assert c.fix is not None
    # Pull command derived from the manifest
    assert c.fix.command[:2] == ("docker", "pull")
    m = load_engine_manifest()
    assert m.image_ref() in c.fix.command
    assert c.fix.destructive is False


def test_check_engine_container_ok_when_running(docker_world):
    c = check_engine_container()
    assert c.status is Status.OK


def test_check_engine_container_warn_with_start_fix_when_stopped(docker_world):
    docker_world.set(docker_container_running=False)
    c = check_engine_container()
    assert c.status is Status.WARN
    assert c.fix is not None
    # Compose-first per the implementation plan §1.3
    cmd = " ".join(c.fix.command)
    assert "compose" in cmd or "docker" in cmd
    assert c.fix.destructive is False


def test_check_engine_bind_mount_ok_when_path_exists(docker_world):
    c = check_engine_bind_mount()
    assert c.status is Status.OK


def test_check_engine_bind_mount_warn_when_missing(docker_world):
    from m_cli.engine_manifest import load_engine_manifest

    docker_world.set(path_exists=False)
    c = check_engine_bind_mount()
    assert c.status is Status.WARN
    m = load_engine_manifest()
    # Message references the host bind-mount path declared in the manifest
    assert m.bind_mount.host in (c.message or "") or m.bind_mount.host in (c.hint or "")


# ─────────────────────────────────────────────────────────────────
# Phase 1b.4 — Root-cause grouping: SKIPPED downstream
# ─────────────────────────────────────────────────────────────────


def test_run_all_checks_marks_docker_downstream_skipped_when_docker_missing(
    docker_world,
):
    docker_world.set(docker_available=False)
    checks = run_all_checks()
    by_name = {c.name: c for c in checks}

    # Top of the chain — WARN with hint
    assert by_name["docker_installed"].status is Status.WARN

    # Everything that prerequisites docker_installed is SKIPPED, not WARN
    for downstream in ("docker_daemon", "engine_image", "engine_container"):
        c = by_name[downstream]
        assert c.status is Status.SKIPPED, (
            f"{downstream} should be SKIPPED when docker_installed fails, got {c.status}"
        )
        # Skipped reason references the failing prereq
        assert "docker_installed" in (c.message or "")


def test_run_all_checks_marks_engine_chain_skipped_when_daemon_down(docker_world):
    docker_world.set(docker_daemon_reachable=False)
    checks = run_all_checks()
    by_name = {c.name: c for c in checks}

    assert by_name["docker_installed"].status is Status.OK
    assert by_name["docker_daemon"].status is Status.WARN
    # engine_image and engine_container both depend on daemon being up
    for downstream in ("engine_image", "engine_container"):
        assert by_name[downstream].status is Status.SKIPPED


# ─────────────────────────────────────────────────────────────────
# Phase 1b.3 — JSON schema extension: fix.command + fix.destructive
# ─────────────────────────────────────────────────────────────────


def test_doctor_json_emits_fix_block_when_check_provides_one(docker_world, capsys):
    docker_world.set(docker_image_present=False)
    doctor_command(_ns(format="json"))
    out = capsys.readouterr().out

    payload = json.loads(out)
    by_name = {c["name"]: c for c in payload}
    assert "engine_image" in by_name
    fx = by_name["engine_image"].get("fix")
    assert fx is not None
    assert isinstance(fx["command"], list)
    assert fx["command"][:2] == ["docker", "pull"]
    assert fx["destructive"] is False


def test_doctor_json_omits_fix_when_check_does_not_provide_one(docker_world, capsys):
    doctor_command(_ns(format="json"))
    out = capsys.readouterr().out
    payload = json.loads(out)
    ok_check = next(c for c in payload if c["status"] == "OK")
    # Healthy checks need no fix
    assert ok_check.get("fix") is None


def test_doctor_text_shows_fix_command_after_hint(docker_world, capsys):
    docker_world.set(docker_image_present=False)
    doctor_command(_ns(format="text"))
    out = capsys.readouterr().out
    # Fix line uses a "fix:" marker, copy-pasteable command
    assert "fix:" in out
    assert "docker pull" in out


def test_doctor_text_renders_skipped_with_prereq_reference(docker_world, capsys):
    docker_world.set(docker_available=False)
    doctor_command(_ns(format="text"))
    out = capsys.readouterr().out
    # SKIPPED checks visible in output
    assert "SKIP" in out
    # The prereq that caused the skip is named in the output
    assert "docker_installed" in out
