"""Tests for `m test` runner — invocation, output parsing, result aggregation."""

from __future__ import annotations

from pathlib import Path

from m_cli.engine import Connection
from m_cli.test.discovery import TestCase, TestSuite
from m_cli.test.runner import (
    Outcome,
    RunResult,
    parse_suite_output,
    run_case,
    run_suite,
)

FAKE_CONN = Connection(host="vm-host", ssh_port=2222, ssh_user="vehu")

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
    result = run_suite(suite, runner=fake, conn=FAKE_CONN)
    assert result.suite == "HELLOTST"
    assert result.ok is True
    cmd = fake.captured["cmd"]
    assert cmd[0] == "ssh"
    assert FAKE_CONN.target in cmd
    # The remote-side script is the last arg; routine entry must be in it.
    assert "^HELLOTST" in cmd[-1]


def test_run_suite_propagates_failure(tmp_path: Path) -> None:
    suite = TestSuite(name="X", path=tmp_path / "X.m", cases=[])
    fake = _fake_runner(WITH_FAIL)
    result = run_suite(suite, runner=fake, conn=FAKE_CONN)
    assert result.ok is False
    assert result.summary.failed == 1


def test_run_suite_handles_nonzero_exit(tmp_path: Path) -> None:
    suite = TestSuite(name="X", path=tmp_path / "X.m", cases=[])
    # A non-zero exit code with no recognisable summary is also a failure.
    fake = _fake_runner("YDB-E-something\n", returncode=1)
    result = run_suite(suite, runner=fake, conn=FAKE_CONN)
    assert result.ok is False


def test_run_suite_marks_timed_out_when_runner_returns_sentinel(
    tmp_path: Path,
) -> None:
    """A runner that signals TIMEOUT_RC must surface as RunResult.timed_out.

    The point of this is the bug we're fixing: a timed-out subprocess
    used to look identical to a real 0/0 parse, so failures got
    silently masked. With the sentinel returncode, the Result carries
    timed_out=True and consumers (text/tap/json/junit) report it
    distinctly.
    """
    from m_cli.test.runner import TIMEOUT_RC

    suite = TestSuite(name="STDJSONTST", path=tmp_path / "STDJSONTST.m", cases=[])
    partial = (
        "  PASS  parse(empty object)\n"
        "  PASS  parse(empty array)\n"
        "[m-cli: timed out after 600s; subprocess killed]\n"
    )
    fake = _fake_runner(partial, returncode=TIMEOUT_RC)
    result = run_suite(suite, runner=fake, conn=FAKE_CONN)
    assert result.timed_out is True
    assert result.ok is False
    # Per-assertion lines printed before the kill are still parsed so
    # the user can see how far the suite got before the subprocess was
    # killed. The summary's `passed` counter uses the `Results: N tests`
    # banner which the timed-out subprocess never emitted, so it stays
    # zero — the per-assertion list is the canonical evidence here.
    assert len(result.summary.assertions) == 2
    assert "[m-cli: timed out" in result.stdout


def test_run_suite_default_timed_out_false_for_normal_runs(tmp_path: Path) -> None:
    """A clean suite must NOT have timed_out set."""
    suite = TestSuite(name="HELLOTST", path=tmp_path / "HELLOTST.m", cases=[])
    fake = _fake_runner(ALL_PASS)
    result = run_suite(suite, runner=fake, conn=FAKE_CONN)
    assert result.timed_out is False
    assert result.ok is True


def test_default_runner_returns_timeout_sentinel_on_subprocess_timeout() -> None:
    """End-to-end: _default_runner must catch TimeoutExpired and return
    (partial-with-marker, TIMEOUT_RC) rather than letting the exception
    bubble up. Uses ``sleep`` so the test costs ~0.2s of real time.
    """
    from m_cli.test.runner import TIMEOUT_RC, _default_runner

    stdout, rc = _default_runner(["sleep", "5"], None, timeout=0.2)
    assert rc == TIMEOUT_RC
    assert "timed out after 0.2s" in stdout


# ---------------------------------------------------------------------------
# run_case — single-test invocation via %XCMD
# ---------------------------------------------------------------------------


def test_run_case_invokes_xcmd(tmp_path: Path) -> None:
    case = TestCase(
        suite="HELLOTST",
        label="tGreetWorld",
        description=None,
        path=tmp_path / "HELLOTST.m",
        line=10,
    )
    fake = _fake_runner(
        "  PASS  greet(World)\n\nResults: 1 tests  1 passed  0 failed\nAll tests passed.\n"
    )
    result = run_case(case, runner=fake, conn=FAKE_CONN)
    assert result.ok is True
    cmd = fake.captured["cmd"]
    # The remote-side script is the last arg; %XCMD and the
    # single-test invocation must both be present in it.
    remote = cmd[-1]
    assert "%XCMD" in remote
    assert "tGreetWorld^HELLOTST" in remote


