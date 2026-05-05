"""Vista-meta engine integration for runtime tools (test, coverage, trace).

m-cli's runtime tools execute M code remotely on the shared vista-meta
YottaDB container — there is no local YottaDB engine. This module owns
the connection contract and the SSH command builder. Pure-source tools
(``m fmt``, ``m lint``) don't touch this module.

Connection contract: ``~/data/vista-meta/conn.env`` is published by
``vista-meta``'s ``make run`` and read here. If the file is missing,
runtime tools raise :class:`EngineNotConfigured` with a clear message
pointing at vista-meta.

Staging convention: each project's ``.m`` files are uploaded once per
process to ``$HOME/export/seed/<project>/`` on vista-meta. The remote
``ydb_routines`` is set to that dir at command-build time, so YDB
JIT-compiles staged routines on first reference.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Default location of the connection contract file. Override with
# the ``VISTA_CONN_FILE`` env var (used in tests).
CONN_FILE = Path.home() / "data" / "vista-meta" / "conn.env"


class EngineNotConfigured(RuntimeError):
    """Raised when the vista-meta connection file is missing or malformed."""


@dataclass(frozen=True)
class Connection:
    host: str
    ssh_port: int
    ssh_user: str

    @property
    def target(self) -> str:
        return f"{self.ssh_user}@{self.host}"


def conn_file_path() -> Path:
    return Path(os.environ.get("VISTA_CONN_FILE") or CONN_FILE)


def read_connection(path: Path | None = None) -> Connection:
    """Parse ``conn.env`` into a :class:`Connection`."""
    p = path or conn_file_path()
    if not p.exists():
        raise EngineNotConfigured(
            f"vista-meta connection not configured: {p} missing.\n"
            "Run: cd ~/projects/vista-meta && make run"
        )
    env: dict[str, str] = {}
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    try:
        return Connection(
            host=env["VISTA_HOST"],
            ssh_port=int(env["VISTA_SSH_PORT"]),
            ssh_user=env["VISTA_SSH_USER"],
        )
    except KeyError as missing:
        raise EngineNotConfigured(
            f"missing key {missing} in {p}; "
            "regenerate via vista-meta: make write-conn"
        ) from None


# ── Project root + remote staging ─────────────────────────────────────

_ROOT_MARKERS = ("pyproject.toml", "Makefile", ".git")


def project_root(start: Path) -> Path:
    """Walk up from ``start`` to find the project root.

    Markers (any of): ``pyproject.toml``, ``Makefile``, ``.git``. Falls
    back to the start path's parent if nothing matches — that's a
    degenerate case (loose .m file outside any project), but keeps the
    function total.
    """
    start = start.resolve()
    candidates = [start] if start.is_dir() else [start.parent]
    candidates.extend(p for p in start.parents)
    for p in candidates:
        if any((p / m).exists() for m in _ROOT_MARKERS):
            return p
    return start.parent if start.is_file() else start


def remote_stage(start: Path) -> str:
    """Remote staging dir for the project containing ``start``."""
    return f"$HOME/export/seed/{project_root(start).name}"


# ── Seeding (file upload) ─────────────────────────────────────────────

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


def seed_routines(start: Path, conn: Connection | None = None) -> str:
    """Upload the project's ``.m`` files to vista-meta. Returns the remote stage path.

    Idempotent: clears the remote stage dir first, then uploads. Safe
    to call multiple times. With SSH ControlMaster active, the second
    call reuses the connection and is fast.
    """
    conn = conn or read_connection()
    root = project_root(start)
    stage = f"$HOME/export/seed/{root.name}"
    files = _collect_routines(root)

    _ssh_run(conn, f"mkdir -p {stage} && find {stage} -maxdepth 1 -name '*.m' -delete")
    if files:
        _scp_upload(conn, files, stage)
    return stage


def seed_for_paths(paths: list[Path], conn: Connection | None = None) -> dict[Path, str]:
    """Seed every distinct project containing a path in ``paths``.

    Returns a mapping of project_root -> remote_stage so callers can
    pass the right stage to :func:`build_suite_ssh_cmd`.
    """
    conn = conn or read_connection()
    by_root: dict[Path, str] = {}
    for p in paths:
        root = project_root(p)
        if root in by_root:
            continue
        by_root[root] = seed_routines(p, conn)
    return by_root


# ── SSH command builders ──────────────────────────────────────────────


def build_suite_ssh_cmd(conn: Connection, suite_name: str, stage: str) -> list[str]:
    """Local ``ssh`` argv that runs ``mumps -run ^SUITE`` on vista-meta."""
    routines = f"{stage} $ydb_dist"
    remote = (
        "source /etc/profile.d/ydb_env.sh && "
        f"export ydb_routines={shlex.quote(routines)} && "
        f"exec $ydb_dist/mumps -run ^{suite_name}"
    )
    return _ssh_argv(conn, remote)


def build_xcmd_ssh_cmd(conn: Connection, m_cmd: str, stage: str) -> list[str]:
    """Local ``ssh`` argv that runs an M command via ``mumps -run %XCMD``."""
    routines = f"{stage} $ydb_dist"
    remote = (
        "source /etc/profile.d/ydb_env.sh && "
        f"export ydb_routines={shlex.quote(routines)} && "
        f"exec $ydb_dist/mumps -run %XCMD {shlex.quote(m_cmd)}"
    )
    return _ssh_argv(conn, remote)


def build_direct_ssh_cmd(conn: Connection, stage: str) -> list[str]:
    """Local ``ssh`` argv that runs ``mumps -direct`` (script piped via stdin)."""
    routines = f"{stage} $ydb_dist"
    remote = (
        "source /etc/profile.d/ydb_env.sh && "
        f"export ydb_routines={shlex.quote(routines)} && "
        "exec $ydb_dist/mumps -direct"
    )
    return _ssh_argv(conn, remote)


# ── SSH plumbing ──────────────────────────────────────────────────────

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


def _ssh_argv(conn: Connection, remote_cmd: str) -> list[str]:
    _CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    return [
        "ssh", "-p", str(conn.ssh_port),
        *_BASE_SSH_OPTS,
        conn.target,
        remote_cmd,
    ]


def _ssh_run(conn: Connection, remote_cmd: str) -> None:
    """Run ``remote_cmd`` over SSH; raise on nonzero exit."""
    subprocess.run(_ssh_argv(conn, remote_cmd), check=True)


def _scp_upload(conn: Connection, files: list[Path], remote_dir: str) -> None:
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


__all__ = [
    "Connection",
    "EngineNotConfigured",
    "build_direct_ssh_cmd",
    "build_suite_ssh_cmd",
    "build_xcmd_ssh_cmd",
    "project_root",
    "read_connection",
    "remote_stage",
    "seed_for_paths",
    "seed_routines",
]
