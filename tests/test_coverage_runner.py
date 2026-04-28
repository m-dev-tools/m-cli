"""Tests for ``m_cli.coverage.runner`` — Phase C, Tier 2.

The runner uses YDB's built-in ``view "TRACE"`` to capture per-line
hit counts into ``^ycov``; we cross-reference with parser-identified
executable lines to compute coverage. Tests inject a fake RunnerFn
that returns canned stdout/returncode pairs so we don't need a live
ydb.
"""

from __future__ import annotations

from pathlib import Path

from m_cli.coverage.runner import (
    CoverageResult,
    LabelCoverage,
    LineCoverage,
    _build_script,
    _executable_lines_for_file,
    _parse_line_hits,
    discover_routines_and_suites,
    run_coverage,
)
from m_cli.test.discovery import discover

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_project(tmp_path: Path) -> tuple[list[Path], list]:
    """Create a minimal m-tools-shaped layout under ``tmp_path``.
    Returns (routines, suites)."""
    routines_dir = tmp_path / "routines"
    routines_dir.mkdir()
    tests_dir = routines_dir / "tests"
    tests_dir.mkdir()

    # Production routine with three labels (one is the routine entry).
    # HELLO label: just a comment + QUIT (line 2 executable).
    # GREET: lines 4 (comment), 5 (set X=1), 6 (QUIT) — lines 5+6 executable.
    # SHOUT: lines 8 (comment), 9 (set Y=2), 10 (QUIT) — lines 9+10 executable.
    (routines_dir / "HELLO.m").write_bytes(
        b"HELLO ;c\n QUIT\nGREET ;c\n SET X=1\n QUIT\nSHOUT ;c\n SET Y=2\n QUIT\n"
    )
    (routines_dir / "MATH.m").write_bytes(b"MATH ;c\n QUIT\nADD ;c\n SET R=1\n QUIT\n")

    (tests_dir / "HELLOTST.m").write_bytes(
        b"HELLOTST ;c\n D GREET^HELLO\n D ADD^MATH\n QUIT\n"
        b"tCovers(pass,fail) ;@TEST\n QUIT\n"
    )
    routines, suites = discover_routines_and_suites([tmp_path])
    return routines, suites


# ---------------------------------------------------------------------------
# discover_routines_and_suites
# ---------------------------------------------------------------------------


def test_discover_separates_suites_from_production(tmp_path: Path) -> None:
    routines, suites = _seed_project(tmp_path)
    routine_names = sorted(p.stem for p in routines)
    assert routine_names == ["HELLO", "MATH"]
    suite_names = sorted(s.name for s in suites)
    assert suite_names == ["HELLOTST"]


def test_discover_classifies_testrun_as_suite_input(tmp_path: Path) -> None:
    """``TESTRUN.m`` (the assertion library) isn't a test suite per se,
    but it isn't production code either — exclude it from production
    routines like m-tools' ycover does."""
    (tmp_path / "MATH.m").write_bytes(b"MATH ;c\n QUIT\nADD ;c\n QUIT\n")
    (tmp_path / "TESTRUN.m").write_bytes(b"TESTRUN ;c\n QUIT\n")
    routines, _ = discover_routines_and_suites([tmp_path])
    assert "TESTRUN" not in {p.stem for p in routines}


# ---------------------------------------------------------------------------
# _build_script
# ---------------------------------------------------------------------------


def test_build_script_enables_trace_runs_suites_disables_and_dumps(
    tmp_path: Path,
) -> None:
    _, suites = _seed_project(tmp_path)

    script = _build_script(suites)
    assert "kill ^ycov" in script
    assert 'view "TRACE":1:"^ycov":""' in script
    assert "do ^HELLOTST" in script
    assert 'view "TRACE":0:"^ycov":""' in script
    assert "zwrite ^ycov" in script
    assert script.rstrip().endswith("halt")


def test_build_script_no_per_label_zbreak() -> None:
    """The trace-based script doesn't need a ZBREAK per label — that's
    the whole point of the refactor. An accidental ZBREAK in the script
    would slow runs to a crawl on large workspaces."""
    suites = []
    script = _build_script(suites)
    assert "zbreak" not in script.lower()


# ---------------------------------------------------------------------------
# _parse_trace_output
# ---------------------------------------------------------------------------


def test_parse_line_hits_extracts_routine_label_offset_count() -> None:
    """Per-line entries are keyed by (routine_upper, label_upper,
    offset_from_label_line). The hit count is the first colon-separated
    field of the value string."""
    stdout = (
        '^ycov("*RUN")="2068:8274:10342"\n'
        '^ycov("hello","GREET")="1:75:299:374:374"\n'
        '^ycov("hello","GREET",2)="1:0:0:1:1"\n'
        '^ycov("hello","GREET",3)="2:0:0:2:2"\n'
        '^ycov("math","ADD",1)="1:0:0:1:1"\n'
        "noise on stderr\n"
    )
    hits = _parse_line_hits(stdout)
    assert hits == {
        ("HELLO", "GREET", 2): 1,
        ("HELLO", "GREET", 3): 2,
        ("MATH", "ADD", 1): 1,
    }


