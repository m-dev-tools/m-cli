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
    container_healthy: bool | None  # None until Phase 3 healthcheck lands
    image_ref: str
    container: str

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
    def version(self) -> int: ...
    def upgrade(self) -> int: ...
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

    def _has_compose_plugin(self) -> bool:
        return self.runner(["docker", "compose", "version"], capture=True, timeout=5).ok

    # ── lifecycle verbs ──────────────────────────────────────────────

    def status(self) -> EngineStatus:
        installed = self._docker_available()
        daemon = installed and self._daemon_reachable()
        image = daemon and self._image_present()
        running = daemon and self._container_running()
        return EngineStatus(
            driver=self.name,
            installed=installed,
            daemon_reachable=daemon,
            image_present=image,
            container_running=running,
            container_healthy=None,  # Phase 3 will source this from HEALTHCHECK
            image_ref=self.manifest.image_ref(),
            container=self.manifest.container,
        )

    def install(self) -> int:
        """Pull the canonical engine image."""
        result = self.runner(
            ["docker", "pull", self.manifest.image_ref()],
            capture=False,
        )
        return result.returncode

    def _start_via_compose(self) -> int:
        result = self.runner(
            [
                "docker",
                "compose",
                "-f",
                self.manifest.compose_file,
                "up",
                "-d",
            ],
            capture=False,
        )
        return result.returncode

    def _start_via_run(self) -> int:
        """Fallback when the compose plugin is unavailable.

        Constructs an equivalent ``docker run`` from the manifest's
        ``run_args`` block + ``bind_mount``. Functionally equivalent to
        compose for the single-service m-test-engine case.
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
        """Start the engine container; compose-first, ``docker run`` fallback."""
        if self._has_compose_plugin():
            return self._start_via_compose()
        return self._start_via_run()

    def stop(self) -> int:
        """Stop the engine container. Globals volume preserved."""
        if self._has_compose_plugin():
            result = self.runner(
                [
                    "docker",
                    "compose",
                    "-f",
                    self.manifest.compose_file,
                    "down",
                ],
                capture=False,
            )
            return result.returncode
        result = self.runner(
            ["docker", "stop", self.manifest.container],
            capture=False,
        )
        return result.returncode

    def restart(self) -> int:
        rc = self.stop()
        if rc != 0:
            return rc
        return self.start()

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

    def version(self) -> int:
        """Print manifest-declared vs container-reported versions."""
        m = self.manifest
        print(f"manifest:  image={m.image_ref()} ydb={m.ydb_version} protocol={m.protocol}")
        result = self.runner(
            ["docker", "inspect", "--format", "{{.Image}}", m.container],
            capture=True,
            timeout=5,
        )
        if result.ok and result.stdout.strip():
            print(f"container: image-id={result.stdout.strip()}")
        else:
            print("container: not running (manifest is the only available version)")
        return 0

    def upgrade(self) -> int:
        """Pull latest image and recreate container.

        Equivalent to ``install`` + ``stop`` + ``start``. Globals
        volume is preserved.
        """
        rc = self.install()
        if rc != 0:
            return rc
        rc = self.stop()
        if rc != 0:
            return rc
        return self.start()

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
        if self._has_compose_plugin():
            result = self.runner(
                [
                    "docker",
                    "compose",
                    "-f",
                    self.manifest.compose_file,
                    "down",
                    "-v",
                ],
                capture=False,
            )
            return result.returncode
        # docker run fallback: stop + rm + volume rm
        self.runner(["docker", "stop", self.manifest.container], capture=False)
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