def test_run_case_uses_TestCase_protocol_for_start_and_report(tmp_path: Path) -> None:
    """C1: per-case selection must address the suite's protocol module
    (STDASSERT, TESTRUN, ...) — not the hardcoded ^TESTRUN."""
    case = TestCase(
        suite="STDB64TST",
        label="tEncodeRfcVectors",
        description=None,
        path=tmp_path / "STDB64TST.m",
        line=10,
        protocol="STDASSERT",
    )
    fake = _fake_runner(
        "  PASS  f\n\nResults: 1 tests  1 passed  0 failed\nAll tests passed.\n"
    )
    run_case(case, runner=fake, conn=FAKE_CONN)
    remote = fake.captured["cmd"][-1]
    assert "start^STDASSERT" in remote
    assert "report^STDASSERT" in remote
    assert "tEncodeRfcVectors^STDB64TST" in remote
    assert "TESTRUN" not in remote


def test_run_case_default_protocol_is_TESTRUN(tmp_path: Path) -> None:
    """Backwards compatibility: cases discovered before the field
    existed (or constructed without protocol=) still target TESTRUN."""
    case = TestCase(
        suite="HELLOTST",
        label="tGreetWorld",
        description=None,
        path=tmp_path / "HELLOTST.m",
        line=10,
    )
    fake = _fake_runner(
        "  PASS  x\n\nResults: 1 tests  1 passed  0 failed\nAll tests passed.\n"
    )
    run_case(case, runner=fake, conn=FAKE_CONN)
    remote = fake.captured["cmd"][-1]
    assert "start^TESTRUN" in remote
    assert "report^TESTRUN" in remote


# ---------------------------------------------------------------------------
# RunResult dataclass
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# JUnit XML output (C2)
# ---------------------------------------------------------------------------


def test_junit_output_emits_testsuites_root(capsys) -> None:
    from m_cli.test.output import write_output

    summary = parse_suite_output(WITH_FAIL)
    result = RunResult(
        suite="HELLOTST",
        label=None,
        summary=summary,
        ok=False,
        stdout=WITH_FAIL,
        returncode=0,
    )
    write_output([result], fmt="junit")
    out = capsys.readouterr().out
    assert out.startswith("<?xml")
    assert "<testsuites" in out
    assert 'name="HELLOTST"' in out
    # Counts roll up at the root.
    assert 'tests="3"' in out
    assert 'failures="1"' in out


def test_junit_output_emits_one_testcase_per_assertion(capsys) -> None:
    from m_cli.test.output import write_output

    summary = parse_suite_output(WITH_FAIL)
    result = RunResult(
        suite="HELLOTST",
        label=None,
        summary=summary,
        ok=False,
        stdout=WITH_FAIL,
        returncode=0,
    )
    write_output([result], fmt="junit")
    out = capsys.readouterr().out
    # 2 PASS + 1 FAIL = 3 testcase elements
    assert out.count("<testcase ") == 3
    # The failed assertion has a <failure> child carrying expected/actual.
    assert "<failure" in out
    assert "Hello, Alice!" in out
    assert "Hello, Alicia!" in out


def test_junit_output_is_well_formed_xml(capsys) -> None:
    import xml.etree.ElementTree as ET

    from m_cli.test.output import write_output

    summary = parse_suite_output(WITH_FAIL)
    result = RunResult(
        suite="HELLOTST",
        label=None,
        summary=summary,
        ok=False,
        stdout=WITH_FAIL,
        returncode=0,
    )
    write_output([result], fmt="junit")
    out = capsys.readouterr().out
    root = ET.fromstring(out)
    assert root.tag == "testsuites"
    suites = root.findall("testsuite")
    assert len(suites) == 1
    cases = suites[0].findall("testcase")
    assert len(cases) == 3
    failed = [c for c in cases if c.find("failure") is not None]
    assert len(failed) == 1


