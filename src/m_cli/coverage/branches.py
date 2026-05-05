"""Branch coverage — track C4.

Branch coverage in M starts from a parse-tree pass: each branching
construct contributes one ``BranchPoint``. We then cross-reference the
trace global ``^ycov`` (line-level hit counts captured by YDB's
``view "TRACE"``) to mark each branch point as reached or unreached.

What counts as a branch:

  - ``IF`` / ``I`` command keywords — gate a same-line action.
  - ``ELSE`` / ``E`` command keywords — gate a same-line action.
  - ``FOR`` / ``F`` command keywords — loop entry / exit.
  - ``postconditional`` nodes — ``S:cond X=1``, ``Q:cond``, etc.
  - ``argument_postconditional`` nodes — ``D LBL:cond`` per-arg gating.

These mirror the decision points the linter's M-MOD-005 rule counts
toward cyclomatic complexity, so static identification is consistent.

True/false-outcome split is not tracked today: M's same-line gating
(``IF X DO BAR``) puts the conditional and its action on the same
source line, so YDB's per-line trace can't distinguish "condition was
true" from "condition was false". A future iteration can layer
ZBREAK-based per-command instrumentation on top — but the pure
line-trace approach already gives a usable "branch reached" signal at
no extra ydb cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from m_cli.parser import parse

# Command keywords whose presence introduces a branch decision. Mirrors
# the linter's _DECISION_KEYWORDS_UPPER set in m_cli.lint._modern.
_IF_KEYWORDS = frozenset({"IF", "I"})
_ELSE_KEYWORDS = frozenset({"ELSE", "E"})
_FOR_KEYWORDS = frozenset({"FOR", "F"})


@dataclass(frozen=True)
class BranchPoint:
    """One branch decision identified statically from the parse tree.

    ``kind`` is one of: ``if``, ``else``, ``for``, ``postconditional``,
    ``argument_postconditional``.
    """

    routine: str  # uppercased canonical routine (file stem)
    label: str  # owning label name (case as declared)
    path: Path
    line: int  # 1-indexed line of the branch decision
    column: int  # 0-indexed column
    kind: str


@dataclass(frozen=True)
class BranchCoverage:
    """A branch point joined to runtime hit data.

    ``reached`` is True iff the line containing the branch decision
    executed at least once. True/false outcome split is reserved for a
    later iteration — see module docstring.
    """

    point: BranchPoint
    reached: bool


def extract_branch_points(path: Path, src: bytes) -> list[BranchPoint]:
    """Walk the parse tree and emit one BranchPoint per branch decision.

    Pre-order walk over top-level ``line`` nodes; for each line, find
    the owning label and emit one BranchPoint per branching construct
    on that line. Returns ``[]`` for files with no branch decisions
    (or no labels at all).
    """
    tree = parse(src)
    routine = path.stem.upper()
    points: list[BranchPoint] = []
    current_label: str | None = None
    for line_node in tree.root_node.children:
        if line_node.type != "line":
            continue
        # Update current label if this line declares one.
        for child in line_node.children:
            if child.type == "label":
                current_label = src[child.start_byte : child.end_byte].decode(
                    "latin-1", errors="replace"
                )
                break
        if current_label is None:
            continue
        points.extend(_branches_in_line(line_node, src, routine, current_label, path))
    return points


def join_branch_coverage(
    points: list[BranchPoint],
    hits: dict[tuple[str, str, int], int],
    label_lines: dict[tuple[str, str], int],
) -> list[BranchCoverage]:
    """Join branch points to per-line hit counts.

    ``hits`` is the map produced by ``coverage.runner._parse_line_hits``:
    keyed by ``(routine_upper, label_upper, offset_from_label_line)``,
    value is the hit count.

    ``label_lines`` maps ``(routine_upper, label_upper) → declaration
    line`` — needed to compute the YDB trace offset for each branch
    point. A missing entry causes the branch to be reported unreached
    rather than raising.
    """
    out: list[BranchCoverage] = []
    for bp in points:
        key_label = (bp.routine, bp.label.upper())
        label_line = label_lines.get(key_label)
        reached = False
        if label_line is not None:
            offset = bp.line - label_line
            reached = hits.get((bp.routine, bp.label.upper(), offset), 0) > 0
        out.append(BranchCoverage(point=bp, reached=reached))
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _branches_in_line(
    line_node, src: bytes, routine: str, label: str, path: Path
) -> list[BranchPoint]:
    """Pre-order scan over one ``line`` subtree, emitting BranchPoints."""
    out: list[BranchPoint] = []
    for node in _walk(line_node):
        kind = _branch_kind(node, src)
        if kind is None:
            continue
        out.append(
            BranchPoint(
                routine=routine,
                label=label,
                path=path,
                line=node.start_point[0] + 1,
                column=node.start_point[1],
                kind=kind,
            )
        )
    return out


def _branch_kind(node, src: bytes) -> str | None:
    """Classify ``node`` as a branch kind, or None if it isn't one."""
    if node.type == "postconditional":
        return "postconditional"
    if node.type == "argument_postconditional":
        return "argument_postconditional"
    if node.type == "command_keyword":
        text = src[node.start_byte : node.end_byte].decode(
            "latin-1", errors="replace"
        ).upper()
        if text in _IF_KEYWORDS:
            return "if"
        if text in _ELSE_KEYWORDS:
            return "else"
        if text in _FOR_KEYWORDS:
            return "for"
    return None


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


__all__ = [
    "BranchCoverage",
    "BranchPoint",
    "extract_branch_points",
    "join_branch_coverage",
]
