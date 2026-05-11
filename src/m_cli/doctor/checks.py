"""Environment-health checks for ``m doctor``.

Two paths share this surface:

1. **Docker engine path** (canonical for m-cli users without local
   YottaDB) — driven by the vendored manifest in
   ``dist/m-test-engine.json`` (see ``m_cli.engine_manifest``). Probes
   live in :mod:`m_cli.doctor._runtime`; checks declare prerequisites
   so downstream checks emit ``SKIPPED`` instead of redundant ``WARN``
   when an upstream cause has already been reported.

2. **Local YottaDB path** (alternative, for hosts with a system-level
   YDB install) — the original five checks. These do **not** declare
   prerequisites because each handles its own missing-input case
   gracefully (e.g. ``check_ydb_binary`` falls back to ``$PATH`` when
   ``$ydb_dist`` is unset).

Each ``check_*`` function is independent. Prerequisite handling lives
in :func:`run_all_checks`.
"""

from __future__ import annotations

import enum
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from m_cli.doctor import _runtime
from m_cli.engine_manifest import EngineManifest, load_engine_manifest


class Status(enum.Enum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class Fix:
    """A copy-pasteable fix command derived from manifest data.

    ``engine_verb`` (Phase 2.4) declares which ``m engine <verb>``
    method applies the fix. When set, ``m doctor --fix`` invokes the
    driver method directly (no shell-out). When ``None``, the fix is
    outside the engine namespace (e.g. ``sudo systemctl start
    docker``) and ``--fix`` only prints a "manual:" hint.

    Keep this distinction tight: the engine-verb path bounds the
    security surface of ``--fix`` to operations the driver already
    owns; non-engine fixes never auto-run, no matter how
    non-destructive they look.
    """

    command: tuple[str, ...]
    destructive: bool = False
    engine_verb: str | None = None


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    message: str
    hint: str | None = None
    prerequisites: tuple[str, ...] = field(default_factory=tuple)
    fix: Fix | None = None


# ── Local YDB path (legacy, unchanged behaviour) ─────────────────────


def check_ydb_dist() -> Check:
    """Check ``$ydb_dist`` env var: set, exists, contains a ``ydb`` binary."""
    val = os.environ.get("ydb_dist")
    if not val:
        return Check(
            name="ydb_dist",
            status=Status.WARN,
            message="not set",
            hint=(
                "Source your YottaDB env script (e.g. "
                "`source $ydb_dist/ydb_env_set`) or export "
                "`ydb_dist=/usr/local/lib/yottadb/r2.07`."
            ),
        )
    path = Path(val)
    if not path.exists():
        return Check(
            name="ydb_dist",
            status=Status.FAIL,
            message=f"missing directory: {val}",
            hint="Set $ydb_dist to a real YottaDB install directory.",
        )
    if not path.is_dir():
        return Check(
            name="ydb_dist",
            status=Status.FAIL,
            message=f"not a directory: {val}",
            hint="$ydb_dist must point at the YottaDB install directory.",
        )
    binary = path / "ydb"
    if not binary.exists():
        return Check(
            name="ydb_dist",
            status=Status.WARN,
            message=f"directory ok but no `ydb` binary inside ({val})",
            hint=(
                "Reinstall YottaDB or check the directory layout — the "
                "expected binary is `$ydb_dist/ydb`."
            ),
        )
    return Check(name="ydb_dist", status=Status.OK, message=val)


def check_ydb_routines() -> Check:
    """Check ``$ydb_routines`` is set (the routine search path)."""
    val = os.environ.get("ydb_routines")
    if not val:
        return Check(
            name="ydb_routines",
            status=Status.WARN,
            message="not set",
            hint=(
                "Export `ydb_routines` to your routine search path, "
                "typically containing your project's `routines/` and "
                "`$ydb_dist/libyottadbutil.so`."
            ),
        )
    return Check(name="ydb_routines", status=Status.OK, message=val)


def check_parser() -> Check:
    """Confirm tree-sitter-m parses a trivial routine."""
    try:
        from m_cli.parser import parse

        tree = parse(b"HELLO ;test\n Q\n")
        if tree.root_node is None:
            return Check(
                name="parser",
                status=Status.FAIL,
                message="parser returned no root node",
                hint="Reinstall tree-sitter-m: pip install -e ../tree-sitter-m",
            )
        return Check(
            name="parser",
            status=Status.OK,
            message="tree-sitter-m loaded",
        )
    except Exception as exc:  # pragma: no cover - import-error path
        return Check(
            name="parser",
            status=Status.FAIL,
            message=f"failed to parse: {exc.__class__.__name__}: {exc}",
            hint="Reinstall tree-sitter-m and verify the .so is present.",
        )


def check_keywords() -> Check:
    """Confirm m-standard keyword TSVs load."""
    try:
        from m_cli.lint._keywords import keyword_records

        records = keyword_records()
        n = len(records)
        if n == 0:
            return Check(
                name="keywords",
                status=Status.FAIL,
                message="m-standard returned 0 keyword records",
                hint="Check m-standard install — TSVs may be missing.",
            )
        return Check(
            name="keywords",
            status=Status.OK,
            message=f"{n} M language keywords loaded from m-standard",
        )
    except Exception as exc:  # pragma: no cover - import-error path
        return Check(
            name="keywords",
            status=Status.FAIL,
            message=f"keyword loader raised {exc.__class__.__name__}: {exc}",
            hint="Reinstall m-standard or verify its TSVs are reachable.",
        )


def check_ydb_binary() -> Check:
    """Locate the ``ydb`` binary via ``$YDB``, ``$ydb_dist/ydb``, or PATH."""
    explicit = os.environ.get("YDB")
    if explicit:
        path = Path(explicit)
        if path.exists() and os.access(path, os.X_OK):
            return Check(
                name="ydb_binary",
                status=Status.OK,
                message=f"$YDB → {path}",
            )
        return Check(
            name="ydb_binary",
            status=Status.FAIL,
            message=f"$YDB points at non-executable path: {explicit}",
            hint="Unset $YDB or fix it to point at a real ydb binary.",
        )
    dist = os.environ.get("ydb_dist")
    if dist:
        candidate = Path(dist) / "ydb"
        if candidate.exists() and os.access(candidate, os.X_OK):
            return Check(
                name="ydb_binary",
                status=Status.OK,
                message=f"$ydb_dist/ydb → {candidate}",
            )
    on_path = shutil.which("ydb")
    if on_path:
        return Check(
            name="ydb_binary",
            status=Status.OK,
            message=f"PATH → {on_path}",
        )
    return Check(
        name="ydb_binary",
        status=Status.WARN,
        message="no `ydb` binary found",
        hint=(
            "Install YottaDB or set $YDB to the binary path. "
            "`m test` and `m coverage` need a working ydb to run suites."
        ),
    )


# ── Docker engine path (canonical for m-cli users) ───────────────────


def _manifest() -> EngineManifest | None:
    """Best-effort manifest load — None if vendoring hasn't happened."""
    try:
        return load_engine_manifest()
    except (FileNotFoundError, ValueError, KeyError):
        return None


def check_docker_installed() -> Check:
    """Top of the Docker chain: is the ``docker`` CLI on ``$PATH``?"""
    if _runtime.docker_available():
        return Check(
            name="docker_installed",
            status=Status.OK,
            message="docker CLI on PATH",
        )
    return Check(
        name="docker_installed",
        status=Status.WARN,
        message="docker CLI not found on PATH",
        hint=(
            "Install Docker Engine (linux) or Docker Desktop (mac/win). "
            "See https://docs.docker.com/engine/install/ for distro-"
            "specific instructions."
        ),
    )


def check_docker_daemon() -> Check:
    """``docker info`` succeeds — the daemon is up and the user can reach it."""
    if _runtime.docker_daemon_reachable():
        return Check(
            name="docker_daemon",
            status=Status.OK,
            message="docker daemon reachable",
            prerequisites=("docker_installed",),
        )
    return Check(
        name="docker_daemon",
        status=Status.WARN,
        message="docker daemon not reachable",
        hint=(
            "Start the daemon: `sudo systemctl start docker` (linux) or "
            "launch Docker Desktop (mac/win). Also verify your user is in "
            "the `docker` group: `groups | grep docker`."
        ),
        prerequisites=("docker_installed",),
        fix=Fix(
            command=("sudo", "systemctl", "start", "docker"),
            destructive=False,
        ),
    )


def check_engine_image() -> Check:
    """The canonical m-test-engine image is pulled locally."""
    m = _manifest()
    if m is None:
        return Check(
            name="engine_image",
            status=Status.WARN,
            message="manifest dist/m-test-engine.json not loadable",
            hint=(
                "Re-vendor the engine contract: "
                "`make manifest M_TEST_ENGINE=/path/to/m-test-engine`."
            ),
            prerequisites=("docker_installed", "docker_daemon"),
        )
    ref = m.image_ref()
    if _runtime.docker_image_present(ref):
        return Check(
            name="engine_image",
            status=Status.OK,
            message=f"image {ref} present",
            prerequisites=("docker_installed", "docker_daemon"),
        )
    return Check(
        name="engine_image",
        status=Status.WARN,
        message=f"image {ref} not pulled",
        hint=f"Pull the canonical engine image: `docker pull {ref}`.",
        prerequisites=("docker_installed", "docker_daemon"),
        fix=Fix(
            command=("docker", "pull", ref),
            destructive=False,
            engine_verb="install",
        ),
    )


def check_engine_container() -> Check:
    """The canonical m-test-engine container is running."""
    m = _manifest()
    if m is None:
        return Check(
            name="engine_container",
            status=Status.WARN,
            message="manifest dist/m-test-engine.json not loadable",
            hint="See engine_image hint.",
            prerequisites=("docker_installed", "docker_daemon"),
        )
    if _runtime.docker_container_running(m.container):
        return Check(
            name="engine_container",
            status=Status.OK,
            message=f"container `{m.container}` running",
            prerequisites=("docker_installed", "docker_daemon"),
        )
    return Check(
        name="engine_container",
        status=Status.WARN,
        message=f"container `{m.container}` not running",
        hint=(
            f"Start it from the m-test-engine checkout: `docker compose -f {m.compose_file} up -d`."
        ),
        prerequisites=("docker_installed", "docker_daemon"),
        fix=Fix(
            command=("docker", "compose", "-f", m.compose_file, "up", "-d"),
            destructive=False,
            engine_verb="start",
        ),
    )


def check_engine_bind_mount() -> Check:
    """Host bind-mount directory exists.

    Independent of the rest of the Docker chain — the user can create
    the bind-mount directory before docker is installed (and should).
    """
    m = _manifest()
    if m is None:
        return Check(
            name="engine_bind_mount",
            status=Status.WARN,
            message="manifest dist/m-test-engine.json not loadable",
            hint="See engine_image hint.",
        )
    host = m.bind_mount.host
    if _runtime.path_exists(host):
        return Check(
            name="engine_bind_mount",
            status=Status.OK,
            message=f"host {host} exists",
        )
    return Check(
        name="engine_bind_mount",
        status=Status.WARN,
        message=f"host {host} does not exist",
        hint=(
            f"Create the shared m-* working dir: "
            f"`sudo install -d -o $USER -g $USER {host}` then "
            f"`cd {host} && git clone <repo>` for each m-* repo you "
            "want available inside the engine."
        ),
        fix=Fix(
            command=("sudo", "install", "-d", "-o", "$USER", "-g", "$USER", host),
            destructive=False,
        ),
    )


# ── Registry + dependency-aware runner ───────────────────────────────


_CHECKS: tuple[Callable[[], Check], ...] = (
    # Docker engine path first — canonical runtime
    check_docker_installed,
    check_docker_daemon,
    check_engine_image,
    check_engine_container,
    check_engine_bind_mount,
    # Local YDB path second — alternative runtime
    check_ydb_dist,
    check_ydb_routines,
    check_parser,
    check_keywords,
    check_ydb_binary,
)


def _skip_for(prereq_name: str) -> Check:
    """SKIPPED placeholder check pointing at the failed prerequisite."""
    return Check(
        name="",  # caller fills this in
        status=Status.SKIPPED,
        message=f"skipped — waiting on {prereq_name}",
    )


def run_all_checks() -> list[Check]:
    """Run every registered check, honouring prerequisite chains.

    A check is SKIPPED (not run) when any of its declared prerequisites
    landed in a non-OK status. This implements the root-cause grouping
    pattern: one warning per cause instead of N warnings per N
    downstream effects.

    Local YDB checks declare no prerequisites and behave exactly as
    before. Only the Docker chain participates in the SKIPPED grouping.
    """
    results: dict[str, Check] = {}
    for fn in _CHECKS:
        # Peek at the function's first-pass output to discover its
        # declared prerequisites and its own name. (The check function
        # is the source of truth — registry has no separate metadata.)
        provisional = fn()
        prereqs = provisional.prerequisites
        blockers = [p for p in prereqs if p in results and results[p].status is not Status.OK]
        if blockers:
            # One pointer is enough — the user follows the chain up.
            skipped = Check(
                name=provisional.name,
                status=Status.SKIPPED,
                message=f"skipped — waiting on {blockers[0]}",
                prerequisites=prereqs,
            )
            results[provisional.name] = skipped
        else:
            results[provisional.name] = provisional
    return list(results.values())
