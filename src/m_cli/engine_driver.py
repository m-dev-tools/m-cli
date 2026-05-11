"""Engine lifecycle drivers — the ``m engine`` subcommand backend.

Distinct from :mod:`m_cli.engine` (which handles **routine execution** —
"given a running engine, build the command to exec inside it"). This
module handles **engine lifecycle** — "install / start / stop / inspect
the engine itself".

The :class:`EngineDriver` Protocol is the public seam for out-of-tree
drivers (IRIS, podman, …). The built-in :class:`DockerDriver` shells
out to ``docker`` / ``docker compose`` and is driven entirely by the
vendored :mod:`m_cli.engine_manifest`. Tests inject a custom
``runner`` to avoid actually running ``docker`` calls.

Implements the Phase 2 surface decided in
``m-test-engine/docs/m-engine-implementation-plan.md``.
"""

from __future__ import annotations

import importlib.metadata as _md
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Protocol

from m_cli.engine_manifest import EngineManifest

# Entry-point group that out-of-tree drivers register against.
# Locked under PLUGIN_API_VERSION = 1 (see m_cli.plugins).
#
# Example downstream pyproject.toml:
#
#     [project.entry-points."m_cli_engines"]
#     iris = "m_cli_iris_engine.driver:IrisDriver"
#
# The named attribute must be a class implementing :class:`EngineDriver`.
ENGINE_DRIVER_ENTRY_POINT_GROUP = "m_cli_engines"


# Result type from a single shell-out: returncode + captured stdout/stderr.
@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


# A `runner` is any callable that takes argv + optional kwargs and returns
# a CommandResult. The default runner shells out via subprocess; tests
# inject a fake that returns canned results without touching the real
# Docker daemon.
Runner = Callable[..., CommandResult]


def default_runner(
    argv: list[str],
    *,
    capture: bool = True,
    timeout: float | None = None,
) -> CommandResult:
    """Shell-out via :mod:`subprocess`. Used by every built-in driver."""
    try:
        result = subprocess.run(
            argv,
            capture_output=capture,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return CommandResult(returncode=127, stderr=str(exc))
    except subprocess.TimeoutExpired as exc:
        # text=True is set on subprocess.run above so stdout/stderr are
        # str when the call completes; on timeout, they remain bytes|None
        # per CPython stdlib. Decode defensively.
        out_raw: bytes | str | None = exc.stdout
        err_raw: bytes | str | None = exc.stderr
        out_str: str = (
            out_raw.decode(errors="replace") if isinstance(out_raw, bytes) else (out_raw or "")
        )
        err_str: str = (
            err_raw.decode(errors="replace") if isinstance(err_raw, bytes) else (err_raw or "")
        )
        return CommandResult(
            returncode=124,
            stdout=out_str,
            stderr=err_str + f"\ntimeout after {timeout}s",
        )
    return CommandResult(
        returncode=result.returncode,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
    )


# ── Status payload ───────────────────────────────────────────────────


@dataclass(frozen=True)
class EngineStatus:
    """Snapshot of the engine state. Used by ``m engine status`` text/JSON output."""

    driver: str  # e.g. "docker"
    installed: bool  # CLI present
    daemon_reachable: bool  # docker info reachable (or n/a)
    image_present: bool  # image is pulled locally
    container_running: bool  # canonical container is up
    container_healthy: bool | None  # True/False from docker healthcheck; None when no healthcheck
    image_ref: str
    container: str
    image_labels: dict[str, str] = field(default_factory=dict)
    mismatches: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "driver": self.driver,
            "installed": self.installed,
            "daemon_reachable": self.daemon_reachable,
            "image_present": self.image_present,
            "container_running": self.container_running,
            "container_healthy": self.container_healthy,
            "image_ref": self.image_ref,
            "container": self.container,
            "image_labels": dict(self.image_labels),
            "mismatches": list(self.mismatches),
        }


# ── Protocol ─────────────────────────────────────────────────────────


class EngineDriver(Protocol):
    """Public lifecycle protocol for engine drivers.

    Locked under ``PLUGIN_API_VERSION = 1``. Out-of-tree drivers
    (e.g. ``m-cli-iris-engine``) register via the ``m_cli_engines``
    Python entry-point group; the built-in :class:`DockerDriver` is the
    only driver registered in core.

    Every method returns an exit code (``0`` for success) so callers
    can compose lifecycle ops with shell-style semantics. Output that
    should reach the user is printed by the driver; the caller decides
    whether to also act on it.
    """

    name: str  # e.g. "docker"

    def status(self) -> EngineStatus: ...
    def install(self) -> int: ...
    def start(self) -> int: ...
    def stop(self) -> int: ...
    def restart(self) -> int: ...
    def logs(self, follow: bool = False) -> int: ...
    def shell(self) -> int: ...
    def exec(self, m_cmd: str) -> int: ...
    def version(self, *, as_json: bool = False) -> int: ...
    def reset(self, *, confirm: bool = False) -> int: ...


