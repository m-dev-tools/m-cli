"""Tests for the `m test` CLI: argument parsing, --list, --filter, formats, exit codes."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from m_cli.cli import main
from m_cli.test import cli as test_cli  # noqa: F401  -- triggers import paths
from m_cli.test.discovery import TestSuite

HELLOTST_SRC = dedent("""\
    HELLOTST ; Test suite
            new pass,fail
            do start^TESTRUN(.pass,.fail)
            do tGreetWorld(.pass,.fail)
            do tGreetName(.pass,.fail)
            do report^TESTRUN(pass,fail)
            quit
            ;
    tGreetWorld(pass,fail)  ;@TEST "greet world"
            quit
            ;
    tGreetName(pass,fail)
            quit
""").encode("ascii")

ALL_PASS_OUTPUT = (
    "  PASS  one\n  PASS  two\n\nResults: 2 tests  2 passed  0 failed\nAll tests passed.\n"
)


def _write_suite(tmp_path: Path, name: str = "HELLOTST") -> Path:
    p = tmp_path / f"{name}.m"
    p.write_bytes(HELLOTST_SRC.replace(b"HELLOTST", name.encode()))
    return p


def test_list_mode_prints_discovered_tests(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _write_suite(tmp_path)
    rc = main(["test", "--list", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "HELLOTST" in out
    assert "tGreetWorld" in out
    assert "tGreetName" in out


def test_list_mode_no_suites_returns_2(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = main(["test", "--list", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no test suites" in err.lower()


def test_run_with_fake_ydb_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_suite(tmp_path)
    from m_cli.test import runner as runner_mod

    def fake(cmd, env=None, **kwargs):
        return ALL_PASS_OUTPUT, 0

    monkeypatch.setattr(runner_mod, "_default_runner", fake)
    rc = main(["test", str(tmp_path)])
    assert rc == 0


def test_run_with_fake_ydb_fail_exit_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_suite(tmp_path)
    from m_cli.test import runner as runner_mod

    fail_out = (
        "  FAIL  one\n         expected: =a\n         actual:   =b\n"
        "\nResults: 1 tests  0 passed  1 failed\n1 test(s) FAILED.\n"
    )

    def fake(cmd, env=None, **kwargs):
        return fail_out, 0

    monkeypatch.setattr(runner_mod, "_default_runner", fake)
    rc = main(["test", str(tmp_path)])
    assert rc == 1


def test_filter_runs_only_matching(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_suite(tmp_path, "ATST")
    _write_suite(tmp_path, "BTST")
    from m_cli.test import runner as runner_mod

    invocations: list[list[str]] = []

    def fake(cmd, env=None, **kwargs):
        invocations.append(cmd)
        return ALL_PASS_OUTPUT, 0

    monkeypatch.setattr(runner_mod, "_default_runner", fake)
    rc = main(["test", "--filter", "ATST", str(tmp_path)])
    assert rc == 0
    flat = " ".join(c for cmd in invocations for c in cmd)
    assert "^ATST" in flat
    assert "^BTST" not in flat


def test_single_case_selector_runs_one_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_suite(tmp_path)
    from m_cli.test import runner as runner_mod

    invocations: list[list[str]] = []

    def fake(cmd, env=None, **kwargs):
        invocations.append(cmd)
        return ALL_PASS_OUTPUT, 0

    monkeypatch.setattr(runner_mod, "_default_runner", fake)
    rc = main(["test", f"{tmp_path}/HELLOTST.m::tGreetWorld"])
    assert rc == 0
    flat = " ".join(c for cmd in invocations for c in cmd)
    # Single-test mode uses %XCMD with label^suite
    assert "tGreetWorld^HELLOTST" in flat


def test_unknown_label_in_selector_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    _write_suite(tmp_path)
    rc = main(["test", f"{tmp_path}/HELLOTST.m::tNoSuchTest"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "tNoSuchTest" in err


def test_tap_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_suite(tmp_path)
    from m_cli.test import runner as runner_mod

    def fake(cmd, env=None, **kwargs):
        return ALL_PASS_OUTPUT, 0

    monkeypatch.setattr(runner_mod, "_default_runner", fake)
    rc = main(["test", "--format", "tap", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("TAP version") or out.startswith("1..")
    assert "ok" in out


def test_json_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_suite(tmp_path)
    from m_cli.test import runner as runner_mod

    def fake(cmd, env=None, **kwargs):
        return ALL_PASS_OUTPUT, 0

    monkeypatch.setattr(runner_mod, "_default_runner", fake)
    rc = main(["test", "--format", "json", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "suites" in payload
    assert payload["ok"] is True
    assert payload["suites"][0]["name"] == "HELLOTST"


def test_junit_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_suite(tmp_path)
    from m_cli.test import runner as runner_mod

    def fake(cmd, env=None, **kwargs):
        return ALL_PASS_OUTPUT, 0

    monkeypatch.setattr(runner_mod, "_default_runner", fake)
    rc = main(["test", "--format", "junit", str(tmp_path)])
    assert rc == 0
    import xml.etree.ElementTree as ET

    out = capsys.readouterr().out
    root = ET.fromstring(out)
    assert root.tag == "testsuites"


def test_no_paths_uses_routines_tests_if_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = tmp_path / "proj"
    (proj / "routines" / "tests").mkdir(parents=True)
    p = proj / "routines" / "tests" / "ATST.m"
    p.write_bytes(HELLOTST_SRC.replace(b"HELLOTST", b"ATST"))
    monkeypatch.chdir(proj)

    from m_cli.test import runner as runner_mod

    invocations: list[list[str]] = []

    def fake(cmd, env=None, **kwargs):
        invocations.append(cmd)
        return ALL_PASS_OUTPUT, 0

    monkeypatch.setattr(runner_mod, "_default_runner", fake)
    rc = main(["test"])
    assert rc == 0
    assert any("^ATST" in " ".join(cmd) for cmd in invocations)


def test_TestSuite_imported_ok() -> None:
    # Sanity: ensure importing TestSuite from the public path is supported.
    s = TestSuite(name="X", path=Path("X.m"), cases=[])
    assert s.name == "X"
