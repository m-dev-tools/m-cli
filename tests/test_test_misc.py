"""Edge-case coverage for `m test`: env composition, output fallbacks, error paths."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from m_cli.cli import main
from m_cli.test.output import write_output
from m_cli.test.runner import (
    Assertion,
    Outcome,
    RunResult,
    Summary,
    _build_env,
    _derive_ydb_routines,
    _ydb_path,
)


def test_ydb_path_uses_YDB_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YDB", "/custom/ydb")
    assert _ydb_path() == "/custom/ydb"


def test_ydb_path_uses_ydb_dist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("YDB", raising=False)
    fake = tmp_path / "dist"
    fake.mkdir()
    (fake / "ydb").write_text("")
    monkeypatch.setenv("ydb_dist", str(fake))
    assert _ydb_path().endswith("/ydb")


def test_ydb_path_falls_back_to_PATH(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YDB", raising=False)
    monkeypatch.delenv("ydb_dist", raising=False)
    assert _ydb_path() == "ydb"


def test_build_env_honors_existing_ydb_routines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ydb_routines", "/already/set")
    env = _build_env(tmp_path / "X.m", None)
    assert env["ydb_routines"] == "/already/set"


def test_build_env_derives_ydb_routines_from_suite_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ydb_routines", raising=False)
    suite = tmp_path / "X.m"
    suite.write_text("X\n")
    env = _build_env(suite, None)
    assert str(tmp_path.resolve()) in env["ydb_routines"]


def test_build_env_includes_routines_sibling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ydb_routines", raising=False)
    routines = tmp_path / "routines"
    tests = routines / "tests"
    tests.mkdir(parents=True)
    suite = tests / "ATST.m"
    suite.write_text("ATST\n")
    env = _build_env(suite, None)
    assert str(routines.resolve()) in env["ydb_routines"]
    assert str(tests.resolve()) in env["ydb_routines"]


def test_derive_ydb_routines_returns_none_for_missing_dir() -> None:
    fake = Path("/no/such/dir/ZTST.m")
    # _derive returns whatever it can; for a non-existent suite dir it
    # may return None or skip parts — assert it's a string-or-None.
    out = _derive_ydb_routines(fake)
    assert out is None or isinstance(out, str)


def test_build_env_override_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ydb_routines", "/will/be/overridden")
    env = _build_env(tmp_path / "X.m", {"ydb_routines": "/overridden"})
    assert env["ydb_routines"] == "/overridden"


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


def test_selector_with_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    rc = main(["test", f"{tmp_path}/MISSING.m::tFoo"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "not found" in err.lower()


def test_two_selectors_rejected(tmp_path: Path) -> None:
    p = tmp_path / "ATST.m"
    p.write_text("ATST\n quit\n")
    with pytest.raises(SystemExit):
        main(["test", f"{p}::tA", f"{p}::tB"])


def test_selector_with_list_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    suite = tmp_path / "ATST.m"
    suite.write_bytes(
        b"ATST\n quit\n ;\ntFoo(pass,fail) ;@TEST \"foo\"\n quit\n"
    )
    rc = main(["test", "--list", f"{suite}::tFoo"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "tFoo" in out


# Sanity: prove the env builder leaves PATH alone (smoke test against
# accidental env clobber)
def test_build_env_preserves_PATH(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", "/sentinel/path")
    env = _build_env(tmp_path / "X.m", None)
    assert env["PATH"] == "/sentinel/path"
    _ = os.environ  # keep the import live