# ── DockerDriver — the only built-in driver ─────────────────────────


@dataclass
class DockerDriver:
    """Default driver: shells out to ``docker`` / ``docker compose``.

    All command construction reads from ``manifest`` — image refs,
    container name, compose file path, run_args fallback. No hardcoded
    strings.
    """

    manifest: EngineManifest
    runner: Runner = field(default=default_runner)
    name: str = "docker"

    # ── primitives ───────────────────────────────────────────────────

    def _docker_available(self) -> bool:
        return shutil.which("docker") is not None

    def _daemon_reachable(self) -> bool:
        if not self._docker_available():
            return False
        return self.runner(["docker", "info"], capture=True, timeout=5).ok

    def _image_present(self) -> bool:
        return self.runner(
            ["docker", "image", "inspect", self.manifest.image_ref()],
            capture=True,
            timeout=5,
        ).ok

    def _container_running(self) -> bool:
        result = self.runner(
            [
                "docker",
                "ps",
                "--filter",
                f"name=^{self.manifest.container}$",
                "--format",
                "{{.Names}}",
            ],
            capture=True,
            timeout=5,
        )
        return result.ok and self.manifest.container in result.stdout.split()

    def _container_state(self) -> str | None:
        """Return the canonical container's state, or ``None`` if absent.

        Common values: ``running``, ``exited``, ``created``. Drives the
        idempotency in :meth:`start` / :meth:`stop` / :meth:`reset`:
        ``docker run`` fails when a container with the same name already
        exists, so the lifecycle verbs branch on state rather than
        assuming a clean slate.
        """
        result = self.runner(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Status}}",
                self.manifest.container,
            ],
            capture=True,
            timeout=5,
        )
        if not result.ok:
            return None
        state = result.stdout.strip()
        return state or None

    def _image_labels(self) -> dict[str, str]:
        """Read OCI labels from the pulled image. Empty dict if not present."""
        import json as _json

        result = self.runner(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                "{{ json .Config.Labels }}",
                self.manifest.image_ref(),
            ],
            capture=True,
            timeout=5,
        )
        if not result.ok or not result.stdout.strip():
            return {}
        try:
            parsed = _json.loads(result.stdout.strip())
        except _json.JSONDecodeError:
            return {}
        # docker inspect returns `null` (the JSON literal) when no labels
        # are set — _json.loads turns that into Python None.
        if not isinstance(parsed, dict):
            return {}
        return {str(k): str(v) for k, v in parsed.items()}

    def _classify_mismatches(self, labels: dict[str, str]) -> tuple[str, ...]:
        """Diff image labels against the manifest; name each discrepancy.

        Returns a tuple of mismatch classifications (e.g.
        ``protocol_mismatch``, ``image_outdated``, ``bind_mount_drift``,
        ``ydb_version_drift``). Empty when labels match the manifest's
        published expectations.

        Empty input (no labels read) → empty output: m-cli can't
        classify what it can't observe.
        """
        if not labels:
            return ()
        m = self.manifest
        out: list[str] = []

        # Protocol comparison: bidirectional.
        raw_proto = labels.get("org.m-dev-tools.m-test-engine.protocol")
        if raw_proto is not None:
            try:
                image_proto = int(raw_proto)
            except ValueError:
                image_proto = None
            if image_proto is not None:
                if image_proto < m.protocol:
                    # m-cli has newer expectations than the pulled image
                    # satisfies — user should `m engine upgrade`.
                    out.append("image_outdated")
                elif image_proto > m.protocol:
                    # Image speaks newer protocol than m-cli understands.
                    out.append("protocol_mismatch")

        # Bind-mount drift — the published image baked the wrong path.
        raw_bm = labels.get("org.m-dev-tools.m-test-engine.bind-mount")
        if raw_bm is not None and raw_bm != m.bind_mount.container:
            out.append("bind_mount_drift")

        # YDB version drift — image was built on a different YDB release
        # than the manifest declares as canonical.
        raw_ydb = labels.get("org.m-dev-tools.m-test-engine.ydb-version")
        if raw_ydb is not None and raw_ydb != m.ydb_version:
            out.append("ydb_version_drift")

        return tuple(out)

    def _container_health(self) -> bool | None:
        """Read the container's healthcheck status from ``docker inspect``.

        Returns True for "healthy", False for "unhealthy", None for
        "starting" / "none" / container missing / docker error.
        """
        result = self.runner(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Health.Status}}",
                self.manifest.container,
            ],
            capture=True,
            timeout=5,
        )
        if not result.ok:
            return None
        status = result.stdout.strip()
        if status == "healthy":
            return True
        if status == "unhealthy":
            return False
        return None

    # ── lifecycle verbs ──────────────────────────────────────────────

    def status(self) -> EngineStatus:
        """Snapshot the engine state."""
        installed = self._docker_available()
        daemon = installed and self._daemon_reachable()
        image = daemon and self._image_present()
        running = daemon and self._container_running()
        labels = self._image_labels() if image else {}
        mismatches = self._classify_mismatches(labels) if labels else ()
        healthy = self._container_health() if running else None

        return EngineStatus(
            driver=self.name,
            installed=installed,
            daemon_reachable=daemon,
            image_present=image,
            container_running=running,
            container_healthy=healthy,
            image_ref=self.manifest.image_ref(),
            container=self.manifest.container,
            image_labels=labels,
            mismatches=mismatches,
        )

    def install(self) -> int:
        """Pull the canonical engine image."""
        result = self.runner(
            ["docker", "pull", self.manifest.image_ref()],
            capture=False,
        )
        return result.returncode

    def _docker_run(self) -> int:
        """Create + start the canonical container from manifest data.

        Constructs ``docker run`` from the manifest's ``run_args`` block
        + ``bind_mount``. The manifest is the single source of truth for
        image, container, volumes, and command — m-cli never reads the
        upstream m-test-engine compose.yml, which would require the
        repo to be checked out at a known location AND references a
        different image (``m-test-engine:latest``) than the manifest.
        """
        bm = self.manifest.bind_mount
        ra = self.manifest.run_args
        argv = [
            "docker",
            "run",
            "-d",
            "--name",
            self.manifest.container,
            "--hostname",
            ra.hostname,
            "--restart",
            ra.restart,
            "-w",
            ra.working_dir,
            "-v",
            f"{bm.host}:{bm.container}:{bm.mode}",
        ]
        for vol in ra.volumes:
            argv.extend(["-v", f"{vol.name}:{vol.target}"])
        argv.append(self.manifest.image_ref())
        argv.extend(ra.command)
        result = self.runner(argv, capture=False)
        return result.returncode

    def start(self) -> int:
        """Start the engine container — idempotent across container states."""
        state = self._container_state()
        if state == "running":
            print(f"container `{self.manifest.container}` already running")
            return 0
        if state is not None:
            result = self.runner(
                ["docker", "start", self.manifest.container],
                capture=False,
            )
            return result.returncode
        return self._docker_run()

    def stop(self) -> int:
        """Stop the engine container. Globals volume preserved.

        Idempotent: no-op if the container is absent or already stopped.
        """
        state = self._container_state()
        if state is None or state != "running":
            return 0
        result = self.runner(
            ["docker", "stop", self.manifest.container],
            capture=False,
        )
        return result.returncode

    def restart(self) -> int:
        state = self._container_state()
        if state == "running":
            result = self.runner(
                ["docker", "stop", self.manifest.container],
                capture=True,
                timeout=30,
            )
            if not result.ok:
                if result.stderr:
                    print(result.stderr, end="")
                return result.returncode
        if state is not None:
            result = self.runner(
                ["docker", "start", self.manifest.container],
                capture=True,
                timeout=30,
            )
            if not result.ok:
                if result.stderr:
                    print(result.stderr, end="")
                return result.returncode
        else:
            rc = self._docker_run()
            if rc != 0:
                return rc
        print(f"restarted {self.manifest.container}")
        return 0

    def logs(self, follow: bool = False) -> int:
        argv = ["docker", "logs"]
        if follow:
            argv.append("--follow")
        argv.append(self.manifest.container)
        # follow streams; never capture
        result = self.runner(argv, capture=not follow)
        if not follow and result.stdout:
            print(result.stdout, end="")
        return result.returncode

    def shell(self) -> int:
        """Drop into an interactive bash shell inside the container."""
        # Interactive: tty must be inherited. runner caller is responsible
        # for not capturing; default_runner with capture=False suffices.
        result = self.runner(
            ["docker", "exec", "-it", self.manifest.container, "bash"],
            capture=False,
        )
        return result.returncode

    def exec(self, m_cmd: str) -> int:
        """One-shot M command via ``mumps -run %XCMD``.

        Useful for ad-hoc inspection. Exit code matters; output goes to
        stdout/stderr unchanged.
        """
        import shlex

        # Inside the container, bash -lc sources /etc/profile.d/ydb-env.sh
        # so $ydb_dist is set.
        inner = f"$ydb_dist/mumps -run %XCMD {shlex.quote(m_cmd)}"
        result = self.runner(
            ["docker", "exec", self.manifest.container, "bash", "-lc", inner],
            capture=False,
        )
        return result.returncode

    def version(self, *, as_json: bool = False) -> int:
        """Print manifest-declared vs image-reported labels side-by-side.

        Text output renders each comparable field with ✓ (match) or ✗
        (mismatch) so version-skew between vendored manifest and pulled
        image is visible at a glance. ``as_json=True`` emits the same
        data as a structured JSON document for tooling.
        """
        import json as _json

        m = self.manifest
        labels = self._image_labels()

        fields = [
            (
                "protocol",
                str(m.protocol),
                labels.get("org.m-dev-tools.m-test-engine.protocol", ""),
            ),
            (
                "ydb-version",
                m.ydb_version,
                labels.get("org.m-dev-tools.m-test-engine.ydb-version", ""),
            ),
            (
                "bind-mount",
                m.bind_mount.container,
                labels.get("org.m-dev-tools.m-test-engine.bind-mount", ""),
            ),
        ]
        image_rev = labels.get("org.m-dev-tools.m-test-engine.image-rev", "")

        result = self.runner(
            ["docker", "inspect", "--format", "{{.Image}}", m.container],
            capture=True,
            timeout=5,
        )
        running_image_id = result.stdout.strip() if (result.ok and result.stdout.strip()) else None

        any_mismatch = any(
            reported and declared != reported for _, declared, reported in fields
        )

        if as_json:
            payload = {
                "image_ref": m.image_ref(),
                "fields": [
                    {
                        "name": name,
                        "manifest": declared,
                        "image": reported or None,
                        "match": (declared == reported) if reported else None,
                    }
                    for name, declared, reported in fields
                ],
                "image_rev": image_rev or None,
                "container_image_id": running_image_id,
                "any_mismatch": any_mismatch,
            }
            print(_json.dumps(payload, indent=2))
            return 0

        print(f"image:     {m.image_ref()}")
        print()
        print("                    manifest          image")
        print("                    ----------------  ----------------")
        for name, declared, reported in fields:
            if not reported:
                mark = "-"
                display = "—"
            elif declared == reported:
                mark = "✓"
                display = reported
            else:
                mark = "✗"
                display = reported
            print(f"  {mark} {name:<16}  {declared:<16}  {display}")
        print(f"    {'image-rev':<16}  {'(none)':<16}  {image_rev or '—'}")
        print()
        if running_image_id:
            print(f"container: image-id={running_image_id}")
        else:
            print("container: not running")
        if any_mismatch:
            print()
            print("⚠ mismatch detected — run `m engine install` then recreate the container.")
        return 0

    def reset(self, *, confirm: bool = False) -> int:
        """Destructive: stop + remove + drop globals volume.

        Refuses to run without ``confirm=True``. After reset, the next
        ``start`` produces a fresh container with empty globals — useful
        when a stuck global/lock state poisons tests.
        """
        if not confirm:
            print(
                "refusing: `m engine reset` is destructive (drops the "
                "globals volume). Re-run with --confirm.",
                flush=True,
            )
            return 2
        state = self._container_state()
        if state == "running":
            self.runner(["docker", "stop", self.manifest.container], capture=False)
        if state is not None:
            self.runner(["docker", "rm", self.manifest.container], capture=False)
        for vol in self.manifest.run_args.volumes:
            self.runner(["docker", "volume", "rm", vol.name], capture=False)
        return 0


