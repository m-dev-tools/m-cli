"""CLI integration for ``m test --changed``.

Exercises the full argparse path: ``--changed`` filters the discovered
suites to those affine with git-modified files; combines with
``--filter`` (intersection); and exits 0 with a hint when no suites
qualify.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from m_cli.cli import main

HELLOTST_SRC = dedent("""\
    HELLOTST ; Test suite
            new pass,fail
            do start^TESTRUN(.pass,.fail)
            do tCase(.pass,.fail)
            do report^TESTRUN(pass,fail)
            quit
            ;
    tCase(pass,fail)  ;@TEST "case"
            quit
""").encode("ascii")

ALL_PASS_OUTPUT = (
    "  PASS  one\n\nResults: 1 tests  1 passed  0 failed\nAll tests passed.\n"
)


def _write_suite(tmp_path: Path, name: str) -> Path:
    p = tmp_path / f"{name}.m"
    p.write_bytes(HELLOTST_SRC.replace(b"HELLOTST", name.encode()))
    return p


def _patch_runner(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Patch the test-runner subprocess to a recorder that always passes."""
    invocations: list[list[str]] = []
    from m_cli.test import runner as runner_mod

    def fake(cmd, env=None):
        invocations.append(cmd)
        return ALL_PASS_OUTPUT, 0

    monkeypatch.setattr(runner_mod, "_default_runner", fake)
    return invocations


def _patch_git(monkeypatch: pytest.MonkeyPatch, status_output: str) -> None:
    from m_cli.test import changed as changed_mod

    def fake(cmd, cwd):
        return status_output, 0

    monkeypatch.setattr(changed_mod, "_default_runner", fake)


def test_changed_runs_only_affinity_matched_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_suite(tmp_path, "ATST")
    _write_suite(tmp_path, "BTST")
    # Source A.m is "modified"; affinity → ATST runs, BTST does not.
    (tmp_path / "A.m").write_bytes(b"; stub\n")
    invocations = _patch_runner(monkeypatch)
    _patch_git(monkeypatch, " M A.m\n")
    monkeypatch.chdir(tmp_path)

    rc = main(["test", "--changed", str(tmp_path)])
    assert rc == 0
    flat = " ".join(c for cmd in invocations for c in cmd)
    assert "^ATST" in flat
    assert "^BTST" not in flat


def test_changed_with_no_changes_exits_zero_with_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    _write_suite(tmp_path, "ATST")
    _patch_runner(monkeypatch)
    _patch_git(monkeypatch, "")  # nothing changed
    monkeypatch.chdir(tmp_path)

    rc = main(["test", "--changed", str(tmp_path)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "no changed" in err.lower()


def test_changed_combines_with_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--changed and --filter intersect: only suites in both sets run."""
    _write_suite(tmp_path, "ATST")
    _write_suite(tmp_path, "BTST")
    (tmp_path / "A.m").write_bytes(b"; stub\n")
    (tmp_path / "B.m").write_bytes(b"; stub\n")
    invocations = _patch_runner(monkeypatch)
    _patch_git(monkeypatch, " M A.m\n M B.m\n")
    monkeypatch.chdir(tmp_path)

    rc = main(["test", "--changed", "--filter", "ATST", str(tmp_path)])
    assert rc == 0
    flat = " ".join(c for cmd in invocations for c in cmd)
    assert "^ATST" in flat
    assert "^BTST" not in flat


def test_changed_suite_edit_runs_only_that_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Editing a suite file targets that suite only — not other suites."""
    _write_suite(tmp_path, "ATST")
    _write_suite(tmp_path, "BTST")
    invocations = _patch_runner(monkeypatch)
    _patch_git(monkeypatch, " M ATST.m\n")
    monkeypatch.chdir(tmp_path)

    rc = main(["test", "--changed", str(tmp_path)])
    assert rc == 0
    flat = " ".join(c for cmd in invocations for c in cmd)
    assert "^ATST" in flat
    assert "^BTST" not in flat


def test_changed_with_base_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--changed --changed-base main`` diffs against the named base."""
    _write_suite(tmp_path, "ATST")
    (tmp_path / "A.m").write_bytes(b"; stub\n")
    invocations = _patch_runner(monkeypatch)

    captured = {}
    from m_cli.test import changed as changed_mod

    def fake(cmd, cwd):
        captured["cmd"] = cmd
        return "A.m\n", 0

    monkeypatch.setattr(changed_mod, "_default_runner", fake)
    monkeypatch.chdir(tmp_path)

    rc = main(["test", "--changed", "--changed-base", "main", str(tmp_path)])
    assert rc == 0
    assert "diff" in captured["cmd"]
    assert "main" in captured["cmd"]
    flat = " ".join(c for cmd in invocations for c in cmd)
    assert "^ATST" in flat
