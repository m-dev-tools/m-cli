"""Tests for ``m test --changed`` — track C5.

Resolves which test suites to re-run based on the set of ``.m`` files
modified relative to git's view of the workspace. Source-side changes
map to their adjacent suite via the same affinity rule ``m watch``
already uses (``foo.m`` → ``FOOTST.m``); suite-side changes map to
themselves; deletions and non-``.m`` paths are ignored.

Tests stub the git runner so no git binary or repo is required.
"""

from __future__ import annotations

from pathlib import Path

from m_cli.test.changed import changed_to_suites, find_changed_m_files
from m_cli.test.discovery import TestSuite


def _suite(tmp_path: Path, name: str) -> TestSuite:
    p = tmp_path / f"{name}.m"
    p.write_bytes(b"; suite stub\n")
    return TestSuite(name=name, path=p, cases=[])


# ---------------------------------------------------------------------------
# find_changed_m_files — git status / diff parsing
# ---------------------------------------------------------------------------


def test_find_changed_returns_modified_m_files(tmp_path: Path) -> None:
    (tmp_path / "FOO.m").write_bytes(b"; stub\n")
    (tmp_path / "BAR.m").write_bytes(b"; stub\n")
    (tmp_path / "README.md").write_bytes(b"# stub\n")

    def runner(cmd, cwd):
        # `git status --porcelain` two-char status + space + path.
        return " M FOO.m\nA  BAR.m\n M README.md\n", 0

    paths = find_changed_m_files(tmp_path, runner=runner)
    names = sorted(p.name for p in paths)
    assert names == ["BAR.m", "FOO.m"]


def test_find_changed_includes_untracked_m_files(tmp_path: Path) -> None:
    (tmp_path / "NEW.m").write_bytes(b"; stub\n")

    def runner(cmd, cwd):
        return "?? NEW.m\n", 0

    paths = find_changed_m_files(tmp_path, runner=runner)
    assert [p.name for p in paths] == ["NEW.m"]


def test_find_changed_handles_renames(tmp_path: Path) -> None:
    """Porcelain renames look like ``R  OLD.m -> NEW.m`` — we pick the
    new name because that's what's on disk."""
    (tmp_path / "NEW.m").write_bytes(b"; stub\n")

    def runner(cmd, cwd):
        return "R  OLD.m -> NEW.m\n", 0

    paths = find_changed_m_files(tmp_path, runner=runner)
    assert [p.name for p in paths] == ["NEW.m"]


def test_find_changed_skips_deleted_files(tmp_path: Path) -> None:
    """A deleted file no longer exists on disk → can't be tested. Drop it."""
    def runner(cmd, cwd):
        return " D GONE.m\n", 0

    assert find_changed_m_files(tmp_path, runner=runner) == []


def test_find_changed_returns_empty_when_git_fails(tmp_path: Path) -> None:
    def runner(cmd, cwd):
        return "fatal: not a git repository\n", 128

    assert find_changed_m_files(tmp_path, runner=runner) == []


def test_find_changed_with_base_uses_diff(tmp_path: Path) -> None:
    """With a base revision, run ``git diff --name-only`` against it."""
    (tmp_path / "X.m").write_bytes(b"; stub\n")
    captured = {}

    def runner(cmd, cwd):
        captured["cmd"] = cmd
        return "X.m\n", 0

    paths = find_changed_m_files(tmp_path, base="main", runner=runner)
    assert [p.name for p in paths] == ["X.m"]
    assert "diff" in captured["cmd"]
    assert "main" in captured["cmd"]


def test_find_changed_filters_non_m_extensions(tmp_path: Path) -> None:
    (tmp_path / "X.py").write_bytes(b"# stub\n")
    (tmp_path / "X.m").write_bytes(b"; stub\n")

    def runner(cmd, cwd):
        return " M X.py\n M X.m\n", 0

    paths = find_changed_m_files(tmp_path, runner=runner)
    assert [p.name for p in paths] == ["X.m"]


# ---------------------------------------------------------------------------
# changed_to_suites — map changed .m files to suites via affinity
# ---------------------------------------------------------------------------


def test_changed_to_suites_resolves_source_to_suite(tmp_path: Path) -> None:
    foo_tst = _suite(tmp_path, "FOOTST")
    bar_tst = _suite(tmp_path, "BARTST")
    changed = [tmp_path / "FOO.m"]
    out = changed_to_suites(changed, [foo_tst, bar_tst])
    assert [s.name for s in out] == ["FOOTST"]


def test_changed_to_suites_dedups_when_two_changes_target_same_suite(
    tmp_path: Path,
) -> None:
    foo_tst = _suite(tmp_path, "FOOTST")
    changed = [tmp_path / "FOO.m", tmp_path / "FOOTST.m"]
    out = changed_to_suites(changed, [foo_tst])
    assert len(out) == 1
    assert out[0].name == "FOOTST"


def test_changed_to_suites_returns_all_suites_when_orphan_source(
    tmp_path: Path,
) -> None:
    """A changed source with no matching suite → fall back to running
    every suite, matching the ``m watch`` affinity convention."""
    a = _suite(tmp_path, "ATST")
    b = _suite(tmp_path, "BTST")
    out = changed_to_suites([tmp_path / "ORPHAN.m"], [a, b])
    assert {s.name for s in out} == {"ATST", "BTST"}


def test_changed_to_suites_empty_input_returns_empty(tmp_path: Path) -> None:
    a = _suite(tmp_path, "ATST")
    assert changed_to_suites([], [a]) == []


def test_changed_to_suites_suite_change_runs_only_itself(tmp_path: Path) -> None:
    a = _suite(tmp_path, "ATST")
    b = _suite(tmp_path, "BTST")
    out = changed_to_suites([tmp_path / "ATST.m"], [a, b])
    assert [s.name for s in out] == ["ATST"]