def test_junit_output_escapes_special_chars(capsys) -> None:
    """Description with <, >, &, " must be XML-escaped."""
    from m_cli.test.output import write_output
    from m_cli.test.runner import Assertion, Outcome, Summary

    summary = Summary(
        passed=0,
        failed=1,
        total=1,
        ok=False,
        assertions=[
            Assertion(
                Outcome.FAIL,
                'a < b & c > "d"',
                expected="<x>",
                actual="&y;",
            )
        ],
    )
    result = RunResult(
        suite="X",
        label=None,
        summary=summary,
        ok=False,
        stdout="",
        returncode=0,
    )
    write_output([result], fmt="junit")
    out = capsys.readouterr().out
    # Raw `<`, `>`, `&` must not appear inside attribute values; check
    # the parser accepts the XML and the description round-trips.
    import xml.etree.ElementTree as ET

    root = ET.fromstring(out)
    case = root.find("testsuite/testcase")
    assert case is not None
    assert case.get("name") == 'a < b & c > "d"'


def test_junit_output_with_no_assertions_falls_back_to_one_testcase_per_suite(
    capsys,
) -> None:
    """Whole-suite RunResult with empty assertions list should still
    emit one testcase per suite so JUnit consumers count something."""
    from m_cli.test.output import write_output
    from m_cli.test.runner import Summary

    summary = Summary(passed=1, failed=0, total=1, ok=True, assertions=[])
    result = RunResult(
        suite="EMPTYTST",
        label=None,
        summary=summary,
        ok=True,
        stdout="",
        returncode=0,
    )
    write_output([result], fmt="junit")
    out = capsys.readouterr().out
    assert "<testcase " in out
    assert "EMPTYTST" in out


def test_RunResult_dataclass() -> None:
    suite = TestSuite(name="X", path=Path("X.m"), cases=[])
    summary = parse_suite_output(ALL_PASS)
    r = RunResult(suite="X", label=None, summary=summary, ok=True, stdout="", returncode=0)
    assert r.ok is True
    _ = suite  # keep import live; used by other tests


# ---------------------------------------------------------------------------
# M1 companion tracks (X / W / Y) — STDMOCK / STDFIX / STDSEED integration
# ---------------------------------------------------------------------------

_PASS_OUTPUT = "  PASS  x\n\nResults: 1 tests  1 passed  0 failed\nAll tests passed.\n"


def _case(tmp_path: Path) -> TestCase:
    return TestCase(
        suite="MYPKGTST",
        label="tDoesAThing",
        description=None,
        path=tmp_path / "MYPKGTST.m",
        line=10,
        protocol="STDASSERT",
    )


# Track X — STDMOCK registry cleared between tests ----------------------


def test_run_case_clears_stdmock_before_test(tmp_path: Path) -> None:
    """Track X: each single-test invocation begins with a clean mock
    registry. The runner emits `do clear^STDMOCK` ahead of the test."""
    fake = _fake_runner(_PASS_OUTPUT)
    run_case(_case(tmp_path), runner=fake, conn=FAKE_CONN)
    remote = fake.captured["cmd"][-1]
    assert "clear^STDMOCK" in remote
    assert remote.index("clear^STDMOCK") < remote.index("tDoesAThing^MYPKGTST")


def test_run_suite_does_not_clear_stdmock(tmp_path: Path) -> None:
    """Track X (suite mode): each `mumps` invocation is a fresh
    process with an empty `^STDLIB($JOB,...)` tree, so the STDMOCK
    registry is empty by construction. No prelude `clear^STDMOCK`
    is needed — and avoiding %XCMD when no seeds are passed keeps
    suite mode robust to engine-side compile-cache issues with the
    `_XCMD.m` system routine."""
    suite = TestSuite(name="MYPKGTST", path=tmp_path / "MYPKGTST.m", cases=[])
    fake = _fake_runner(_PASS_OUTPUT)
    run_suite(suite, runner=fake, conn=FAKE_CONN)
    remote = fake.captured["cmd"][-1]
    assert "clear^STDMOCK" not in remote
    # Without seeds, suite mode invokes the routine directly via
    # `mumps -run ^SUITE` — no %XCMD indirection.
    assert "%XCMD" not in remote
    assert "^MYPKGTST" in remote


# Track W — per-test transactional isolation via inline tstart/trollback ---


def test_run_case_wraps_test_in_tstart_trollback_by_default(tmp_path: Path) -> None:
    """Track W: by default, the runner wraps the test invocation in
    inline ``tstart`` / ``trollback`` so per-test global mutations
    roll back at the end of the test. (Inline rather than via
    ``with^STDFIX`` because XECUTE inside ``with``'s stack frame
    cannot reach the xcmd-level ``pass`` / ``fail`` locals — STDFIX
    stays the API for application code that wants tag bookkeeping
    and an error-trap re-raise; the runner only needs rollback.)"""
    fake = _fake_runner(_PASS_OUTPUT)
    run_case(_case(tmp_path), runner=fake, conn=FAKE_CONN)
    remote = fake.captured["cmd"][-1]
    invoke = "do tDoesAThing^MYPKGTST(.pass,.fail)"
    assert invoke in remote
    assert "tstart" in remote
    assert "trollback" in remote
    # tstart precedes the test, trollback follows it.
    assert remote.index("tstart") < remote.index(invoke)
    assert remote.index(invoke) < remote.index("trollback")


