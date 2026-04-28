"""Run a coverage pass over an M project.

The pipeline:

  1. Discover non-suite (production) routines and their labels via
     ``m_cli.workspace.WorkspaceIndex``. The routine-entry label
     (whose name equals the routine name, case-insensitive) is
     excluded — it's the file's load-on-do entry, not a callable.
  2. Discover test suites via ``m_cli.test.discovery.discover``.
  3. Build a YottaDB direct-mode script that sets one ``ZBREAK`` per
     production label (writing to ``^ycov``) and then ``do^suite`` for
     each test suite.
  4. Run ``ydb -direct`` with the script piped on stdin, env composed
     from the suites' parent directory layout.
  5. Parse ``^ycov`` lines from stdout; everything in the discovered
     label set that isn't in ``^ycov`` is uncovered.

The subprocess is injectable (``RunnerFn``) so unit tests don't need
a live ydb.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from m_cli.test.discovery import TestSuite, is_suite_file
from m_cli.test.runner import _build_env, _ydb_path
from m_cli.workspace import LabelLocation, WorkspaceIndex

# (cmd, stdin_text, env) -> (stdout, returncode)
RunnerFn = Callable[[list[str], str, "dict[str, str] | None"], "tuple[str, int]"]


@dataclass(frozen=True)
class LabelCoverage:
    """One discovered label and whether it was hit during the run."""

    routine: str
    label: str
    path: Path
    line: int
    covered: bool


@dataclass(frozen=True)
class CoverageResult:
    """Aggregate result of a coverage run."""

    labels: list[LabelCoverage]
    suites_run: list[str]
    returncode: int
    stdout: str
    by_routine: dict[str, tuple[int, int]] = field(default_factory=dict)
    # by_routine[routine] = (covered_count, total_count)

    @property
    def total(self) -> int:
        return len(self.labels)

    @property
    def covered(self) -> int:
        return sum(1 for label in self.labels if label.covered)

    @property
    def percent(self) -> float:
        return 100.0 * self.covered / self.total if self.total else 0.0


def discover_routines_and_suites(
    paths: list[Path],
) -> tuple[list[Path], list[TestSuite]]:
    """Split a set of input paths into (production routines, test suites).

    A path may be a file or directory. Directories are walked
    recursively for ``*.m`` files. Files whose stem matches the
    ``[A-Z][A-Z0-9]*TST`` suite convention are routed to suites; the
    canonical TESTRUN library file is also classified as a suite (it
    isn't a test itself but it isn't production code either —
    excluding it from coverage matches m-tools' convention).
    """
    from m_cli.test.discovery import discover

    seen: set[Path] = set()
    routine_paths: list[Path] = []
    suite_inputs: list[Path] = []
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*.m")):
                _classify(f, seen, routine_paths, suite_inputs)
        elif p.is_file():
            _classify(p, seen, routine_paths, suite_inputs)
    suites = discover(suite_inputs) if suite_inputs else []
    return routine_paths, suites


def _classify(
    path: Path, seen: set[Path], routines: list[Path], suite_inputs: list[Path]
) -> None:
    resolved = path.resolve()
    if resolved in seen:
        return
    seen.add(resolved)
    if is_suite_file(path) or path.stem.upper() == "TESTRUN":
        suite_inputs.append(path)
    else:
        routines.append(path)


def run_coverage(
    routine_paths: list[Path],
    suites: list[TestSuite],
    *,
    runner: RunnerFn | None = None,
    env: dict[str, str] | None = None,
    suite_filter: list[str] | None = None,
) -> CoverageResult:
    """Run coverage over ``routine_paths`` driven by ``suites``.

    ``suite_filter``, when given, restricts execution to suites whose
    name is in the list — useful for ``m coverage --suites X,Y``.
    """
    selected_suites = (
        [s for s in suites if s.name in suite_filter] if suite_filter else list(suites)
    )

    targets = _discover_targets(routine_paths)
    if not targets:
        return CoverageResult(
            labels=[],
            suites_run=[s.name for s in selected_suites],
            returncode=0,
            stdout="",
        )

    script = _build_script(targets, selected_suites)
    cmd = [_ydb_path(), "-direct"]
    runner = runner or _default_runner

    # Compose env. Reuse `_build_env` from the test runner so suite +
    # routines paths line up the same way `m test` does — the user has
    # one mental model for "where does ydb find the .m files."
    env_seed = selected_suites[0].path if selected_suites else routine_paths[0]
    full_env = _build_env(env_seed, env)
    stdout, rc = runner(cmd, script, full_env)

    covered_set = _parse_covered(stdout)
    labels = [
        LabelCoverage(
            routine=t.routine,
            label=t.label,
            path=t.path,
            line=t.line,
            covered=(t.routine.upper(), t.label.upper()) in covered_set,
        )
        for t in targets
    ]
    by_routine: dict[str, tuple[int, int]] = {}
    for lab in labels:
        cov, total = by_routine.get(lab.routine, (0, 0))
        by_routine[lab.routine] = (cov + (1 if lab.covered else 0), total + 1)
    return CoverageResult(
        labels=labels,
        suites_run=[s.name for s in selected_suites],
        returncode=rc,
        stdout=stdout,
        by_routine=by_routine,
    )


def _discover_targets(routine_paths: list[Path]) -> list[LabelLocation]:
    """Index every production routine, drop the routine-entry label."""
    idx = WorkspaceIndex()
    for path in routine_paths:
        try:
            idx.add_file(path, path.read_bytes())
        except OSError:
            continue
    out: list[LabelLocation] = []
    for loc in idx.all_locations():
        # Skip the top-of-file routine-entry label — it's the file's
        # load-on-do entry, never targeted by a labelled call.
        if loc.label.upper() == loc.routine.upper():
            continue
        out.append(loc)
    return out


def _build_script(targets: list[LabelLocation], suites: list[TestSuite]) -> str:
    """Compose the ydb-direct script: kill ^ycov, ZBREAK every target,
    do every suite, ZWRITE ^ycov, halt."""
    lines = ["kill ^ycov"]
    for t in targets:
        # ydb's routine resolution is case-sensitive on Linux, so the
        # ZBREAK target must match the actual filename's case (e.g.
        # `csv.m` not `CSV.m`). LabelLocation.routine upper-cases for
        # case-insensitive lookup; we recover the filename case from
        # the path.stem here. The ^ycov key uses the same case so
        # _parse_covered's case-insensitive match still aligns.
        #
        # Inner double-quotes are doubled per M string-literal
        # convention; without that doubling ydb parses the ZBREAK
        # action string and silently drops it.
        routine_name = t.path.stem
        action = f'set ^ycov(""{routine_name}"",""{t.label}"")=1'
        lines.append(f'zbreak {t.label}^{routine_name}:"{action}"')
    for s in suites:
        lines.append(f"do ^{s.name}")
    lines.append("zwrite ^ycov")
    lines.append("halt")
    return "\n".join(lines) + "\n"


def _parse_covered(stdout: str) -> set[tuple[str, str]]:
    """Parse ``^ycov("ROUTINE","LABEL")=1`` lines from stdout into a set
    of upper-cased (routine, label) pairs."""
    out: set[tuple[str, str]] = set()
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line.startswith("^ycov("):
            continue
        # ^ycov("R","L")=...
        try:
            inner = line.split("(", 1)[1].rsplit(")", 1)[0]
            parts = [p.strip().strip('"') for p in inner.split(",", 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                out.add((parts[0].upper(), parts[1].upper()))
        except (IndexError, ValueError):
            continue
    return out


def _default_runner(
    cmd: list[str], stdin_text: str, env: dict[str, str] | None
) -> tuple[str, int]:
    """Run ``cmd`` with ``stdin_text`` piped in. Stderr folded into stdout."""
    proc = subprocess.run(
        cmd,
        input=stdin_text.encode("latin-1", errors="replace"),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.stdout.decode("latin-1", errors="replace"), proc.returncode


__all__ = [
    "CoverageResult",
    "LabelCoverage",
    "RunnerFn",
    "discover_routines_and_suites",
    "run_coverage",
]
