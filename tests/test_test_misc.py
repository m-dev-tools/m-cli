"""Edge-case coverage for `m test`: output fallbacks, CLI error paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from m_cli.cli import main
from m_cli.test.output import write_output
from m_cli.test.runner import (
    Assertion,
    Outcome,
    RunResult,
    Summary,
)

# ---------------------------------------------------------------------------
# Output formatters — fallback / failure paths
# ---------------------------------------------------------------------------


def _make_failing_result() -> RunResult:
    summary = Summary(
        passed=0,
        failed=1,
        total=1,
        ok=False,
        assertions=[
            Assertion(
                outcome=Outcome.FAIL,
                description="x equals y",
                expected="=1",
                actual="=2",
            ),
        ],
    )
    return RunResult(
        suite="ATST",
        label=None,
        summary=summary,
        ok=False,
        stdout="",
        returncode=0,
    )


def test_text_output_prints_failure_details(
    capsys: pytest.CaptureFixture,
) -> None:
    write_output([_make_failing_result()], fmt="text")
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "x equals y" in out
    assert "expected" in out
    assert "actual" in out


def test_tap_output_falls_back_to_per_suite_when_no_assertions(
    capsys: pytest.CaptureFixture,
) -> None:
    summary = Summary(passed=0, failed=0, total=0, ok=False, assertions=[])
    r = RunResult(
        suite="ETST",
        label=None,
        summary=summary,
        ok=False,
        stdout="",
        returncode=1,
    )
    write_output([r], fmt="tap")
    out = capsys.readouterr().out
    assert out.startswith("TAP version")
    assert "1..1" in out
    assert "not ok" in out


def test_tap_output_emits_failure_yaml_block(
    capsys: pytest.CaptureFixture,
) -> None:
    write_output([_make_failing_result()], fmt="tap")
    out = capsys.readouterr().out
    assert "not ok 1" in out
    assert "  ---" in out
    assert "expected: =1" in out
    assert "actual:   =2" in out


# ---------------------------------------------------------------------------
# CLI error paths
# ---------------------------------------------------------------------------


def test_no_paths_and_no_routines_tests_returns_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = main(["test"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no paths" in err.lower() or "no test suites" in err.lower()


def test_selector_with_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = main(["test", f"{tmp_path}/MISSING.m::tFoo"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "not found" in err.lower()


def test_two_selectors_rejected(tmp_path: Path) -> None:
    p = tmp_path / "ATST.m"
    p.write_text("ATST\n quit\n")
    with pytest.raises(SystemExit):
        main(["test", f"{p}::tA", f"{p}::tB"])


def test_selector_with_list_mode(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    suite = tmp_path / "ATST.m"
    suite.write_bytes(b'ATST\n quit\n ;\ntFoo(pass,fail) ;@TEST "foo"\n quit\n')
    rc = main(["test", "--list", f"{suite}::tFoo"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "tFoo" in out