def test_run_case_no_isolation_skips_transaction_wrapper(tmp_path: Path) -> None:
    """Track W: ``--no-isolation`` opts out so legacy ^TESTRUN-style
    suites (or suites that manage their own transactions) still work."""
    fake = _fake_runner(_PASS_OUTPUT)
    run_case(_case(tmp_path), runner=fake, conn=FAKE_CONN, isolation=False)
    remote = fake.captured["cmd"][-1]
    # No transaction wrapper.
    assert "tstart" not in remote
    assert "trollback" not in remote
    # The test is still invoked, just without the wrapper.
    assert "do tDoesAThing^MYPKGTST(.pass,.fail)" in remote


def test_run_suite_does_not_wrap_in_transaction(tmp_path: Path) -> None:
    """Track W (suite mode): the suite's own routine drives its
    per-test loop. The runner can't usefully wrap individual tests in
    suite mode, so it doesn't try — and a single suite-wide
    transaction would defeat per-test isolation anyway."""
    suite = TestSuite(name="MYPKGTST", path=tmp_path / "MYPKGTST.m", cases=[])
    fake = _fake_runner(_PASS_OUTPUT)
    run_suite(suite, runner=fake, conn=FAKE_CONN)
    remote = fake.captured["cmd"][-1]
    assert "tstart" not in remote
    assert "trollback" not in remote


# Track Y — STDSEED fixture loading via --seed PATH ---------------------


def test_run_case_loads_seeds_before_test(tmp_path: Path) -> None:
    """Track Y: each `--seed PATH` becomes a `do load^STDSEED("PATH")`
    call ahead of the test invocation. Order is preserved."""
    fake = _fake_runner(_PASS_OUTPUT)
    run_case(
        _case(tmp_path),
        runner=fake,
        conn=FAKE_CONN,
        seeds=["/data/users.tsv", "/data/sites.tsv"],
    )
    remote = fake.captured["cmd"][-1]
    assert 'load^STDSEED("/data/users.tsv")' in remote
    assert 'load^STDSEED("/data/sites.tsv")' in remote
    # Both seeds must come before the test invocation.
    assert remote.index("load^STDSEED") < remote.index("tDoesAThing^MYPKGTST")
    # Order preserved.
    assert remote.index("/data/users.tsv") < remote.index("/data/sites.tsv")


def test_run_case_no_seeds_emits_no_load_call(tmp_path: Path) -> None:
    """Track Y: empty seeds list emits no load^STDSEED."""
    fake = _fake_runner(_PASS_OUTPUT)
    run_case(_case(tmp_path), runner=fake, conn=FAKE_CONN)
    remote = fake.captured["cmd"][-1]
    assert "load^STDSEED" not in remote


def test_run_case_seed_path_with_double_quote_is_escaped(tmp_path: Path) -> None:
    """Track Y: a double-quote in a seed path is doubled per M string-
    literal escaping rules so the xcmd parses cleanly."""
    fake = _fake_runner(_PASS_OUTPUT)
    run_case(
        _case(tmp_path),
        runner=fake,
        conn=FAKE_CONN,
        seeds=['/data/has"quote.tsv'],
    )
    remote = fake.captured["cmd"][-1]
    assert 'load^STDSEED("/data/has""quote.tsv")' in remote


def test_run_suite_loads_seeds_before_suite(tmp_path: Path) -> None:
    """Track Y (suite mode): seeds are loaded before the suite entry
    so the suite's own per-test invocations see them."""
    suite = TestSuite(name="MYPKGTST", path=tmp_path / "MYPKGTST.m", cases=[])
    fake = _fake_runner(_PASS_OUTPUT)
    run_suite(suite, runner=fake, conn=FAKE_CONN, seeds=["/data/x.tsv"])
    remote = fake.captured["cmd"][-1]
    assert 'load^STDSEED("/data/x.tsv")' in remote
    assert remote.index("load^STDSEED") < remote.index("^MYPKGTST")


# --env PATH — STDENV-loaded test config -------------------------------