def test_parse_line_hits_ignores_summary_records() -> None:
    """Label summary (no third subscript) and ``*RUN`` / ``*CHILDREN``
    aren't per-line entries; ignore them."""
    stdout = (
        '^ycov("*RUN")="..."\n'
        '^ycov("*CHILDREN")="..."\n'
        '^ycov("hello","GREET")="1:75:299:374:374"\n'
    )
    assert _parse_line_hits(stdout) == {}


def test_parse_line_hits_handles_empty_stdout() -> None:
    assert _parse_line_hits("") == {}


def test_parse_line_hits_records_zero_counts() -> None:
    """A trace entry with hit_count=0 is rare but should still be
    parsed — the caller decides what to do with it."""
    stdout = '^ycov("hello","GREET",4)="0:0:0:0:0"\n'
    hits = _parse_line_hits(stdout)
    assert hits == {("HELLO", "GREET", 4): 0}


# ---------------------------------------------------------------------------
# _executable_lines_for_file
# ---------------------------------------------------------------------------


def test_executable_lines_finds_command_bearing_lines(tmp_path: Path) -> None:
    src = b"FOO ;header\n ; comment\n SET X=1\n QUIT\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    lines = _executable_lines_for_file(p, src)
    # Line 1 (label-only header) and line 2 (comment-only) are NOT executable.
    # Lines 3 (SET X=1) and 4 (QUIT) ARE.
    line_numbers = sorted(line.line for line in lines)
    assert line_numbers == [3, 4]
    # Each line carries its owning label.
    assert all(line.label == "FOO" for line in lines)


def test_executable_lines_attribute_to_nearest_label(tmp_path: Path) -> None:
    src = b"FOO ;c\n QUIT\nINNER ;c\n SET X=1\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    lines = _executable_lines_for_file(p, src)
    by_line = {line.line: line.label for line in lines}
    assert by_line == {2: "FOO", 4: "INNER"}


def test_executable_lines_carry_label_line_for_offset_decode(tmp_path: Path) -> None:
    """Each executable line tracks its owning label's declaration
    line so we can map back from YDB's TRACE offset to the file line."""
    src = b"FOO ;c\n QUIT\nINNER ;c\n SET X=1\n QUIT\n"
    p = tmp_path / "FOO.m"
    p.write_bytes(src)
    lines = _executable_lines_for_file(p, src)
    by_line = {line.line: line for line in lines}
    # FOO body on line 2: FOO declared on line 1 → offset 1.
    assert by_line[2].label_line == 1
    assert by_line[2].trace_offset == 1
    # INNER body on lines 4 and 5: INNER on line 3 → offsets 1, 2.
    assert by_line[4].label_line == 3
    assert by_line[4].trace_offset == 1
    assert by_line[5].trace_offset == 2


# ---------------------------------------------------------------------------
# run_coverage — full pipeline with mocked runner
# ---------------------------------------------------------------------------


def test_run_coverage_marks_each_label_covered_or_not(tmp_path: Path) -> None:
    routines, suites = _seed_project(tmp_path)

    # Mocked runner: trace shows GREET's two body lines (offsets 1, 2
    # from GREET on line 3) and ADD's first body line (offset 1 from
    # ADD on line 3 of MATH.m). SHOUT and the entry labels are absent.
    canned = (
        '^ycov("HELLO","GREET",1)="1:0:0:1:1"\n'
        '^ycov("HELLO","GREET",2)="1:0:0:1:1"\n'
        '^ycov("MATH","ADD",1)="1:0:0:1:1"\n'
    )
    captured = {}

    def fake_runner(cmd, stdin_text, env):
        captured["cmd"] = cmd
        captured["stdin"] = stdin_text
        return canned, 0

    result = run_coverage(routines, suites, runner=fake_runner)

    assert result.returncode == 0
    by_label = {(lab.routine, lab.label): lab.covered for lab in result.labels}
    assert by_label[("HELLO", "GREET")] is True
    assert by_label[("HELLO", "SHOUT")] is False
    assert by_label[("MATH", "ADD")] is True
    # Routine-entry labels (HELLO^HELLO, MATH^MATH) shouldn't appear at all.
    assert ("HELLO", "HELLO") not in by_label
    assert ("MATH", "MATH") not in by_label