# ── Entry-point driver discovery ─────────────────────────────────────


@dataclass(frozen=True)
class DriverInfo:
    """Metadata for a discovered engine driver."""

    name: str
    package: str
    entry_point: str


def discover_drivers() -> list[DriverInfo]:
    """Walk the ``m_cli_engines`` entry-point group.

    The built-in ``docker`` driver is **not** included here — only
    out-of-tree drivers. m-cli's CLI always falls back to
    :class:`DockerDriver` when no override is requested. Today this
    function returns an empty list on most installs; the seam exists so
    a future ``m-cli-iris-engine`` package can register.
    """
    out: list[DriverInfo] = []
    for ep in _md.entry_points(group=ENGINE_DRIVER_ENTRY_POINT_GROUP):
        dist = getattr(ep, "dist", None)
        pkg = getattr(dist, "name", None) or ep.value.split(":", 1)[0].split(".", 1)[0]
        out.append(DriverInfo(name=ep.name, package=pkg, entry_point=ep.value))
    return out


__all__ = [
    "CommandResult",
    "DockerDriver",
    "DriverInfo",
    "ENGINE_DRIVER_ENTRY_POINT_GROUP",
    "EngineDriver",
    "EngineStatus",
    "Runner",
    "default_runner",
    "discover_drivers",
]
