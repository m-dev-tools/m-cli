"""Run a coverage pass over an M project.

YottaDB ships built-in tracing via ``view "TRACE":1:"^GBL":""``;
when enabled, every executed line increments
``^GBL(routine, label, line_offset)`` where the third subscript's
exact meaning is YDB-internal (it's an offset into the label, not a
file-absolute line number). For label-level coverage we only need
"any entry under (routine, label)" → label was hit, which gives us
the same semantics the earlier ZBREAK-based implementation had.

Line-level coverage with absolute file-line numbers requires
mapping YDB's offset back via the parser; that's deferred until the
offset semantics are settled. The line data we *do* return today is
the parser's executable-line list with hit counts attributed at
the label level — useful for "which labels never ran" but not yet
for "which line on disk never ran."

The pipeline:

  1. Discover non-suite (production) routines via
     ``discover_routines_and_suites``.
  2. Build a YottaDB direct-mode script that enables tracing into
     ``^ycov``, runs every selected suite, disables tracing, and
     ``ZWRITE``s the global. Subprocess is injectable for tests.
  3. Parse the ZWRITE dump into a set of (routine, label) pairs
     whose entries appeared — those are the covered labels.
"""

from __future__ import annotations

import re
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
    """One discovered label and whether it was hit during the run.

    A label is "covered" iff any of its executable lines was executed
    at least once during the trace pass. That's the same semantics the
    earlier ZBREAK-based implementation had — both shapes yield the
    same answer for normal labels (entry instruction is a label's
    first executable line)."""

    routine: str
    label: str
    path: Path
    line: int
    covered: bool


@dataclass(frozen=True)
class LineCoverage:
    """One executable line of M source and how many times it ran."""

    routine: str  # uppercased canonical (matches LabelLocation.routine)
    label: str  # the label this line is inside (declaration name, case-preserved)
    path: Path
    line: int  # 1-indexed absolute line number in the file
    hit_count: int  # 0 if discovered but not executed


@dataclass(frozen=True)
class CoverageResult:
    """Aggregate result of a coverage run.

    Carries both label-level (back-compat) and line-level data. The
    label-level summary is derived from the line-level data — there's
    a single source of truth from the YDB trace global.
    """

    labels: list[LabelCoverage]
    lines: list[LineCoverage]
    suites_run: list[str]
    returncode: int
    stdout: str
    by_routine: dict[str, tuple[int, int]] = field(default_factory=dict)
    # by_routine[routine] = (covered_count, total_count)  — label-level

    @property
    def total(self) -> int:
        return len(self.labels)

    @property
    def covered(self) -> int:
        return sum(1 for label in self.labels if label.covered)

    @property
    def percent(self) -> float:
        return 100.0 * self.covered / self.total if self.total else 0.0

    @property
    def total_lines(self) -> int:
        return len(self.lines)

    @property
    def covered_lines(self) -> int:
        return sum(1 for line in self.lines if line.hit_count > 0)

    @property
    def line_percent(self) -> float:
        return 100.0 * self.covered_lines / self.total_lines if self.total_lines else 0.0


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

    executable, label_locs = _discover_executables(routine_paths)
    if not executable and not label_locs:
        return CoverageResult(
            labels=[],
            lines=[],
            suites_run=[s.name for s in selected_suites],
            returncode=0,
            stdout="",
        )

    script = _build_script(selected_suites)
    cmd = [_ydb_path(), "-direct"]
    runner = runner or _default_runner

    # Compose env. Reuse `_build_env` from the test runner so suite +
    # routines paths line up the same way `m test` does — the user has
    # one mental model for "where does ydb find the .m files."
    env_seed = selected_suites[0].path if selected_suites else routine_paths[0]
    full_env = _build_env(env_seed, env)
    stdout, rc = runner(cmd, script, full_env)

    covered_labels = _parse_covered_labels(stdout)

    # LineCoverage attributes hits at the label granularity: every
    # executable line in a covered label is reported as hit_count=1;
    # uncovered labels report 0. Once YDB's TRACE offset semantics are
    # decoded, this can be tightened to actual per-line counts without
    # an API change.
    lines = [
        LineCoverage(
            routine=ex.routine,
            label=ex.label,
            path=ex.path,
            line=ex.line,
            hit_count=1
            if (ex.routine.upper(), ex.label.upper()) in covered_labels
            else 0,
        )
        for ex in executable
    ]

    # Label coverage: a label is covered iff its (routine, label) pair
    # appeared in the trace dump.
    label_cov = [
        LabelCoverage(
            routine=loc.routine,
            label=loc.label,
            path=loc.path,
            line=loc.line,
            covered=(loc.routine.upper(), loc.label.upper()) in covered_labels,
        )
        for loc in label_locs
    ]
    by_routine: dict[str, tuple[int, int]] = {}
    for lab in label_cov:
        cov, total = by_routine.get(lab.routine, (0, 0))
        by_routine[lab.routine] = (cov + (1 if lab.covered else 0), total + 1)
    return CoverageResult(
        labels=label_cov,
        lines=lines,
        suites_run=[s.name for s in selected_suites],
        returncode=rc,
        stdout=stdout,
        by_routine=by_routine,
    )


