"""Engine integration for runtime tools (test, coverage, trace).

m-cli's runtime tools (`m test`, `m coverage`, etc.) execute M code on a
YottaDB engine. Three transports are supported:

- :class:`LocalEngine` — locally-installed YottaDB; runs ``mumps`` via
  subprocess. Lightest; preferred default if available.
- :class:`DockerEngine` — YottaDB running in a Docker container
  (typically `m-dev-tools/m-test-engine`). Runs ``mumps`` via
  ``docker exec``. Cross-platform (Mac, no native YDB needed).
- :class:`SSHEngine` (= :class:`Connection` for backward compat) —
  remote YottaDB reachable over SSH. The legacy vista-meta path; kept
  for the maintainer's existing setup.

:func:`detect_engine` picks the right transport from the
``M_CLI_ENGINE`` env var (``local`` | ``docker`` | ``ssh``) or
auto-detects: if ``vista-meta``'s ``conn.env`` exists, use SSH (preserves
the existing maintainer workflow); else try local YottaDB; else try
Docker; else raise :class:`EngineNotConfigured` with guidance for all
three paths.

Pure-source tools (``m fmt``, ``m lint``) don't touch this module.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

# Default location of the SSH-mode connection-contract file (vista-meta
# legacy). Override with the ``VISTA_CONN_FILE`` env var (used in tests).
CONN_FILE = Path.home() / "data" / "vista-meta" / "conn.env"


class EngineNotConfigured(RuntimeError):
    """Raised when no transport can be resolved or its inputs are malformed."""


# ── Project root + routine discovery ──────────────────────────────────

_ROOT_MARKERS = ("pyproject.toml", "Makefile", ".git")

# Subdirs under a project root where we look for .m files to stage.
_ROUTINE_DIRS = (
    "src",
    "src/routines",
    "routines",
    "routines/tests",
    "tests",
    "tests/conformance",
    "tests/fixtures",
    "tests/fixtures/routines",
)


def project_root(start: Path) -> Path:
    """Walk up from ``start`` to find the project root.

    Markers (any of): ``pyproject.toml``, ``Makefile``, ``.git``. Falls
    back to the start path's parent if nothing matches.
    """
    start = start.resolve()
    candidates = [start] if start.is_dir() else [start.parent]
    candidates.extend(p for p in start.parents)
    for p in candidates:
        if any((p / m).exists() for m in _ROOT_MARKERS):
            return p
    return start.parent if start.is_file() else start


def remote_stage(start: Path) -> str:
    """SSH-mode remote staging dir for the project containing ``start``."""
    return f"$HOME/export/seed/{project_root(start).name}"


def _collect_routines(root: Path) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for sub in _ROUTINE_DIRS:
        d = root / sub
        if not d.is_dir():
            continue
        for f in d.glob("*.m"):
            r = f.resolve()
            if r in seen:
                continue
            seen.add(r)
            files.append(f)
    return files


# ── LocalEngine — locally-installed YottaDB ───────────────────────────


@dataclass(frozen=True)
class LocalEngine:
    """Runs ``mumps`` directly on the host as a subprocess.

    Requires YottaDB installed locally. ``ydb_dist`` is the directory
    containing the ``mumps`` / ``ydb`` binary; auto-detected from the
    ``ydb_dist`` env var or ``which ydb`` if not given.
    """

    ydb_dist: Path

    @classmethod
    def detect(cls) -> "LocalEngine":
        """Resolve ``ydb_dist`` from env vars or PATH."""
        for var in ("ydb_dist", "YDB_DIST"):
            val = os.environ.get(var)
            if val:
                return cls(ydb_dist=Path(val))
        for binary in ("ydb", "mumps"):
            found = shutil.which(binary)
            if found:
                return cls(ydb_dist=Path(found).parent)
        raise EngineNotConfigured(
            "LocalEngine: no YottaDB found. Install YottaDB locally, "
            "set $ydb_dist, or use a different transport "
            "(M_CLI_ENGINE=docker | ssh)."
        )

    def _mumps(self) -> str:
        return str(self.ydb_dist / "mumps")

    def _routines_value(self, stage: str) -> str:
        # Include $ydb_dist so YDB can find its own stdlib routines.
        return f"{stage} {self.ydb_dist}"

    def build_suite_cmd(self, suite_name: str, stage: str) -> list[str]:
        return [
            "env",
            f"ydb_routines={self._routines_value(stage)}",
            self._mumps(),
            "-run",
            f"^{suite_name}",
        ]

    def build_xcmd_cmd(self, m_cmd: str, stage: str) -> list[str]:
        return [
            "env",
            f"ydb_routines={self._routines_value(stage)}",
            self._mumps(),
            "-run",
            "%XCMD",
            m_cmd,
        ]

    def build_direct_cmd(self, stage: str) -> list[str]:
        return [
            "env",
            f"ydb_routines={self._routines_value(stage)}",
            self._mumps(),
            "-direct",
        ]

    def stage_routines(self, start: Path) -> str:
        """No copy — return the local routine dirs as a space-separated list."""
        root = project_root(start)
        dirs = [str(root / sub) for sub in _ROUTINE_DIRS if (root / sub).is_dir()]
        return " ".join(dirs) if dirs else str(root)


# ── DockerEngine — YottaDB in a container (m-test-engine) ─────────────


@dataclass(frozen=True)
class DockerEngine:
    """Runs ``mumps`` via ``docker exec`` against a long-running container.

    The container is typically ``m-test-engine`` started via
    ``m-dev-tools/m-test-engine``'s compose file. The compose file
    bind-mounts the consumer project's root as ``/work``, so the
    in-container path for any project file is ``/work/<rel-path>``.
    """

    container: str = "m-test-engine"
    bind_root: Path = field(default_factory=lambda: Path("/work"))

    def _exec_prefix(self) -> list[str]:
        return ["docker", "exec", self.container]

    def _shell_script(self, stage: str, body: str) -> str:
        # Inside the container, expand $ydb_dist via bash login shell.
        return (
            f'export ydb_routines="{stage} $ydb_dist" && '
            f"exec $ydb_dist/{body}"
        )

    def build_suite_cmd(self, suite_name: str, stage: str) -> list[str]:
        script = self._shell_script(stage, f"mumps -run ^{suite_name}")
        return [*self._exec_prefix(), "bash", "-lc", script]

    def build_xcmd_cmd(self, m_cmd: str, stage: str) -> list[str]:
        script = self._shell_script(stage, f"mumps -run %XCMD {shlex.quote(m_cmd)}")
        return [*self._exec_prefix(), "bash", "-lc", script]

    def build_direct_cmd(self, stage: str) -> list[str]:
        script = self._shell_script(stage, "mumps -direct")
        return [*self._exec_prefix(), "bash", "-lc", script]

    def stage_routines(self, start: Path) -> str:
        """Return the in-container path the host project root is bound to.

        Assumes the project root mounts to ``self.bind_root`` (the
        m-test-engine compose default). Routine dirs under it are
        space-separated, mirroring LocalEngine semantics.
        """
        root = project_root(start)
        dirs = [
            str(self.bind_root / sub)
            for sub in _ROUTINE_DIRS
            if (root / sub).is_dir()
        ]
        return " ".join(dirs) if dirs else str(self.bind_root)


# ── SSHEngine — remote YottaDB over SSH (legacy / vista-meta) ─────────


@dataclass(frozen=True)
class SSHEngine:
    """Remote YottaDB reachable over SSH.

    Originally written for vista-meta. The connection contract
    (``host``, ``ssh_port``, ``ssh_user``) is published by vista-meta's
    ``make run`` to ``~/data/vista-meta/conn.env``; loaded by
    :func:`read_connection`.
    """

    host: str
    ssh_port: int
    ssh_user: str

    @property
    def target(self) -> str:
        return f"{self.ssh_user}@{self.host}"

    def _ssh_argv(self, remote_cmd: str) -> list[str]:
        _CONTROL_DIR.mkdir(parents=True, exist_ok=True)
        return [
            "ssh",
            "-p",
            str(self.ssh_port),
            *_BASE_SSH_OPTS,
            self.target,
            remote_cmd,
        ]

    def _remote_script(self, stage: str, body: str) -> str:
        routines = f"{stage} $ydb_dist"
        return (
            "source /etc/profile.d/ydb_env.sh && "
            f"export ydb_routines={shlex.quote(routines)} && "
            f"exec $ydb_dist/{body}"
        )

    def build_suite_cmd(self, suite_name: str, stage: str) -> list[str]:
        return self._ssh_argv(self._remote_script(stage, f"mumps -run ^{suite_name}"))

    def build_xcmd_cmd(self, m_cmd: str, stage: str) -> list[str]:
        return self._ssh_argv(
            self._remote_script(stage, f"mumps -run %XCMD {shlex.quote(m_cmd)}")
        )

    def build_direct_cmd(self, stage: str) -> list[str]:
        return self._ssh_argv(self._remote_script(stage, "mumps -direct"))

    def stage_routines(self, start: Path) -> str:
        """Upload .m files via SCP and return the remote stage path.

        Side-effecting: actually copies files. Idempotent (clears the
        remote stage first).
        """
        root = project_root(start)
        stage = remote_stage(start)
        files = _collect_routines(root)
        _ssh_run(
            self,
            f"mkdir -p {stage} && find {stage} -maxdepth 1 -name '*.m' -delete",
        )
        if files:
            _scp_upload(self, files, stage)
        return stage


# Backward-compat alias. Old code imports `Connection` and
# `read_connection() -> Connection`; that surface is preserved.
Connection = SSHEngine

# Type alias for callers that want to type a parameter as "any engine".
Engine = Union[LocalEngine, DockerEngine, SSHEngine]


# ── conn.env parsing ──────────────────────────────────────────────────


def conn_file_path() -> Path:
    return Path(os.environ.get("VISTA_CONN_FILE") or CONN_FILE)


def read_connection(path: Path | None = None) -> SSHEngine:
    """Parse a vista-meta-style ``conn.env`` into an SSHEngine."""
    p = path or conn_file_path()
    if not p.exists():
        raise EngineNotConfigured(
            f"vista-meta connection not configured: {p} missing.\n"
            "Run: cd ~/projects/vista-meta && make run\n"
            "Or use a different transport: M_CLI_ENGINE=local | docker"
        )
    env: dict[str, str] = {}
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    try:
        return SSHEngine(
            host=env["VISTA_HOST"],
            ssh_port=int(env["VISTA_SSH_PORT"]),
            ssh_user=env["VISTA_SSH_USER"],
        )
    except KeyError as missing:
        raise EngineNotConfigured(
            f"missing key {missing} in {p}; "
            "regenerate via vista-meta: make write-conn"
        ) from None


# ── Engine resolver ───────────────────────────────────────────────────


def _has_local_ydb() -> bool:
    return bool(
        os.environ.get("ydb_dist")
        or os.environ.get("YDB_DIST")
        or shutil.which("ydb")
        or shutil.which("mumps")
    )


def _has_docker_engine_running() -> bool:
    """True if Docker is reachable and an `m-test-engine` container is up."""
    if not shutil.which("docker"):
        return False
    try:
        out = subprocess.run(
            ["docker", "ps", "--filter", "name=m-test-engine", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return "m-test-engine" in (out.stdout or "")


def detect_engine() -> Engine:
    """Resolve the active engine transport.

    Order of resolution:

    1. If ``M_CLI_ENGINE`` is set, use that (``local`` | ``docker`` | ``ssh``).
    2. If a vista-meta conn.env exists, use SSHEngine — preserves the
       maintainer's existing workflow without forcing a new transport.
    3. If a local YottaDB is detectable (``$ydb_dist`` or ``which ydb``),
       use LocalEngine.
    4. If a running ``m-test-engine`` container is detectable, use
       DockerEngine.
    5. Otherwise raise :class:`EngineNotConfigured` with guidance for
       all three paths.
    """
    forced = os.environ.get("M_CLI_ENGINE", "").strip().lower()
    if forced:
        if forced == "local":
            return LocalEngine.detect()
        if forced == "docker":
            return DockerEngine()
        if forced == "ssh":
            return read_connection()
        raise EngineNotConfigured(
            f"M_CLI_ENGINE={forced!r} unrecognized; expected local | docker | ssh"
        )

    # Auto-detect.
    if conn_file_path().exists():
        return read_connection()
    if _has_local_ydb():
        return LocalEngine.detect()
    if _has_docker_engine_running():
        return DockerEngine()
    raise EngineNotConfigured(
        "No engine transport detected. Pick one:\n"
        "  - local:  install YottaDB locally (apt install yottadb on Linux)\n"
        "  - docker: start the m-test-engine container "
        "(see m-dev-tools/m-test-engine)\n"
        "  - ssh:    set up vista-meta and run `make run` there\n"
        "Override with M_CLI_ENGINE=local|docker|ssh."
    )


# ── SSH plumbing (used by SSHEngine) ──────────────────────────────────

# ControlMaster keeps the SSH connection warm for 5 min so that the
# m test / m watch hot loops don't pay handshake cost on every call.
_CONTROL_DIR = Path.home() / ".ssh"
_CONTROL_PATH_FMT = str(_CONTROL_DIR / "cm-vista-%r@%h:%p")
_BASE_SSH_OPTS = (
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=no",
    "-o", "ServerAliveInterval=30",
    "-o", "ControlMaster=auto",
    "-o", f"ControlPath={_CONTROL_PATH_FMT}",
    "-o", "ControlPersist=300s",
)


def _ssh_run(conn: SSHEngine, remote_cmd: str) -> None:
    """Run ``remote_cmd`` over SSH; raise on nonzero exit."""
    subprocess.run(conn._ssh_argv(remote_cmd), check=True)


def _scp_upload(conn: SSHEngine, files: list[Path], remote_dir: str) -> None:
    """Upload ``files`` to ``remote_dir`` using legacy SCP protocol.

    vista-meta's sshd ships without the SFTP subsystem so the modern
    OpenSSH 9+ default fails; ``-O`` forces the original SCP protocol.
    """
    _CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        "scp", "-O",
        "-P", str(conn.ssh_port),
        *_BASE_SSH_OPTS,
        *[str(f) for f in files],
        f"{conn.target}:{remote_dir}/",
    ]
    subprocess.run(cmd, check=True)


# ── Backward-compat module-level helpers ──────────────────────────────
#
# These thin wrappers preserve the legacy import surface that runner.py,
# coverage/runner.py, and existing tests rely on. They dispatch to the
# engine's methods so they automatically work for any transport when
# given any engine — but the historical names retain "ssh" in them
# because the original implementation was SSH-only.


def build_suite_ssh_cmd(engine: Engine, suite_name: str, stage: str) -> list[str]:
    return engine.build_suite_cmd(suite_name, stage)


def build_xcmd_ssh_cmd(engine: Engine, m_cmd: str, stage: str) -> list[str]:
    return engine.build_xcmd_cmd(m_cmd, stage)


def build_direct_ssh_cmd(engine: Engine, stage: str) -> list[str]:
    return engine.build_direct_cmd(stage)


def seed_routines(start: Path, conn: SSHEngine | None = None) -> str:
    """Upload the project's .m files to the SSH-mode engine.

    Kept for legacy callers. New code should call
    ``engine.stage_routines(start)`` on whatever transport ``detect_engine``
    returned — local / docker no-ops the upload, SSH copies via SCP.
    """
    conn = conn or read_connection()
    return conn.stage_routines(start)


def seed_for_paths(
    paths: list[Path], conn: SSHEngine | None = None
) -> dict[Path, str]:
    """Seed every distinct project root in ``paths``."""
    conn = conn or read_connection()
    by_root: dict[Path, str] = {}
    for p in paths:
        root = project_root(p)
        if root in by_root:
            continue
        by_root[root] = conn.stage_routines(p)
    return by_root


__all__ = [
    "Connection",
    "DockerEngine",
    "Engine",
    "EngineNotConfigured",
    "LocalEngine",
    "SSHEngine",
    "build_direct_ssh_cmd",
    "build_suite_ssh_cmd",
    "build_xcmd_ssh_cmd",
    "detect_engine",
    "project_root",
    "read_connection",
    "remote_stage",
    "seed_for_paths",
    "seed_routines",
]
