"""Tests for the EngineDriver Protocol + built-in DockerDriver.

The driver layer manages engine **lifecycle** (install / start / stop /
inspect) — distinct from :mod:`m_cli.engine` which handles routine
execution against a running engine. The two collaborate but neither
imports the other.

Tests inject a fake ``runner`` so no actual ``docker`` calls fire. The
fake records every argv it sees so we can assert command shape +
manifest-derived values.

Phase 2 of the m-engine plan
(see m-test-engine/docs/m-engine-implementation-plan.md §2.2).
"""

from __future__ import annotations

import pytest

from m_cli.engine_driver import (
    CommandResult,
    DockerDriver,
    EngineDriver,
    EngineStatus,
)
from m_cli.engine_manifest import load_engine_manifest


@pytest.fixture
def manifest():
    return load_engine_manifest()


@pytest.fixture
def fake_runner():
    """Returns a runner callable that records calls and dispatches via a rules dict.

    Tests configure ``world.rule(prefix=tuple_of_args, result=CommandResult)``
    or ``world.default = CommandResult(...)`` to drive specific argv
    matches without faking subprocess module-wide.
    """
    calls: list[list[str]] = []
    rules: list[tuple[tuple[str, ...], CommandResult]] = []
    default = CommandResult(returncode=0, stdout="", stderr="")

    def _runner(argv, *, capture=True, timeout=None):
        calls.append(list(argv))
        for prefix, result in rules:
            if tuple(argv[: len(prefix)]) == prefix:
                return result
        return default

    class _World:
        def __init__(self):
            self.calls = calls
            self.rules = rules
            self.runner = _runner

        def rule(self, prefix, result):
            self.rules.append((tuple(prefix), result))

        def set_default(self, result):
            nonlocal default
            default = result

    return _World()


# ── Protocol shape ───────────────────────────────────────────────────


def test_docker_driver_satisfies_engine_driver_protocol(manifest, fake_runner):
    drv: EngineDriver = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    assert drv.name == "docker"


def test_engine_status_dataclass_roundtrips_to_dict():
    s = EngineStatus(
        driver="docker",
        installed=True,
        daemon_reachable=True,
        image_present=False,
        container_running=False,
        container_healthy=None,
        image_ref="ghcr.io/example:tag",
        container="m-test-engine",
    )
    d = s.to_dict()
    assert d["driver"] == "docker"
    assert d["installed"] is True
    assert d["container_healthy"] is None  # serialised as null in JSON


# ── DockerDriver.status() ────────────────────────────────────────────


def test_docker_driver_status_uses_manifest_image_and_container(manifest, fake_runner):
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    s = drv.status()
    assert s.image_ref == manifest.image_ref()
    assert s.container == manifest.container