@dataclass(frozen=True)
class _ExecutableLine:
    """Internal: one line that the parser thinks is executable."""

    routine: str  # upper-case canonical
    label: str  # owning label (case-preserved as declared)
    path: Path
    line: int  # 1-indexed absolute line


def _discover_executables(
    routine_paths: list[Path],
) -> tuple[list[_ExecutableLine], list[LabelLocation]]:
    """Walk every production routine and return (executable lines,
    non-routine-entry labels).

    A line is "executable" iff its ``line`` AST node carries a
    ``command_sequence`` child. Comment-only lines and label-only
    lines are excluded — YDB's TRACE wouldn't emit hit counts for
    them either, so their absence wouldn't tell us "uncovered."
    """
    idx = WorkspaceIndex()
    for path in routine_paths:
        try:
            idx.add_file(path, path.read_bytes())
        except OSError:
            continue

    label_locs: list[LabelLocation] = []
    for loc in idx.all_locations():
        if loc.label.upper() == loc.routine.upper():
            # Routine-entry label — skip from the label-coverage denominator
            # (matches the original ycover convention).
            continue
        label_locs.append(loc)

    executable: list[_ExecutableLine] = []
    # Group label_locs by path so we can map every line in a file to
    # its owning label in one pass.
    paths_seen: set[Path] = set()
    for path in routine_paths:
        resolved = path.resolve()
        if resolved in paths_seen:
            continue
        paths_seen.add(resolved)
        try:
            src = path.read_bytes()
        except OSError:
            continue
        executable.extend(_executable_lines_for_file(path, src))
    return executable, label_locs


def _executable_lines_for_file(path: Path, src: bytes) -> list[_ExecutableLine]:
    """Return one _ExecutableLine per executable line in the file.

    Pre-order walk over top-level ``line`` nodes. Each line carries
    its owning label — the most recent label declaration seen — so
    label-coverage aggregation works without a second pass.
    """
    from m_cli.parser import parse

    tree = parse(src)
    routine = path.stem.upper()
    out: list[_ExecutableLine] = []
    current_label: str | None = None
    for line_node in tree.root_node.children:
        if line_node.type != "line":
            continue
        # Update current_label if this line has a label declaration.
        for child in line_node.children:
            if child.type == "label":
                current_label = src[child.start_byte : child.end_byte].decode(
                    "latin-1", errors="replace"
                )
                break
        if current_label is None:
            # Lines before the first label can't be addressed by ydb anyway.
            continue
        # Executable iff the line has a command_sequence child.
        if any(c.type == "command_sequence" for c in line_node.children):
            out.append(
                _ExecutableLine(
                    routine=routine,
                    label=current_label,
                    path=path,
                    line=line_node.start_point[0] + 1,
                )
            )
    return out


def _build_script(suites: list[TestSuite]) -> str:
    """Compose the ydb-direct script: kill ^ycov, enable line trace,
    do every suite, disable trace, ZWRITE ^ycov, halt.

    YDB's ``view "TRACE":N:"^GBL":""`` enables (N=1) or disables
    (N=0) per-line tracing into ``^GBL``. While enabled, every
    executed line increments ``^GBL(routine, label, absLine)``."""
    lines = ["kill ^ycov", 'view "TRACE":1:"^ycov":""']
    for s in suites:
        lines.append(f"do ^{s.name}")
    lines.append('view "TRACE":0:"^ycov":""')
    lines.append("zwrite ^ycov")
    lines.append("halt")
    return "\n".join(lines) + "\n"


# Per-line trace entry: ``^ycov("routine","LABEL",N)="hit:..."``.
# The third subscript ``N`` is a YDB-internal label offset; we
# don't decode it here — any entry means the label was hit.
_TRACE_LINE_RE = re.compile(r'^\^ycov\("([^"]+)","([^"]+)",\d+\)="(\d+):')


def _parse_covered_labels(stdout: str) -> set[tuple[str, str]]:
    """Parse ``^ycov(...)`` lines into a set of upper-cased
    ``(routine, label)`` pairs that appeared in the trace.

    The ZWRITE format puts the value after ``=``. Per-line entries
    look like ``^ycov("test","TEST",2)="1:0:1:1:1"`` (hit count > 0
    in the first colon-separated field). Summary records like
    ``^ycov("*RUN")="..."`` and ``^ycov("test","TEST")="..."`` (the
    label entry total, no third subscript) are ignored — we only
    care about the per-line entries since they're proof the label
    body executed.
    """
    out: set[tuple[str, str]] = set()
    for raw in stdout.splitlines():
        m = _TRACE_LINE_RE.match(raw.strip())
        if not m:
            continue
        try:
            count = int(m.group(3))
        except ValueError:
            continue
        if count > 0:
            out.add((m.group(1).upper(), m.group(2).upper()))
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
    "LineCoverage",
    "RunnerFn",
    "discover_routines_and_suites",
    "run_coverage",
]
