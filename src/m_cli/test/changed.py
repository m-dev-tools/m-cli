"""Resolve which test suites to re-run based on git-changed files.

``m test --changed`` is a TDD-loop accelerator: only run the suites
whose adjacent source has been modified relative to git. Source-side
changes (``foo.m``) map to ``FOOTST.m`` via the same affinity rule
``m watch`` uses; suite-side changes (``FOOTST.m``) map to themselves;
deletions are dropped because there's nothing to test against.

The git invocation is wrapped behind a ``GitRunner`` callable so unit
tests can stub it without needing a real repo. The default runner
shells out to ``git status --porcelain`` (or ``git diff --name-only
<base>`` when a base revision is requested).
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from m_cli.test.discovery import TestSuite

GitRunner = Callable[[list[str], Path], "tuple[str, int]"]


def find_changed_m_files(
    cwd: Path,
    *,
    base: str | None = None,
    runner: GitRunner | None = None,
) -> list[Path]:
    """Return absolute paths to ``.m`` files git considers modified.

    Without ``base``: working-tree + index + untracked, via
    ``git status --porcelain``. With ``base``: changed files since
    that revision, via ``git diff --name-only --diff-filter=ACMR``.

    Files that no longer exist on disk (e.g. deleted) are dropped —
    we can't test what's not there. A non-zero git exit (e.g. not a
    repo) returns an empty list rather than raising; the caller can
    decide how to surface that to the user.
    """
    runner = runner or _default_runner
    if base:
        cmd = ["git", "diff", "--name-only", "--diff-filter=ACMR", base]
    else:
        cmd = ["git", "status", "--porcelain"]
    out, rc = runner(cmd, cwd)
    if rc != 0:
        return []
    candidates: list[Path] = []
    for line in out.splitlines():
        rel = _parse_porcelain_path(line) if not base else line.strip()
        if not rel:
            continue
        if not rel.endswith(".m"):
            continue
        candidate = (cwd / rel).resolve()
        if candidate.exists():
            candidates.append(candidate)
    # De-dup while preserving first-seen order.
    seen: set[Path] = set()
    out_paths: list[Path] = []
    for p in candidates:
        if p in seen:
            continue
        seen.add(p)
        out_paths.append(p)
    return out_paths


def changed_to_suites(
    changed: list[Path], suites: list[TestSuite]
) -> list[TestSuite]:
    """Resolve a set of changed paths to the suites that should run.

    Each changed path is fed through ``resolve_affinity``; the union
    is returned with duplicates removed and stable order preserved.
    Returns an empty list when ``changed`` is empty.
    """
    if not changed:
        return []
    # Local import to avoid triggering m_cli.watch package init at
    # module load — m_cli.watch.cli imports back into m_cli.test.cli.
    from m_cli.watch.affinity import resolve_affinity

    seen: set[str] = set()
    out: list[TestSuite] = []
    for path in changed:
        for suite in resolve_affinity(path, suites):
            if suite.name in seen:
                continue
            seen.add(suite.name)
            out.append(suite)
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_porcelain_path(line: str) -> str | None:
    """Extract the file path from one ``git status --porcelain`` line.

    Format: ``XY filename`` where ``X`` and ``Y`` are status codes.
    Renames are reported as ``XY old -> new``; we keep ``new`` since
    that's the file on disk. Deletions (``D`` in either column) are
    skipped — there's nothing to test against a missing file.
    """
    if len(line) < 4:
        return None
    x, y = line[0], line[1]
    if "D" in (x, y):
        return None
    rest = line[3:]
    if " -> " in rest:
        rest = rest.split(" -> ", 1)[1]
    return rest.strip() or None


def _default_runner(cmd: list[str], cwd: Path) -> tuple[str, int]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.stdout.decode("utf-8", errors="replace"), proc.returncode


__all__ = [
    "GitRunner",
    "changed_to_suites",
    "find_changed_m_files",
]
