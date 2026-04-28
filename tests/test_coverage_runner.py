"""Tests for ``m_cli.coverage.runner`` — Phase C, Tier 2 first slice.

The runner builds a ZBREAK-instrumented script, hands it to ydb on
stdin, and parses ^ycov output. Tests inject a fake RunnerFn that
returns canned stdout/returncode pairs so we don't need a live ydb.
"""

from __future__ import annotations

from pathlib import Path

from m_cli.coverage.runner import (
    CoverageResult,
    LabelCoverage,
    _build_script,
    _parse_covered,
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

    # Production routine with three labels (one of which is the routine entry).
    (routines_dir / "HELLO.m").write_bytes(
        b"HELLO ;c\n QUIT\nGREET ;c\n QUIT\nSHOUT ;c\n QUIT\n"
    )
    (routines_dir / "MATH.m").write_bytes(b"MATH ;c\n QUIT\nADD ;c\n QUIT\n")

    # Suite that calls GREET^HELLO and ADD^MATH (so both should be covered).
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


def test_build_script_emits_zbreak_per_label_and_do_per_suite(tmp_path: Path) -> None:
    routines, suites = _seed_project(tmp_path)

    # Trim to non-routine-entry labels (matches what _discover_targets does).
    from m_cli.coverage.runner import _discover_targets
    targets = _discover_targets(routines)

    script = _build_script(targets, suites)
    assert "kill ^ycov" in script
    assert 'zbreak GREET^HELLO:"set ^ycov(""HELLO"",""GREET"")=1"' in script
    assert 'zbreak ADD^MATH:"set ^ycov(""MATH"",""ADD"")=1"' in script
    assert "do ^HELLOTST" in script
    assert script.rstrip().endswith("halt")


def test_build_script_preserves_lowercase_filenames(tmp_path: Path) -> None:
    """ydb resolves routines case-sensitively on Linux; lowercase
    filenames (m-tools convention) must produce lowercase ZBREAK targets."""
    routines_dir = tmp_path / "routines"
    routines_dir.mkdir()
    (routines_dir / "tests").mkdir()
    (routines_dir / "csv.m").write_bytes(b"csv ;c\n QUIT\nparseLine ;c\n QUIT\n")
    (routines_dir / "tests" / "CSVTST.m").write_bytes(
        b"CSVTST ;c\n D parseLine^csv\n QUIT\n"
    )
    routines, suites = discover_routines_and_suites([tmp_path])
    from m_cli.coverage.runner import _discover_targets
    targets = _discover_targets(routines)

    script = _build_script(targets, suites)
    assert "zbreak parseLine^csv:" in script
    assert '^ycov(""csv"",""parseLine"")' in script
    # No uppercased CSV in the ZBREAK target — that would mis-resolve on Linux.
    assert "zbreak parseLine^CSV:" not in script


# ---------------------------------------------------------------------------
# _parse_covered
# ---------------------------------------------------------------------------


def test_parse_covered_extracts_routine_label_pairs() -> None:
    stdout = (
        '^ycov("HELLO","GREET")=1\n'
        '^ycov("MATH","ADD")=1\n'
        "noise on stderr\n"
        '^ycov("HELLO","SHOUT")=1\n'
    )
    covered = _parse_covered(stdout)
    assert covered == {("HELLO", "GREET"), ("MATH", "ADD"), ("HELLO", "SHOUT")}


def test_parse_covered_ignores_unrelated_lines() -> None:
    stdout = "Hello world\nERROR: nothing\n"
    assert _parse_covered(stdout) == set()


# ---------------------------------------------------------------------------
# run_coverage — full pipeline with mocked runner
# ---------------------------------------------------------------------------


def test_run_coverage_marks_each_label_covered_or_not(tmp_path: Path) -> None:
    routines, suites = _seed_project(tmp_path)

    # Mocked runner: pretend ydb covered GREET^HELLO and ADD^MATH only.
    canned = (
        '^ycov("HELLO","GREET")=1\n'
        '^ycov("MATH","ADD")=1\n'
    )

    captured = {}

    def fake_runner(cmd, stdin_text, env):
        captured["cmd"] = cmd
        captured["stdin"] = stdin_text
        captured["env"] = env
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


def test_run_coverage_computes_percent_and_routine_breakdown(tmp_path: Path) -> None:
    routines, suites = _seed_project(tmp_path)
    canned = '^ycov("HELLO","GREET")=1\n'

    def fake_runner(cmd, stdin_text, env):
        return canned, 0

    result = run_coverage(routines, suites, runner=fake_runner)

    # 1 covered out of 3 non-entry labels (HELLO has GREET + SHOUT, MATH has ADD).
    assert result.total == 3
    assert result.covered == 1
    # Per-routine: HELLO 1/2, MATH 0/1.
    assert result.by_routine == {"HELLO": (1, 2), "MATH": (0, 1)}


def test_run_coverage_passes_script_to_runner_via_stdin(tmp_path: Path) -> None:
    routines, suites = _seed_project(tmp_path)
    captured = {}

    def fake_runner(cmd, stdin_text, env):
        captured["stdin"] = stdin_text
        return "", 0

    run_coverage(routines, suites, runner=fake_runner)

    # The script must include both ZBREAKs and the suite call.
    stdin = captured["stdin"]
    assert "zbreak GREET^HELLO" in stdin
    assert "do ^HELLOTST" in stdin


def test_run_coverage_suite_filter_restricts_run(tmp_path: Path) -> None:
    routines, suites = _seed_project(tmp_path)

    def fake_runner(cmd, stdin_text, env):
        # Suite filter should drop HELLOTST → no `do ^HELLOTST` in script.
        assert "do ^HELLOTST" not in stdin_text
        return "", 0

    result = run_coverage(routines, suites, runner=fake_runner, suite_filter=["NONEXIST"])
    assert result.suites_run == []


def test_run_coverage_returns_empty_result_when_no_labels(tmp_path: Path) -> None:
    """No production routines → empty CoverageResult, no ydb invocation."""
    suites = discover([tmp_path])  # no .m files — empty discovery

    def fake_runner(cmd, stdin_text, env):
        raise AssertionError("runner should not be called with no labels")

    result = run_coverage([], suites, runner=fake_runner)
    assert result.total == 0
    assert result.percent == 0.0


# ---------------------------------------------------------------------------
# CoverageResult properties
# ---------------------------------------------------------------------------


def test_coverage_result_percent_handles_zero_total() -> None:
    result = CoverageResult(labels=[], suites_run=[], returncode=0, stdout="")
    assert result.percent == 0.0


def test_coverage_result_total_and_covered() -> None:
    labels = [
        LabelCoverage(routine="X", label="A", path=Path("/x.m"), line=1, covered=True),
        LabelCoverage(routine="X", label="B", path=Path("/x.m"), line=2, covered=False),
    ]
    result = CoverageResult(labels=labels, suites_run=[], returncode=0, stdout="")
    assert result.total == 2
    assert result.covered == 1
    assert result.percent == 50.0
