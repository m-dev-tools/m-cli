"""Tests for branch coverage — track C4 (m coverage --branch).

Branch points in M are derived from the parse tree. Today we identify:

  - ``IF`` / ``I`` command keywords (decision)
  - ``ELSE`` / ``E`` command keywords (decision)
  - ``FOR`` / ``F`` command keywords (loop)
  - ``postconditional`` nodes (``S:cond X=1``, ``Q:cond``, …)
  - ``argument_postconditional`` nodes (``D:cond LBL``, ``R X:5``)

These mirror what the linter's cyclomatic-complexity rule (M-MOD-005)
counts as decisions, so the AST extraction logic is shared.

This MVP tracks **branch reach** only: a branch is "reached" iff its
containing line was executed during the run (per ``view "TRACE"``).
True/false-outcome split would need per-command instrumentation that
``view "TRACE"`` does not provide; flagged for a follow-up.
"""

from __future__ import annotations

from pathlib import Path

from m_cli.coverage.branches import (
    BranchCoverage,
    BranchPoint,
    extract_branch_points,
    join_branch_coverage,
)

# ---------------------------------------------------------------------------
# extract_branch_points — pure AST analysis
# ---------------------------------------------------------------------------


def test_extract_branch_points_finds_if_command(tmp_path: Path) -> None:
    src = b"FOO ;c\n IF X DO BAR\n QUIT\nBAR ;c\n QUIT\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    points = extract_branch_points(p, src)
    kinds = [bp.kind for bp in points]
    assert "if" in kinds


def test_extract_branch_points_finds_else_command(tmp_path: Path) -> None:
    src = b"FOO ;c\n IF X DO BAR\n ELSE  DO BAZ\n QUIT\nBAR ;c\n QUIT\nBAZ ;c\n QUIT\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    points = extract_branch_points(p, src)
    kinds = [bp.kind for bp in points]
    assert kinds.count("if") == 1
    assert kinds.count("else") == 1


def test_extract_branch_points_finds_for_command(tmp_path: Path) -> None:
    src = b"FOO ;c\n FOR I=1:1:10 DO BAR\n QUIT\nBAR ;c\n QUIT\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    points = extract_branch_points(p, src)
    assert any(bp.kind == "for" for bp in points)


def test_extract_branch_points_finds_postconditional(tmp_path: Path) -> None:
    src = b"FOO ;c\n SET:X=1 Y=2\n QUIT\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    points = extract_branch_points(p, src)
    assert any(bp.kind == "postconditional" for bp in points)


def test_extract_branch_points_finds_argument_postconditional(tmp_path: Path) -> None:
    """``DO LBL:cond`` attaches a postconditional to the argument, not
    the command. Tree-sitter-m emits ``argument_postconditional``."""
    src = b"FOO ;c\n DO BAR:X=1\n QUIT\nBAR ;c\n QUIT\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    points = extract_branch_points(p, src)
    assert any(bp.kind == "argument_postconditional" for bp in points)


def test_extract_branch_points_carries_routine_and_label(tmp_path: Path) -> None:
    src = b"FOO ;c\n QUIT\nINNER ;c\n IF X QUIT\n QUIT\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    points = extract_branch_points(p, src)
    if_pts = [bp for bp in points if bp.kind == "if"]
    assert len(if_pts) == 1
    assert if_pts[0].routine == "FOO"
    assert if_pts[0].label == "INNER"
    assert if_pts[0].line == 4  # 1-indexed


def test_extract_branch_points_skips_label_only_lines(tmp_path: Path) -> None:
    """A bare label line with no command can't carry a branch — make
    sure we don't hallucinate one."""
    src = b"FOO ;c\nINNER\n QUIT\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    points = extract_branch_points(p, src)
    assert points == []


def test_extract_branch_points_handles_empty_routine(tmp_path: Path) -> None:
    src = b"FOO ;c\n QUIT\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    assert extract_branch_points(p, src) == []


# ---------------------------------------------------------------------------
# join_branch_coverage — branch points × line-hit map
# ---------------------------------------------------------------------------


def test_join_marks_branch_reached_when_line_was_hit(tmp_path: Path) -> None:
    """A branch point whose containing line was executed at least once
    counts as 'reached'."""
    src = b"FOO ;c\n QUIT\nINNER ;c\n IF X QUIT\n QUIT\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    points = extract_branch_points(p, src)
    # Hit map keyed by (routine_upper, label_upper, offset_from_label_line)
    # INNER on line 3; the IF is on line 4 → offset 1.
    hits = {("FOO", "INNER", 1): 5}
    label_lines = {("FOO", "INNER"): 3}
    coverage = join_branch_coverage(points, hits, label_lines)
    assert len(coverage) == 1
    assert coverage[0].reached is True


def test_join_marks_branch_unreached_when_line_was_not_hit(tmp_path: Path) -> None:
    src = b"FOO ;c\n QUIT\nINNER ;c\n IF X QUIT\n QUIT\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    points = extract_branch_points(p, src)
    label_lines = {("FOO", "INNER"): 3}
    coverage = join_branch_coverage(points, {}, label_lines)
    assert len(coverage) == 1
    assert coverage[0].reached is False


def test_join_handles_missing_label_line(tmp_path: Path) -> None:
    """If we can't locate the owning label's line, the branch is
    reported unreached — never crashed."""
    src = b"FOO ;c\n IF X QUIT\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    points = extract_branch_points(p, src)
    coverage = join_branch_coverage(points, {}, {})
    assert all(bc.reached is False for bc in coverage)


# ---------------------------------------------------------------------------
# BranchPoint / BranchCoverage data classes — invariants
# ---------------------------------------------------------------------------


def test_branchpoint_is_hashable() -> None:
    """Frozen dataclass — usable as a dict key / set member."""
    bp = BranchPoint(
        routine="FOO", label="INNER", path=Path("FOO.m"),
        line=4, column=1, kind="if",
    )
    assert {bp}  # uses __hash__


def test_branchcoverage_carries_point_and_reached_flag() -> None:
    bp = BranchPoint(
        routine="FOO", label="INNER", path=Path("FOO.m"),
        line=4, column=1, kind="if",
    )
    bc = BranchCoverage(point=bp, reached=True)
    assert bc.point is bp
    assert bc.reached is True
