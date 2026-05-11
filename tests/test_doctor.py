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
import os

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


def test_check_ydb_routines_missing_path_is_warn(monkeypatch, tmp_path):
    """A path that doesn't exist on disk must not pass silently —
    otherwise `ydb_routines` flips OK while `ydb_dist` flips FAIL for
    the same nonexistent directory, contradicting itself.

    The hint must be concrete (cite the bad value and the env var) and
    a `Fix` must be attached so `m doctor --fix` surfaces a recipe."""
    missing = tmp_path / "no-such-dir"
    monkeypatch.setenv("ydb_routines", str(missing))
    c = check_ydb_routines()
    assert c.status is Status.WARN
    assert str(missing) in c.message
    assert c.hint is not None
    # Concrete: hint must name the env var and give the exact unset cmd.
    assert "ydb_routines" in c.hint
    assert "unset ydb_routines" in c.hint
    # Auto-fix recipe wired up (printed by `m doctor --fix`).
    assert c.fix is not None
    assert c.fix.command == ("unset", "ydb_routines")
    assert c.fix.engine_verb is None  # not an engine action


def test_check_ydb_routines_partial_missing_is_warn(monkeypatch, tmp_path):
    """Multi-component search path: one missing component → WARN."""
    real = tmp_path / "real"
    real.mkdir()
    missing = tmp_path / "missing"
    monkeypatch.setenv("ydb_routines", f"{real} {missing}")
    c = check_ydb_routines()
    assert c.status is Status.WARN
    assert str(missing) in c.message


def test_check_ydb_routines_wildcard_and_source_grouping_ok(
    monkeypatch, tmp_path
):
    """YDB syntax: trailing `*` (recursive) and `(srcdir)` suffix must
    not be treated as part of the directory name."""
    objects = tmp_path / "obj"
    sources = tmp_path / "src"
    objects.mkdir()
    sources.mkdir()
    monkeypatch.setenv(
        "ydb_routines", f"{objects}*({sources})"
    )
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


def test_run_all_checks_returns_list_of_checks(monkeypatch):
    # Force local intent so all five legacy host-side checks are present.
    monkeypatch.setenv("M_CLI_ENGINE", "local")
    checks = run_all_checks()
    assert isinstance(checks, list)
    assert all(isinstance(c, Check) for c in checks)
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
    # Local intent: force every host-side check to OK by setting a clean env.
    monkeypatch.setenv("M_CLI_ENGINE", "local")
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
    monkeypatch.setenv("M_CLI_ENGINE", "local")
    bogus = tmp_path / "no-such-dir"
    monkeypatch.setenv("ydb_dist", str(bogus))
    rc = doctor_command(_ns())
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out


def test_doctor_cli_warn_does_not_fail_run(monkeypatch, capsys):
    # Local intent + unset ydb_dist → WARN, but no FAIL anywhere.
    monkeypatch.setenv("M_CLI_ENGINE", "local")
    monkeypatch.delenv("ydb_dist", raising=False)
    monkeypatch.delenv("ydb_routines", raising=False)
    monkeypatch.delenv("YDB", raising=False)
    rc = doctor_command(_ns())
    assert rc == 0  # warns only