def test_run_case_loads_env_before_test(tmp_path: Path) -> None:
    """`--env PATH` parses each .env file via STDENV.parseFile and merges
    the result into ^STDLIB($JOB,"env"). Both files arrive before the
    test invocation; the kill+merge sequence is per-file so later files
    override earlier keys for matching subscripts."""
    fake = _fake_runner(_PASS_OUTPUT)
    run_case(
        _case(tmp_path),
        runner=fake,
        conn=FAKE_CONN,
        env_files=["/cfg/dev.env", "/cfg/local.env"],
    )
    remote = fake.captured["cmd"][-1]
    assert 'parseFile^STDENV("/cfg/dev.env",.envtmp)' in remote
    assert 'parseFile^STDENV("/cfg/local.env",.envtmp)' in remote
    assert 'merge ^STDLIB($JOB,"env")=envtmp' in remote
    # All env loads must precede the test invocation.
    assert remote.index("parseFile^STDENV") < remote.index("tDoesAThing^MYPKGTST")
    # Order preserved (later overrides earlier).
    assert remote.index("/cfg/dev.env") < remote.index("/cfg/local.env")


def test_run_case_no_env_files_emits_no_parsefile(tmp_path: Path) -> None:
    fake = _fake_runner(_PASS_OUTPUT)
    run_case(_case(tmp_path), runner=fake, conn=FAKE_CONN)
    remote = fake.captured["cmd"][-1]
    assert "parseFile^STDENV" not in remote


def test_run_suite_loads_env_before_suite(tmp_path: Path) -> None:
    """`--env PATH` (suite mode) populates ^STDLIB($JOB,"env") before the
    suite routine runs so test code can read via $get(^STDLIB($JOB,"env",
    KEY))."""
    suite = TestSuite(name="MYPKGTST", path=tmp_path / "MYPKGTST.m", cases=[])
    fake = _fake_runner(_PASS_OUTPUT)
    run_suite(suite, runner=fake, conn=FAKE_CONN, env_files=["/cfg/x.env"])
    remote = fake.captured["cmd"][-1]
    assert 'parseFile^STDENV("/cfg/x.env",.envtmp)' in remote
    assert remote.index("parseFile^STDENV") < remote.index("^MYPKGTST")
    # Suite mode falls back to %XCMD when there's a prelude.
    assert "%XCMD" in remote


# --update-snapshots — STDSNAP update mode ----------------------------


def test_run_case_sets_snap_update_sentinel(tmp_path: Path) -> None:
    fake = _fake_runner(_PASS_OUTPUT)
    run_case(_case(tmp_path), runner=fake, conn=FAKE_CONN, update_snapshots=True)
    remote = fake.captured["cmd"][-1]
    assert 'set ^STDLIB($JOB,"stdsnap","update")=1' in remote
    assert remote.index("stdsnap") < remote.index("tDoesAThing^MYPKGTST")


def test_run_case_default_does_not_set_snap_sentinel(tmp_path: Path) -> None:
    fake = _fake_runner(_PASS_OUTPUT)
    run_case(_case(tmp_path), runner=fake, conn=FAKE_CONN)
    remote = fake.captured["cmd"][-1]
    assert "stdsnap" not in remote


def test_run_suite_update_snapshots_routes_via_xcmd(tmp_path: Path) -> None:
    """Suite mode normally bypasses %XCMD; --update-snapshots forces
    %XCMD because a prelude is needed to set the sentinel."""
    suite = TestSuite(name="MYPKGTST", path=tmp_path / "MYPKGTST.m", cases=[])
    fake = _fake_runner(_PASS_OUTPUT)
    run_suite(suite, runner=fake, conn=FAKE_CONN, update_snapshots=True)
    remote = fake.captured["cmd"][-1]
    assert "%XCMD" in remote
    assert 'set ^STDLIB($JOB,"stdsnap","update")=1' in remote


# --timings — wall-clock per suite -------------------------------------


def test_run_suite_records_elapsed_ms(tmp_path: Path) -> None:
    """Every run_suite invocation records elapsed_ms via time.perf_counter,
    even when the caller doesn't ask for timings (the cost is one
    perf_counter call; cheap enough to always pay)."""
    suite = TestSuite(name="HELLOTST", path=tmp_path / "HELLOTST.m", cases=[])
    fake = _fake_runner(ALL_PASS)
    result = run_suite(suite, runner=fake, conn=FAKE_CONN)
    # The fake runner is essentially a no-op so elapsed will be very small,
    # but must be a finite non-negative number.
    assert result.elapsed_ms >= 0.0


def test_run_case_records_elapsed_ms(tmp_path: Path) -> None:
    fake = _fake_runner(_PASS_OUTPUT)
    result = run_case(_case(tmp_path), runner=fake, conn=FAKE_CONN)
    assert result.elapsed_ms >= 0.0