def test_docker_driver_status_reports_container_not_running_when_ps_empty(manifest, fake_runner):
    # docker info → ok; image inspect → ok; docker ps → empty stdout
    fake_runner.rule(prefix=["docker", "info"], result=CommandResult(returncode=0))
    fake_runner.rule(
        prefix=["docker", "image", "inspect"],
        result=CommandResult(returncode=0),
    )
    fake_runner.rule(
        prefix=["docker", "ps"],
        result=CommandResult(returncode=0, stdout=""),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    s = drv.status()
    assert s.container_running is False


def test_docker_driver_status_reports_running_when_ps_returns_name(manifest, fake_runner):
    fake_runner.rule(prefix=["docker", "info"], result=CommandResult(returncode=0))
    fake_runner.rule(
        prefix=["docker", "image", "inspect"],
        result=CommandResult(returncode=0),
    )
    fake_runner.rule(
        prefix=["docker", "ps"],
        result=CommandResult(returncode=0, stdout=f"{manifest.container}\n"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    s = drv.status()
    assert s.container_running is True


# ── install / start (compose-first, run fallback) ────────────────────


def test_docker_driver_install_pulls_image_ref(manifest, fake_runner):
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    rc = drv.install()
    assert rc == 0
    pulls = [c for c in fake_runner.calls if c[:2] == ["docker", "pull"]]
    assert len(pulls) == 1
    assert pulls[0] == ["docker", "pull", manifest.image_ref()]


def test_docker_driver_start_uses_expanded_host_bind_path(manifest, fake_runner):
    # The host side of the bind mount in `docker run -v <host>:<container>:<mode>`
    # must be an absolute, $HOME-expanded path — docker does not expand
    # env vars in volume specs, and the manifest declares `$HOME/m-work`.
    fake_runner.rule(
        prefix=["docker", "inspect", "--format"],
        result=CommandResult(returncode=1, stderr="No such object"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    drv.start()
    runs = [c for c in fake_runner.calls if c[:2] == ["docker", "run"]]
    assert len(runs) == 1
    run = runs[0]
    bm = manifest.bind_mount
    assert "$HOME" not in bm.host
    assert "~" not in bm.host
    assert bm.host.startswith("/")
    assert f"{bm.host}:{bm.container}:{bm.mode}" in run


def test_docker_driver_start_creates_container_when_absent(manifest, fake_runner):
    # `docker inspect` of a missing container fails → state is None →
    # driver creates the container via `docker run` from manifest data.
    fake_runner.rule(
        prefix=["docker", "inspect", "--format"],
        result=CommandResult(returncode=1, stderr="No such object"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    drv.start()
    runs = [c for c in fake_runner.calls if c[:2] == ["docker", "run"]]
    assert len(runs) == 1
    run = runs[0]
    # Container name + image from manifest
    assert manifest.container in run
    assert manifest.image_ref() in run
    # Bind mount from manifest fields
    bm = manifest.bind_mount
    expected_bind = f"{bm.host}:{bm.container}:{bm.mode}"
    assert expected_bind in run
    # Secondary volumes
    for vol in manifest.run_args.volumes:
        assert f"{vol.name}:{vol.target}" in run
    # working_dir from run_args
    assert manifest.run_args.working_dir in run


def test_docker_driver_start_calls_docker_start_when_container_stopped(manifest, fake_runner):
    # Container exists but exited → driver issues `docker start` rather
    # than `docker run` (which would error on name conflict).
    fake_runner.rule(
        prefix=["docker", "inspect", "--format"],
        result=CommandResult(returncode=0, stdout="exited\n"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    rc = drv.start()
    assert rc == 0
    starts = [c for c in fake_runner.calls if c[:2] == ["docker", "start"]]
    assert starts == [["docker", "start", manifest.container]]
    runs = [c for c in fake_runner.calls if c[:2] == ["docker", "run"]]
    assert runs == []


def test_docker_driver_start_is_noop_when_container_already_running(manifest, fake_runner):
    fake_runner.rule(
        prefix=["docker", "inspect", "--format"],
        result=CommandResult(returncode=0, stdout="running\n"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    rc = drv.start()
    assert rc == 0
    # No `docker run` or `docker start` calls — just the inspect probe.
    assert all(c[:2] not in (["docker", "run"], ["docker", "start"]) for c in fake_runner.calls)


# ── stop / restart / reset ───────────────────────────────────────────


def test_docker_driver_stop_issues_docker_stop_when_running(manifest, fake_runner):
    fake_runner.rule(
        prefix=["docker", "inspect", "--format"],
        result=CommandResult(returncode=0, stdout="running\n"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    rc = drv.stop()
    assert rc == 0
    stops = [c for c in fake_runner.calls if c[:2] == ["docker", "stop"]]
    assert stops == [["docker", "stop", manifest.container]]


def test_docker_driver_stop_is_noop_when_container_absent(manifest, fake_runner):
    fake_runner.rule(
        prefix=["docker", "inspect", "--format"],
        result=CommandResult(returncode=1, stderr="No such object"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    rc = drv.stop()
    assert rc == 0
    assert [c for c in fake_runner.calls if c[:2] == ["docker", "stop"]] == []


def test_docker_driver_stop_is_noop_when_already_stopped(manifest, fake_runner):
    fake_runner.rule(
        prefix=["docker", "inspect", "--format"],
        result=CommandResult(returncode=0, stdout="exited\n"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    rc = drv.stop()
    assert rc == 0
    assert [c for c in fake_runner.calls if c[:2] == ["docker", "stop"]] == []


def test_docker_driver_reset_refuses_without_confirm(manifest, fake_runner, capsys):
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    rc = drv.reset(confirm=False)
    out = capsys.readouterr().out
    assert rc != 0
    assert "destructive" in out.lower()
    assert "--confirm" in out


def test_docker_driver_reset_with_confirm_stops_removes_and_drops_volumes(manifest, fake_runner):
    # Container running → stop + rm + per-volume rm.
    fake_runner.rule(
        prefix=["docker", "inspect", "--format"],
        result=CommandResult(returncode=0, stdout="running\n"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    rc = drv.reset(confirm=True)
    assert rc == 0
    stops = [c for c in fake_runner.calls if c[:2] == ["docker", "stop"]]
    rms = [c for c in fake_runner.calls if c[:2] == ["docker", "rm"]]
    vol_rms = [c for c in fake_runner.calls if c[:3] == ["docker", "volume", "rm"]]
    assert stops == [["docker", "stop", manifest.container]]
    assert rms == [["docker", "rm", manifest.container]]
    assert len(vol_rms) == len(manifest.run_args.volumes)


def test_docker_driver_reset_with_confirm_skips_stop_when_container_absent(manifest, fake_runner):
    # Container doesn't exist → just drop the named volumes.
    fake_runner.rule(
        prefix=["docker", "inspect", "--format"],
        result=CommandResult(returncode=1, stderr="No such object"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    rc = drv.reset(confirm=True)
    assert rc == 0
    assert [c for c in fake_runner.calls if c[:2] == ["docker", "stop"]] == []
    assert [c for c in fake_runner.calls if c[:2] == ["docker", "rm"]] == []
    vol_rms = [c for c in fake_runner.calls if c[:3] == ["docker", "volume", "rm"]]
    assert len(vol_rms) == len(manifest.run_args.volumes)


# ── exec / shell / logs / version ────────────────────────────────────


def test_docker_driver_exec_wraps_in_bash_lc(manifest, fake_runner):
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    drv.exec("write 1+2,!")
    execs = [c for c in fake_runner.calls if c[:2] == ["docker", "exec"]]
    assert execs
    cmd = execs[0]
    assert manifest.container in cmd
    assert "bash" in cmd
    assert "-lc" in cmd
    # The M command is shlex-quoted inside the bash -lc script
    inner = cmd[-1]
    assert "%XCMD" in inner
    assert "write 1+2,!" in inner


def test_docker_driver_shell_uses_docker_exec_it(manifest, fake_runner):
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    drv.shell()
    shells = [c for c in fake_runner.calls if c[:3] == ["docker", "exec", "-it"] and "bash" in c]
    assert shells


def test_docker_driver_logs_follow_flag(manifest, fake_runner):
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    drv.logs(follow=True)
    follow_calls = [c for c in fake_runner.calls if c[:2] == ["docker", "logs"] and "--follow" in c]
    assert follow_calls


def test_docker_driver_version_prints_manifest_summary(manifest, fake_runner, capsys):
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    rc = drv.version()
    out = capsys.readouterr().out
    assert rc == 0
    assert manifest.image_ref() in out
    assert manifest.ydb_version in out
    assert "protocol" in out


# ── Entry-point group seam ───────────────────────────────────────────


def test_entry_point_group_name_is_locked():
    """The group name is part of the PLUGIN_API_VERSION contract."""
    from m_cli.engine_driver import ENGINE_DRIVER_ENTRY_POINT_GROUP

    assert ENGINE_DRIVER_ENTRY_POINT_GROUP == "m_cli_engines"


def test_discover_drivers_returns_list_without_builtin():
    """Built-in DockerDriver is NOT enumerated — only out-of-tree drivers."""
    from m_cli.engine_driver import discover_drivers

    drivers = discover_drivers()
    # The list may be empty (no out-of-tree drivers installed); the
    # built-in must never appear in it.
    assert all(d.name != "docker" for d in drivers)


# ── Phase 3b: OCI label reading + version-mismatch detection ─────────


# Helper: canned `docker image inspect --format '{{ json .Config.Labels }}'`
# output. Tests configure the runner to return one of these per scenario.
def _labels_stdout(labels: dict[str, str]) -> str:
    import json as _json

    return _json.dumps(labels) + "\n"


def _matching_labels(manifest) -> dict[str, str]:
    """Labels that exactly match the manifest — no mismatches."""
    return {
        "org.m-dev-tools.m-test-engine.protocol": str(manifest.protocol),
        "org.m-dev-tools.m-test-engine.bind-mount": manifest.bind_mount.container,
        "org.m-dev-tools.m-test-engine.ydb-version": manifest.ydb_version,
        "org.m-dev-tools.m-test-engine.image-rev": "deadbeef" * 5,
    }


def test_engine_status_carries_image_labels_and_mismatches_fields():
    """Phase 3b shape: EngineStatus exposes image-label payload + mismatch list."""
    s = EngineStatus(
        driver="docker",
        installed=True,
        daemon_reachable=True,
        image_present=True,
        container_running=True,
        container_healthy=True,
        image_ref="x:y",
        container="m-test-engine",
        image_labels={"org.m-dev-tools.m-test-engine.protocol": "1"},
        mismatches=("protocol_mismatch",),
    )
    d = s.to_dict()
    assert d["image_labels"] == {"org.m-dev-tools.m-test-engine.protocol": "1"}
    assert d["mismatches"] == ["protocol_mismatch"]


def test_engine_status_defaults_image_labels_to_empty_and_mismatches_to_empty():
    s = EngineStatus(
        driver="docker",
        installed=True,
        daemon_reachable=True,
        image_present=False,
        container_running=False,
        container_healthy=None,
        image_ref="x:y",
        container="m-test-engine",
    )
    assert s.image_labels == {}
    assert s.mismatches == ()


def test_docker_driver_image_labels_empty_when_no_image(manifest, fake_runner):
    """No image pulled → labels dict is empty (no inspect call necessary)."""
    fake_runner.rule(
        prefix=["docker", "image", "inspect", manifest.image_ref()],
        result=CommandResult(returncode=1, stderr="No such image"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    s = drv.status()
    assert s.image_present is False
    assert s.image_labels == {}
    # Mismatches require labels — no labels means no mismatches reported.
    assert s.mismatches == ()


def test_docker_driver_status_populates_image_labels_when_present(manifest, fake_runner):
    labels = _matching_labels(manifest)
    fake_runner.rule(prefix=["docker", "info"], result=CommandResult(returncode=0))
    fake_runner.rule(
        prefix=["docker", "image", "inspect", manifest.image_ref()],
        result=CommandResult(returncode=0),
    )
    # The label-reading call uses --format with a json template
    fake_runner.rule(
        prefix=["docker", "image", "inspect", "--format"],
        result=CommandResult(returncode=0, stdout=_labels_stdout(labels)),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    s = drv.status()
    assert s.image_labels == labels
    assert s.mismatches == ()


def test_docker_driver_status_detects_protocol_mismatch(manifest, fake_runner):
    labels = _matching_labels(manifest)
    labels["org.m-dev-tools.m-test-engine.protocol"] = str(manifest.protocol + 1)
    fake_runner.rule(prefix=["docker", "info"], result=CommandResult(returncode=0))
    fake_runner.rule(
        prefix=["docker", "image", "inspect", manifest.image_ref()],
        result=CommandResult(returncode=0),
    )
    fake_runner.rule(
        prefix=["docker", "image", "inspect", "--format"],
        result=CommandResult(returncode=0, stdout=_labels_stdout(labels)),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    s = drv.status()
    assert "protocol_mismatch" in s.mismatches


def test_docker_driver_status_detects_bind_mount_drift(manifest, fake_runner):
    labels = _matching_labels(manifest)
    labels["org.m-dev-tools.m-test-engine.bind-mount"] = "/wrong"
    fake_runner.rule(prefix=["docker", "info"], result=CommandResult(returncode=0))
    fake_runner.rule(
        prefix=["docker", "image", "inspect", manifest.image_ref()],
        result=CommandResult(returncode=0),
    )
    fake_runner.rule(
        prefix=["docker", "image", "inspect", "--format"],
        result=CommandResult(returncode=0, stdout=_labels_stdout(labels)),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    s = drv.status()
    assert "bind_mount_drift" in s.mismatches


def test_docker_driver_status_detects_ydb_version_drift(manifest, fake_runner):
    labels = _matching_labels(manifest)
    labels["org.m-dev-tools.m-test-engine.ydb-version"] = "r1.99"
    fake_runner.rule(prefix=["docker", "info"], result=CommandResult(returncode=0))
    fake_runner.rule(
        prefix=["docker", "image", "inspect", manifest.image_ref()],
        result=CommandResult(returncode=0),
    )
    fake_runner.rule(
        prefix=["docker", "image", "inspect", "--format"],
        result=CommandResult(returncode=0, stdout=_labels_stdout(labels)),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    s = drv.status()
    assert "ydb_version_drift" in s.mismatches


def test_docker_driver_status_image_outdated_when_protocol_lower_than_manifest(
    manifest, fake_runner
):
    """image_outdated fires when image protocol < manifest protocol — m-cli
    has newer expectations than the pulled image satisfies."""
    labels = _matching_labels(manifest)
    labels["org.m-dev-tools.m-test-engine.protocol"] = "0"
    fake_runner.rule(prefix=["docker", "info"], result=CommandResult(returncode=0))
    fake_runner.rule(
        prefix=["docker", "image", "inspect", manifest.image_ref()],
        result=CommandResult(returncode=0),
    )
    fake_runner.rule(
        prefix=["docker", "image", "inspect", "--format"],
        result=CommandResult(returncode=0, stdout=_labels_stdout(labels)),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    s = drv.status()
    assert "image_outdated" in s.mismatches or "protocol_mismatch" in s.mismatches


# ── DockerDriver.version() — Phase 3b.2 ──────────────────────────────


def test_docker_driver_version_shows_image_label_actuals_when_present(
    manifest, fake_runner, capsys
):
    labels = _matching_labels(manifest)
    fake_runner.rule(
        prefix=["docker", "image", "inspect", "--format"],
        result=CommandResult(returncode=0, stdout=_labels_stdout(labels)),
    )
    # docker inspect for image-id should still succeed
    fake_runner.rule(
        prefix=["docker", "inspect", "--format", "{{.Image}}"],
        result=CommandResult(returncode=0, stdout="sha256:abcdef\n"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    rc = drv.version()
    out = capsys.readouterr().out
    assert rc == 0
    # Manifest-declared lines
    assert manifest.image_ref() in out
    # Image-reported lines
    assert labels["org.m-dev-tools.m-test-engine.image-rev"][:7] in out or "deadbeef" in out
    assert "image" in out.lower()  # the comparison framing


def test_docker_driver_version_highlights_mismatch_in_protocol(manifest, fake_runner, capsys):
    labels = _matching_labels(manifest)
    labels["org.m-dev-tools.m-test-engine.protocol"] = str(manifest.protocol + 1)
    fake_runner.rule(
        prefix=["docker", "image", "inspect", "--format"],
        result=CommandResult(returncode=0, stdout=_labels_stdout(labels)),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    drv.version()
    out = capsys.readouterr().out
    # Some visible mismatch indicator — `mismatch`, `✗`, or both
    assert "mismatch" in out.lower() or "✗" in out


# ── container_healthy — sourced from docker inspect ─────────────────


def test_docker_driver_status_reports_healthy_from_docker_inspect(manifest, fake_runner):
    """When the container is running and its healthcheck reports `healthy`,
    EngineStatus.container_healthy is True."""
    fake_runner.rule(prefix=["docker", "info"], result=CommandResult(returncode=0))
    fake_runner.rule(
        prefix=["docker", "image", "inspect"],
        result=CommandResult(returncode=0),
    )
    fake_runner.rule(
        prefix=["docker", "ps"],
        result=CommandResult(returncode=0, stdout=f"{manifest.container}\n"),
    )
    fake_runner.rule(
        prefix=["docker", "inspect", "--format", "{{.State.Health.Status}}"],
        result=CommandResult(returncode=0, stdout="healthy\n"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    s = drv.status()
    assert s.container_healthy is True


def test_docker_driver_status_reports_unhealthy_from_docker_inspect(manifest, fake_runner):
    fake_runner.rule(prefix=["docker", "info"], result=CommandResult(returncode=0))
    fake_runner.rule(
        prefix=["docker", "image", "inspect"],
        result=CommandResult(returncode=0),
    )
    fake_runner.rule(
        prefix=["docker", "ps"],
        result=CommandResult(returncode=0, stdout=f"{manifest.container}\n"),
    )
    fake_runner.rule(
        prefix=["docker", "inspect", "--format", "{{.State.Health.Status}}"],
        result=CommandResult(returncode=0, stdout="unhealthy\n"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    s = drv.status()
    assert s.container_healthy is False


def test_docker_driver_status_healthy_none_when_no_healthcheck(manifest, fake_runner):
    """A container without a HEALTHCHECK reports nothing useful — keep None."""
    fake_runner.rule(prefix=["docker", "info"], result=CommandResult(returncode=0))
    fake_runner.rule(
        prefix=["docker", "image", "inspect"],
        result=CommandResult(returncode=0),
    )
    fake_runner.rule(
        prefix=["docker", "ps"],
        result=CommandResult(returncode=0, stdout=f"{manifest.container}\n"),
    )
    fake_runner.rule(
        prefix=["docker", "inspect", "--format", "{{.State.Health.Status}}"],
        result=CommandResult(returncode=0, stdout="\n"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    s = drv.status()
    assert s.container_healthy is None


def test_docker_driver_status_healthy_skipped_when_not_running(manifest, fake_runner):
    """No point asking docker inspect for health when the container is down."""
    fake_runner.rule(prefix=["docker", "info"], result=CommandResult(returncode=0))
    fake_runner.rule(
        prefix=["docker", "image", "inspect"],
        result=CommandResult(returncode=0),
    )
    fake_runner.rule(
        prefix=["docker", "ps"],
        result=CommandResult(returncode=0, stdout=""),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    s = drv.status()
    assert s.container_running is False
    assert s.container_healthy is None
    assert not any(
        c[:4] == ["docker", "inspect", "--format", "{{.State.Health.Status}}"]
        for c in fake_runner.calls
    )


# ── version() --json ─────────────────────────────────────────────────


def test_docker_driver_version_emits_json_when_as_json(manifest, fake_runner, capsys):
    import json as _json

    labels = _matching_labels(manifest)
    fake_runner.rule(
        prefix=["docker", "image", "inspect", "--format"],
        result=CommandResult(returncode=0, stdout=_labels_stdout(labels)),
    )
    fake_runner.rule(
        prefix=["docker", "inspect", "--format", "{{.Image}}"],
        result=CommandResult(returncode=0, stdout="sha256:abcdef\n"),
    )
    drv = DockerDriver(manifest=manifest, runner=fake_runner.runner)
    rc = drv.version(as_json=True)
    out = capsys.readouterr().out
    payload = _json.loads(out)
    assert rc == 0
    assert payload["image_ref"] == manifest.image_ref()
    field_names = [f["name"] for f in payload["fields"]]
    assert {"protocol", "ydb-version", "bind-mount"} <= set(field_names)
    assert payload["any_mismatch"] is False
    assert payload["container_image_id"] == "sha256:abcdef"
