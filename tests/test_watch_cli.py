"""Tests for the `m watch` CLI: argument parsing, --once, error paths."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from m_cli.cli import main

HELLOTST_SRC = dedent("""\
    HELLOTST ; Test suite
            new pass,fail
            do start^TESTRUN(.pass,.fail)
            do tGreetWorld(.pass,.fail)
            do report^TESTRUN(pass,fail)
            quit
            ;
    tGreetWorld(pass,fail)  ;@TEST "greet world"
            quit
""").encode("ascii")

ALL_PASS_OUTPUT = "  PASS  one\n\nResults: 1 tests  1 passed  0 failed\nAll tests passed.\n"


def _write_suite(tmp_path: Path, name: str = "HELLOTST") -> Path:
    p = tmp_path / f"{name}.m"
    p.write_bytes(HELLOTST_SRC.replace(b"HELLOTST", name.encode()))
    return p


def test_once_runs_initial_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_suite(tmp_path)
    from m_cli.test import runner as runner_mod

    invocations: list[list[str]] = []

    def fake(cmd, env=None):
        invocations.append(cmd)
        return ALL_PASS_OUTPUT, 0

    monkeypatch.setattr(runner_mod, "_default_runner", fake)
    rc = main(["watch", "--once", str(tmp_path)])
    assert rc == 0
    flat = " ".join(c for cmd in invocations for c in cmd)
    assert "^HELLOTST" in flat


def test_once_returns_1_when_initial_run_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_suite(tmp_path)
    from m_cli.test import runner as runner_mod

    fail_out = (
        "  FAIL  one\n         expected: =a\n         actual:   =b\n"
        "\nResults: 1 tests  0 passed  1 failed\n1 test(s) FAILED.\n"
    )

    def fake(cmd, env=None):
        return fail_out, 0

    monkeypatch.setattr(runner_mod, "_default_runner", fake)
    rc = main(["watch", "--once", str(tmp_path)])
    assert rc == 1


def test_no_suites_returns_2(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = main(["watch", "--once", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no test suites" in err.lower()


def test_filter_limits_initial_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_suite(tmp_path, "ATST")
    _write_suite(tmp_path, "BTST")
    from m_cli.test import runner as runner_mod

    invocations: list[list[str]] = []

    def fake(cmd, env=None):
        invocations.append(cmd)
        return ALL_PASS_OUTPUT, 0

    monkeypatch.setattr(runner_mod, "_default_runner", fake)
    rc = main(["watch", "--once", "--filter", "ATST", str(tmp_path)])
    assert rc == 0
    flat = " ".join(c for cmd in invocations for c in cmd)
    assert "^ATST" in flat
    assert "^BTST" not in flat
