"""Run a coverage pass over an M project.

YottaDB ships built-in tracing via ``view "TRACE":1:"^GBL":""``;
when enabled, every executed line increments
``^GBL(routine, LABEL, offset)`` where ``offset`` is the line offset
*from the owning label's declaration line*. So a comment on the
line directly below the label is offset 1, the next line is offset
2, and so on — and comment-only or label-only lines never produce
trace entries because they aren't executable.

To map back to file-absolute lines: for each trace entry
``^ycov(routine, LABEL, N)``, find ``LABEL``'s declaration line
``L`` from the parser, and the absolute line is ``L + N``. The
parser-identified executable lines (any tree-sitter ``line`` node
with a ``command_sequence`` child) are the denominator; trace
entries with hit_count > 0 are the numerator.

The pipeline:

  1. Discover non-suite (production) routines via
     ``discover_routines_and_suites``.
  2. Walk each routine to enumerate executable lines, tracking
     each line's owning label and the label's declaration line so
     we can compute the offset YDB will report.
  3. Build a direct-mode script that toggles trace, runs every
     selected suite, and ``ZWRITE``s ``^ycov``.
  4. Parse the dump into ``{(routine_upper, label_upper, offset):
     hit_count}`` and join with the executable list.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from m_cli.coverage.branches import (
    BranchCoverage,
    extract_branch_points,
    join_branch_coverage,
)
from m_cli.engine import (
    Engine,
    build_direct_ssh_cmd,
    detect_engine,
)
from m_cli.test.discovery import TestSuite, is_suite_file
from m_cli.workspace import LabelLocation, WorkspaceIndex

# (cmd, stdin_text, env) -> (stdout, returncode). ``env`` retained for
# signature stability but unused (env is set inside the remote shell).
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

    Carries label-level and line-level data, and — when the caller
    opts in via ``with_branches=True`` — branch-level data. Default is
    ``branches=None`` so existing call sites keep their payload shape.
    """

    labels: list[LabelCoverage]
    lines: list[LineCoverage]
    suites_run: list[str]
    returncode: int
    stdout: str
    by_routine: dict[str, tuple[int, int]] = field(default_factory=dict)
    # by_routine[routine] = (covered_count, total_count)  — label-level
    branches: list[BranchCoverage] | None = None

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

    @property
    def total_branches(self) -> int:
        return len(self.branches) if self.branches else 0

    @property
    def reached_branches(self) -> int:
        return sum(1 for bc in self.branches or [] if bc.reached)

    @property
    def branch_percent(self) -> float:
        return (
            100.0 * self.reached_branches / self.total_branches
            if self.total_branches
            else 0.0
        )


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
    conn: Engine | None = None,
    suite_filter: list[str] | None = None,
    with_branches: bool = False,
) -> CoverageResult:
    """Run coverage over ``routine_paths`` driven by ``suites``.

    ``suite_filter``, when given, restricts execution to suites whose
    name is in the list — useful for ``m coverage --suites X,Y``.

    ``with_branches`` opts into branch-coverage extraction. When set,
    the returned ``CoverageResult.branches`` is a list of
    ``BranchCoverage`` records, one per static branch point in the
    production routines. When unset, ``branches`` stays ``None`` so
    existing payloads don't change.
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
            branches=[] if with_branches else None,
        )

    script = _build_script(selected_suites)
    runner = runner or _default_runner

    # Build the SSH cmd targeting vista-meta. The remote stage dir is
    # derived from the project root of the first suite (or first
    # routine, if no suites) — every project's .m files share one
    # stage dir so a single ydb_routines value works for all.
    seed = selected_suites[0].path if selected_suites else routine_paths[0]
    conn = conn or detect_engine()
    stage = conn.stage_path(seed)
    cmd = build_direct_ssh_cmd(conn, stage)
    stdout, rc = runner(cmd, script, None)

    hit_lines = _parse_line_hits(stdout)

    # Compute per-line hit counts by mapping each parser-identified
    # executable line to its trace key (routine_upper, label_upper,
    # offset = line - label_line) and looking up the count.
    lines = [
        LineCoverage(
            routine=ex.routine,
            label=ex.label,
            path=ex.path,
            line=ex.line,
            hit_count=hit_lines.get(
                (ex.routine.upper(), ex.label.upper(), ex.trace_offset),
                0,
            ),
        )
        for ex in executable
    ]

    # Label coverage: a label is covered iff any of its executable
    # lines has hit_count > 0. Derived from the line-level data so
    # there's a single source of truth.
    covered_labels: set[tuple[str, str]] = {
        (ln.routine.upper(), ln.label.upper())
        for ln in lines
        if ln.hit_count > 0
    }
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

    branches: list[BranchCoverage] | None = None
    if with_branches:
        branches = _collect_branches(routine_paths, label_locs, hit_lines)

    return CoverageResult(
        labels=label_cov,
        lines=lines,
        suites_run=[s.name for s in selected_suites],
        returncode=rc,
        stdout=stdout,
        by_routine=by_routine,
        branches=branches,
    )


def _collect_branches(
    routine_paths: list[Path],
    label_locs: list[LabelLocation],
    hits: dict[tuple[str, str, int], int],
) -> list[BranchCoverage]:
    """Walk every production routine for branch points and join them
    against the per-line hit map.

    Includes routine-entry labels in ``label_lines`` even though they
    don't appear in ``label_locs`` (the entry label is excluded from
    label coverage but is still a valid owner for branches on the
    routine's first body lines).
    """
    label_lines: dict[tuple[str, str], int] = {
        (loc.routine, loc.label.upper()): loc.line for loc in label_locs
    }
    points = []
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
        # Re-walk for entry-label lines so branches on the routine
        # body line(s) before any non-entry label still join correctly.
        for entry_label, entry_line in _entry_label_lines(path, src):
            label_lines.setdefault((path.stem.upper(), entry_label.upper()), entry_line)
        points.extend(extract_branch_points(path, src))
    return join_branch_coverage(points, hits, label_lines)


def _entry_label_lines(path: Path, src: bytes) -> list[tuple[str, int]]:
    """Return ``(label_name, line)`` pairs for every label in ``path``.

    Used to seed the label_lines map so branches inside routine-entry
    labels can resolve their offset.
    """
    from m_cli.parser import parse

    out: list[tuple[str, int]] = []
    tree = parse(src)
    for line_node in tree.root_node.children:
        if line_node.type != "line":
            continue
        for child in line_node.children:
            if child.type == "label":
                name = src[child.start_byte : child.end_byte].decode(
                    "latin-1", errors="replace"
                )
                out.append((name, line_node.start_point[0] + 1))
                break
    return out


@dataclass(frozen=True)
class _ExecutableLine:
    """Internal: one line that the parser thinks is executable.

    ``label_line`` is the declaration line of ``label`` — needed to
    compute the YDB-internal trace offset (``line - label_line``).
    """

    routine: str  # upper-case canonical
    label: str  # owning label (case-preserved as declared)
    label_line: int  # 1-indexed line where the owning label is declared
    path: Path
    line: int  # 1-indexed absolute line of the executable command

    @property
    def trace_offset(self) -> int:
        """The third subscript YDB's TRACE will report for this line."""
        return self.line - self.label_line


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
    its owning label and the label's declaration line — the latter
    is needed to compute the YDB-internal trace offset.
    """
    from m_cli.parser import parse

    tree = parse(src)
    routine = path.stem.upper()
    out: list[_ExecutableLine] = []
    current_label: str | None = None
    current_label_line: int = 0
    for line_node in tree.root_node.children:
        if line_node.type != "line":
            continue
        line_no = line_node.start_point[0] + 1
        # Update current_label if this line has a label declaration.
        for child in line_node.children:
            if child.type == "label":
                current_label = src[child.start_byte : child.end_byte].decode(
                    "latin-1", errors="replace"
                )
                current_label_line = line_no
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
                    label_line=current_label_line,
                    path=path,
                    line=line_no,
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


# Per-line trace entry: ``^ycov("routine","LABEL",offset)="hit:..."``.
# The third subscript ``offset`` is the line offset from LABEL's
# declaration line (so absolute line == label_line + offset). The
# value's first colon-separated field is the hit count.
_TRACE_LINE_RE = re.compile(r'^\^ycov\("([^"]+)","([^"]+)",(\d+)\)="(\d+):')


def _parse_line_hits(stdout: str) -> dict[tuple[str, str, int], int]:
    """Parse ``^ycov(routine,LABEL,offset)`` entries into
    ``{(routine_upper, label_upper, offset): hit_count}``.

    Summary records like ``^ycov("*RUN")="..."`` and
    ``^ycov("routine","LABEL")="..."`` (the label entry total, no
    third subscript) are ignored — we only need the per-line
    entries.
    """
    out: dict[tuple[str, str, int], int] = {}
    for raw in stdout.splitlines():
        m = _TRACE_LINE_RE.match(raw.strip())
        if not m:
            continue
        try:
            offset = int(m.group(3))
            count = int(m.group(4))
        except ValueError:
            continue
        out[(m.group(1).upper(), m.group(2).upper(), offset)] = count
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
    "BranchCoverage",
    "CoverageResult",
    "LabelCoverage",
    "LineCoverage",
    "RunnerFn",
    "discover_routines_and_suites",
    "run_coverage",
]