def test_run_coverage_populates_line_data(tmp_path: Path) -> None:
    """Line data carries true per-line hit counts: trace offsets are
    decoded against the parser's label declaration lines."""
    routines, suites = _seed_project(tmp_path)
    canned = (
        # GREET on line 3 → offsets 1 (line 4) and 2 (line 5).
        '^ycov("HELLO","GREET",1)="2:0:0:2:2"\n'
        '^ycov("HELLO","GREET",2)="3:0:0:3:3"\n'
        # ADD on line 3 of MATH.m → offset 1 (line 4) only.
        '^ycov("MATH","ADD",1)="1:0:0:1:1"\n'
    )

    def fake_runner(cmd, stdin_text, env):
        return canned, 0

    result = run_coverage(routines, suites, runner=fake_runner)

    by_pos = {(lc.routine, lc.line): lc.hit_count for lc in result.lines}
    # GREET line 4 hit twice, line 5 hit thrice (offset-decoded).
    assert by_pos[("HELLO", 4)] == 2
    assert by_pos[("HELLO", 5)] == 3
    # SHOUT body lines 7, 8 not traced → 0.
    assert by_pos[("HELLO", 7)] == 0
    assert by_pos[("HELLO", 8)] == 0
    # ADD line 4 hit once; line 5 not traced.
    assert by_pos[("MATH", 4)] == 1
    assert by_pos[("MATH", 5)] == 0


def test_run_coverage_computes_label_and_line_percent(tmp_path: Path) -> None:
    """Label-coverage denominator excludes routine-entry labels;
    line-coverage denominator counts every executable line in the file."""
    routines, suites = _seed_project(tmp_path)
    # Only GREET line 4 is traced (offset 1 from GREET on line 3).
    canned = '^ycov("HELLO","GREET",1)="1:0:0:1:1"\n'

    def fake_runner(cmd, stdin_text, env):
        return canned, 0

    result = run_coverage(routines, suites, runner=fake_runner)

    # 3 non-entry labels: GREET, SHOUT, ADD. 1 covered (GREET — any
    # of its lines hit ⇒ covered).
    assert result.total == 3
    assert result.covered == 1
    assert result.by_routine == {"HELLO": (1, 2), "MATH": (0, 1)}
    # Line-level: HELLO has 5 executable lines (entry body line 2;
    # GREET 4,5; SHOUT 7,8); MATH has 3 (entry line 2; ADD 4,5).
    # Total 8 executable; only GREET line 4 was hit → 1/8.
    assert result.total_lines == 8
    assert result.covered_lines == 1


def test_run_coverage_passes_script_to_runner_via_stdin(tmp_path: Path) -> None:
    routines, suites = _seed_project(tmp_path)
    captured = {}

    def fake_runner(cmd, stdin_text, env):
        captured["stdin"] = stdin_text
        return "", 0

    run_coverage(routines, suites, runner=fake_runner)

    stdin = captured["stdin"]
    assert 'view "TRACE":1:"^ycov":""' in stdin
    assert "do ^HELLOTST" in stdin


def test_run_coverage_suite_filter_restricts_run(tmp_path: Path) -> None:
    routines, suites = _seed_project(tmp_path)

    def fake_runner(cmd, stdin_text, env):
        assert "do ^HELLOTST" not in stdin_text
        return "", 0

    result = run_coverage(routines, suites, runner=fake_runner, suite_filter=["NONEXIST"])
    assert result.suites_run == []


def test_run_coverage_returns_empty_when_no_routines(tmp_path: Path) -> None:
    """No production routines → empty CoverageResult, no ydb invocation."""
    suites = discover([tmp_path])

    def fake_runner(cmd, stdin_text, env):
        raise AssertionError("runner should not be called with no routines")

    result = run_coverage([], suites, runner=fake_runner)
    assert result.total == 0
    assert result.percent == 0.0


# ---------------------------------------------------------------------------
# CoverageResult properties
# ---------------------------------------------------------------------------


def test_coverage_result_percent_handles_zero_total() -> None:
    result = CoverageResult(labels=[], lines=[], suites_run=[], returncode=0, stdout="")
    assert result.percent == 0.0
    assert result.line_percent == 0.0


def test_coverage_result_total_and_covered() -> None:
    p = Path("/x.m")
    labels = [
        LabelCoverage(routine="X", label="A", path=p, line=1, covered=True),
        LabelCoverage(routine="X", label="B", path=p, line=2, covered=False),
    ]
    lines = [
        LineCoverage(routine="X", label="A", path=p, line=1, hit_count=1),
        LineCoverage(routine="X", label="B", path=p, line=2, hit_count=0),
    ]
    result = CoverageResult(
        labels=labels, lines=lines, suites_run=[], returncode=0, stdout=""
    )
    assert result.total == 2
    assert result.covered == 1
    assert result.percent == 50.0
    assert result.total_lines == 2
    assert result.covered_lines == 1
    assert result.line_percent == 50.0