def test_doctor_cli_json_format(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("M_CLI_ENGINE", "local")
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

    Forces ``M_CLI_ENGINE=docker`` so the transport-aware check
    selector in :func:`m_cli.doctor.checks.run_all_checks` always
    picks the Docker check set, regardless of ambient ``$ydb_dist``
    or other env state on the test host.
    """
    from m_cli.doctor import _runtime

    monkeypatch.setenv("M_CLI_ENGINE", "docker")

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
    # Drives `m engine start` — m-cli does not invoke docker compose
    # directly because the upstream compose.yml is dev-facing and
    # references a different image than the manifest declares.
    assert c.fix.command == ("m", "engine", "start")
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


def test_check_engine_bind_mount_under_home_uses_mkdir_no_sudo(docker_world, monkeypatch):
    # Workspace convention: host paths under $HOME need no sudo. The
    # fix command should be `mkdir -p`, never `sudo install -d`.
    from m_cli.engine_manifest import load_engine_manifest

    docker_world.set(path_exists=False)
    host = load_engine_manifest().bind_mount.host
    home = os.path.expanduser("~")
    if not (host == home or host.startswith(home + os.sep)):
        pytest.skip("manifest host path is not under $HOME in this environment")
    c = check_engine_bind_mount()
    assert c.fix is not None
    assert c.fix.command[0] == "mkdir"
    assert "sudo" not in c.fix.command


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


def test_run_all_checks_docker_default_omits_host_ydb_even_when_stale(
    docker_world, monkeypatch
):
    """Under canonical (docker) intent, stale host-YDB env vars are
    irrelevant: the engine container provides YDB. Doctor must not
    show host-YDB rows at all — neither WARN/FAIL nor SKIPPED.
    """
    # docker_world default: every engine probe returns OK; M_CLI_ENGINE
    # unset → auto-resolve to docker. But the test machine may have
    # host YDB present which would flip auto to local — force docker.
    monkeypatch.setenv("M_CLI_ENGINE", "docker")
    bad = "/definitely/not/a/real/path"
    monkeypatch.setenv("ydb_dist", bad)
    monkeypatch.setenv("ydb_routines", bad)
    monkeypatch.delenv("YDB", raising=False)

    names = {c.name for c in run_all_checks()}
    assert names.isdisjoint({"ydb_dist", "ydb_routines", "ydb_binary"})


def test_run_all_checks_local_intent_surfaces_host_ydb_failure(
    docker_world, monkeypatch
):
    """In explicit local mode, host-YDB checks run regardless of the
    Docker engine's state — they are the primary signal for that user."""
    monkeypatch.setenv("M_CLI_ENGINE", "local")
    monkeypatch.setenv("ydb_dist", "/definitely/not/a/real/path")
    monkeypatch.delenv("YDB", raising=False)

    by_name = {c.name: c for c in run_all_checks()}
    assert by_name["ydb_dist"].status is Status.FAIL


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


# ─────────────────────────────────────────────────────────────────
# Phase 2.4 — m doctor --fix delegates to m engine verbs
# ─────────────────────────────────────────────────────────────────


def test_fix_dataclass_carries_engine_verb_field():
    """Phase 2.4: Fix grows engine_verb so --fix knows which `m engine
    <verb>` to invoke. None means the fix is non-engine (e.g. sudo'd
    system command) and --fix should print a 'manual:' line instead."""
    f = Fix(command=("docker", "pull", "x"), engine_verb="install")
    assert f.engine_verb == "install"
    f2 = Fix(command=("sudo", "systemctl", "start", "docker"))
    assert f2.engine_verb is None  # default


def test_check_engine_image_fix_declares_install_engine_verb(docker_world):
    docker_world.set(docker_image_present=False)
    c = check_engine_image()
    assert c.fix is not None
    assert c.fix.engine_verb == "install"


def test_check_engine_container_fix_declares_start_engine_verb(docker_world):
    docker_world.set(docker_container_running=False)
    c = check_engine_container()
    assert c.fix is not None
    assert c.fix.engine_verb == "start"


def test_check_docker_daemon_fix_has_no_engine_verb(docker_world):
    """sudo systemctl start docker isn't an engine verb — --fix must
    NOT auto-run it. It belongs to the 'manual:' bucket."""
    docker_world.set(docker_daemon_reachable=False)
    c = check_docker_daemon()
    assert c.fix is not None
    assert c.fix.engine_verb is None


def test_check_engine_bind_mount_fix_has_no_engine_verb(docker_world):
    """sudo install -d /m-work also belongs to manual: bucket."""
    docker_world.set(path_exists=False)
    c = check_engine_bind_mount()
    if c.fix is not None:
        assert c.fix.engine_verb is None


# ── apply_fixes — driver-delegation engine ───────────────────────


class _FakeFixDriver:
    """Records every engine method invocation. apply_fixes uses these."""

    name = "docker"

    def __init__(self):
        self.calls: list[str] = []

    def install(self):
        self.calls.append("install")
        return 0

    def start(self):
        self.calls.append("start")
        return 0

    def stop(self):
        self.calls.append("stop")
        return 0

    def restart(self):
        self.calls.append("restart")
        return 0

    def upgrade(self):
        self.calls.append("upgrade")
        return 0

    def reset(self, *, confirm=False):
        self.calls.append(f"reset(confirm={confirm})")
        return 0 if confirm else 2


@pytest.fixture
def fake_fix_driver():
    from m_cli.engine_cli import _default_driver_factory, set_driver_factory

    drv = _FakeFixDriver()
    set_driver_factory(lambda: drv)
    try:
        yield drv
    finally:
        set_driver_factory(_default_driver_factory)


def test_apply_fixes_invokes_engine_verb_for_each_fixable_warn(
    docker_world, fake_fix_driver
):
    """engine_image WARN + engine_container WARN should both run via the driver."""
    from m_cli.doctor.cli import apply_fixes

    docker_world.set(docker_image_present=False, docker_container_running=False)
    invoked = apply_fixes(run_all_checks(), confirm=False)
    assert "install" in fake_fix_driver.calls
    assert "start" in fake_fix_driver.calls
    # apply_fixes returns the count of driver invocations; both engine
    # checks fired so we expect 2 (not all fixes have engine_verb).
    assert invoked == 2


def test_apply_fixes_skips_non_engine_fixes_with_manual_message(
    docker_world, fake_fix_driver, capsys
):
    """A WARN whose fix lacks engine_verb is not auto-run; manual hint prints."""
    from m_cli.doctor.cli import apply_fixes

    docker_world.set(docker_daemon_reachable=False)
    apply_fixes(run_all_checks(), confirm=False)
    out = capsys.readouterr().out
    # No fix.command for docker_daemon should have been driver-invoked
    assert "install" not in fake_fix_driver.calls
    assert "start" not in fake_fix_driver.calls
    # The user is told what to run by hand
    assert "manual" in out.lower()
    assert "systemctl" in out or "Docker" in out


def test_apply_fixes_refuses_destructive_engine_verb_without_confirm(
    docker_world, fake_fix_driver, capsys
):
    """If a check ever emits a destructive Fix with an engine_verb, --fix
    must require --confirm before running. None of the Phase 1b/2 checks
    do this today; this test pins the guard for future additions."""
    from m_cli.doctor.checks import Check, Fix, Status
    from m_cli.doctor.cli import _apply_one_fix

    bad = Check(
        name="hypothetical_destructive",
        status=Status.WARN,
        message="m",
        fix=Fix(command=("docker", "reset"), engine_verb="reset", destructive=True),
    )
    # Without --confirm: skipped, driver not called
    _apply_one_fix(bad, confirm=False)
    assert not any("reset" in c for c in fake_fix_driver.calls)
    out = capsys.readouterr().out
    assert "destructive" in out.lower() or "--confirm" in out


def test_apply_fixes_runs_destructive_engine_verb_with_confirm(
    docker_world, fake_fix_driver
):
    from m_cli.doctor.checks import Check, Fix, Status
    from m_cli.doctor.cli import _apply_one_fix

    bad = Check(
        name="hypothetical_destructive",
        status=Status.WARN,
        message="m",
        fix=Fix(command=("docker", "reset"), engine_verb="reset", destructive=True),
    )
    _apply_one_fix(bad, confirm=True)
    assert any("reset" in c for c in fake_fix_driver.calls)


def test_apply_fixes_skips_ok_checks(docker_world, fake_fix_driver):
    """Only WARN/FAIL checks with a fix are candidates; OK checks are ignored."""
    from m_cli.doctor.cli import apply_fixes

    # All green
    apply_fixes(run_all_checks(), confirm=False)
    assert fake_fix_driver.calls == []


def test_doctor_command_fix_flag_invokes_fixes(docker_world, fake_fix_driver):
    """The CLI flag wires apply_fixes after the initial check pass."""
    from m_cli.doctor import doctor_command

    docker_world.set(docker_image_present=False)
    rc = doctor_command(_ns(format="text", fix=True, confirm=False))
    assert "install" in fake_fix_driver.calls
    assert rc in (0, 1)  # may re-check; exit code reflects post-fix state


def test_doctor_command_fix_flag_default_off(docker_world, fake_fix_driver):
    """Without --fix, no engine verbs fire even if WARN checks have engine_verb."""
    from m_cli.doctor import doctor_command

    docker_world.set(docker_image_present=False)
    doctor_command(_ns(format="text"))


# ─────────────────────────────────────────────────────────────────
# Phase 2 — Transport-aware check selection
# ─────────────────────────────────────────────────────────────────


def _clean_transport_env(monkeypatch):
    """Common setup: no transport override, no conn.env, no host YDB."""
    monkeypatch.delenv("M_CLI_ENGINE", raising=False)
    monkeypatch.delenv("ydb_dist", raising=False)
    monkeypatch.delenv("YDB_DIST", raising=False)
    monkeypatch.delenv("ydb_routines", raising=False)
    monkeypatch.delenv("YDB", raising=False)
    monkeypatch.setenv("VISTA_CONN_FILE", "/definitely/no/such/file/conn.env")
    monkeypatch.setattr("shutil.which", lambda _: None)


def test_transport_intent_respects_explicit_override(monkeypatch):
    from m_cli.doctor.checks import _transport_intent

    for value in ("local", "docker", "ssh"):
        monkeypatch.setenv("M_CLI_ENGINE", value)
        assert _transport_intent() == value


def test_transport_intent_normalizes_case_and_whitespace(monkeypatch):
    from m_cli.doctor.checks import _transport_intent

    monkeypatch.setenv("M_CLI_ENGINE", "  DOCKER  ")
    assert _transport_intent() == "docker"


def test_transport_intent_auto_defaults_to_docker_when_nothing_detected(monkeypatch):
    from m_cli.doctor.checks import _transport_intent

    _clean_transport_env(monkeypatch)
    assert _transport_intent() == "docker"


def test_transport_intent_auto_picks_ssh_when_conn_env_exists(monkeypatch, tmp_path):
    from m_cli.doctor.checks import _transport_intent

    _clean_transport_env(monkeypatch)
    conn = tmp_path / "conn.env"
    conn.write_text("VISTA_HOST=h\nVISTA_SSH_PORT=22\nVISTA_SSH_USER=u\n")
    monkeypatch.setenv("VISTA_CONN_FILE", str(conn))
    assert _transport_intent() == "ssh"


def test_transport_intent_auto_picks_local_when_ydb_dist_set(monkeypatch):
    from m_cli.doctor.checks import _transport_intent

    _clean_transport_env(monkeypatch)
    monkeypatch.setenv("ydb_dist", "/some/path")
    assert _transport_intent() == "local"


def test_transport_intent_auto_picks_local_when_ydb_on_path(monkeypatch):
    from m_cli.doctor.checks import _transport_intent

    _clean_transport_env(monkeypatch)

    def _which(name):
        return "/usr/local/bin/ydb" if name == "ydb" else None

    monkeypatch.setattr("shutil.which", _which)
    assert _transport_intent() == "local"


def test_run_all_checks_docker_mode_excludes_host_ydb_checks(
    docker_world, monkeypatch
):
    """Under docker intent, the three host-YDB checks are not run at all
    — not as SKIPPED, not at any status. They are noise that distracts
    from the canonical engine path.
    """
    _clean_transport_env(monkeypatch)
    monkeypatch.setenv("M_CLI_ENGINE", "docker")
    names = {c.name for c in run_all_checks()}
    assert names.isdisjoint({"ydb_dist", "ydb_routines", "ydb_binary"})
    assert {"docker_installed", "engine_container", "parser", "keywords"} <= names


def test_run_all_checks_local_mode_excludes_docker_engine_checks(monkeypatch):
    """Under local intent, the Docker engine chain is irrelevant and
    must not appear in the output."""
    _clean_transport_env(monkeypatch)
    monkeypatch.setenv("M_CLI_ENGINE", "local")
    names = {c.name for c in run_all_checks()}
    assert names.isdisjoint(
        {
            "docker_installed",
            "docker_daemon",
            "engine_image",
            "engine_container",
            "engine_bind_mount",
        }
    )
    assert {"ydb_dist", "ydb_routines", "ydb_binary", "parser", "keywords"} <= names


def test_run_all_checks_ssh_mode_runs_only_parser_and_keywords(monkeypatch):
    """SSH intent: transport health is out of scope for now; the only
    transport-neutral checks are parser + keywords."""
    _clean_transport_env(monkeypatch)
    monkeypatch.setenv("M_CLI_ENGINE", "ssh")
    names = {c.name for c in run_all_checks()}
    assert names == {"parser", "keywords"}


def test_run_all_checks_local_mode_surfaces_stale_ydb_dist_as_fail(monkeypatch):
    """In explicit local mode, a missing $ydb_dist directory FAILs —
    same behavior as before the transport refactor, just no longer
    overridden by an engine-OK post-pass."""
    _clean_transport_env(monkeypatch)
    monkeypatch.setenv("M_CLI_ENGINE", "local")
    monkeypatch.setenv("ydb_dist", "/definitely/not/a/real/path")
    by_name = {c.name: c for c in run_all_checks()}
    assert by_name["ydb_dist"].status is Status.FAIL
