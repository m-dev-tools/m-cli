"""Tests for `m test` runner — invocation, output parsing, result aggregation."""

from __future__ import annotations

from pathlib import Path

from m_cli.test.discovery import TestCase, TestSuite
from m_cli.test.runner import (
    Outcome,
    RunResult,
    parse_suite_output,
    run_case,
    run_suite,
)

# ---------------------------------------------------------------------------
# parse_suite_output — extract pass/fail counts and per-assertion lines
# ---------------------------------------------------------------------------

ALL_PASS = """\
  PASS  greet(World)
  PASS  greet(Alice)
  PASS  shout(alice)
  PASS  shout(BOB)

Results: 4 tests  4 passed  0 failed
All tests passed.
"""

WITH_FAIL = """\
  PASS  greet(World)
  FAIL  greet(Alice)
         expected: =Hello, Alice!
         actual:   =Hello, Alicia!
  PASS  shout(alice)

Results: 3 tests  2 passed  1 failed
1 test(s) FAILED.
"""


def test_parse_all_pass() -> None:
    summary = parse_suite_output(ALL_PASS)
    assert summary.passed == 4
    assert summary.failed == 0
    assert summary.total == 4
    assert summary.ok is True


def test_parse_with_failure() -> None:
    summary = parse_suite_output(WITH_FAIL)
    assert summary.passed == 2
    assert summary.failed == 1
    assert summary.total == 3
    assert summary.ok is False


def test_parse_empty_output() -> None:
    summary = parse_suite_output("")
    assert summary.passed == 0
    assert summary.failed == 0
    assert summary.total == 0
    # No "Results:" line -> we cannot conclude success.
    assert summary.ok is False


def test_parse_individual_assertions() -> None:
    summary = parse_suite_output(WITH_FAIL)
    assert len(summary.assertions) == 3
    assert summary.assertions[0].outcome == Outcome.PASS
    assert summary.assertions[0].description == "greet(World)"
    assert summary.assertions[1].outcome == Outcome.FAIL
    assert summary.assertions[1].description == "greet(Alice)"
    assert summary.assertions[1].expected == "=Hello, Alice!"
    assert summary.assertions[1].actual == "=Hello, Alicia!"
    assert summary.assertions[2].outcome == Outcome.PASS


# ---------------------------------------------------------------------------
# run_suite — uses an injectable command runner so tests don't need ydb
# ---------------------------------------------------------------------------


def _fake_runner(stdout: str, returncode: int = 0):
    captured: dict = {}

    def runner(cmd, env=None):
        captured["cmd"] = cmd
        captured["env"] = env
        return stdout, returncode

    runner.captured = captured  # type: ignore[attr-defined]
    return runner


def test_run_suite_invokes_ydb_with_routine_entry(tmp_path: Path) -> None:
    suite = TestSuite(name="HELLOTST", path=tmp_path / "HELLOTST.m", cases=[])
    fake = _fake_runner(ALL_PASS)
    result = run_suite(suite, runner=fake)
    assert result.suite == "HELLOTST"
    assert result.ok is True
    assert "^HELLOTST" in fake.captured["cmd"]


def test_run_suite_propagates_failure() -> None:
    suite = TestSuite(name="X", path=Path("X.m"), cases=[])
    fake = _fake_runner(WITH_FAIL)
    result = run_suite(suite, runner=fake)
    assert result.ok is False
    assert result.summary.failed == 1


def test_run_suite_handles_nonzero_exit() -> None:
    suite = TestSuite(name="X", path=Path("X.m"), cases=[])
    # A non-zero exit code with no recognisable summary is also a failure.
    fake = _fake_runner("YDB-E-something\n", returncode=1)
    result = run_suite(suite, runner=fake)
    assert result.ok is False


# ---------------------------------------------------------------------------
# run_case — single-test invocation via %XCMD
# ---------------------------------------------------------------------------


def test_run_case_invokes_xcmd() -> None:
    case = TestCase(
        suite="HELLOTST",
        label="tGreetWorld",
        description=None,
        path=Path("HELLOTST.m"),
        line=10,
    )
    fake = _fake_runner(
        "  PASS  greet(World)\n\nResults: 1 tests  1 passed  0 failed\nAll tests passed.\n"
    )
    result = run_case(case, runner=fake)
    assert result.ok is True
    cmd = fake.captured["cmd"]
    assert "%XCMD" in cmd
    # The single-test invocation must include the label^suite call.
    joined = " ".join(cmd)
    assert "tGreetWorld^HELLOTST" in joined


# ---------------------------------------------------------------------------
# RunResult dataclass
# ---------------------------------------------------------------------------


def test_RunResult_dataclass() -> None:
    suite = TestSuite(name="X", path=Path("X.m"), cases=[])
    summary = parse_suite_output(ALL_PASS)
    r = RunResult(suite="X", label=None, summary=summary, ok=True, stdout="", returncode=0)
    assert r.ok is True
    _ = suite  # keep import live; used by other tests
