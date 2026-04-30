"""Tests for ``m lint`` baseline-file support.

Covers loading, writing, filtering, and the ancestor-walk discovery
logic. CLI integration (``--baseline``, ``--update-baseline``,
``--no-baseline``) is exercised via subprocess in the integration
test below.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from m_cli.lint.baseline import (
    DEFAULT_BASELINE_NAME,
    SCHEMA_VERSION,
    BaselineEntry,
    filter_baselined,
    find_baseline,
    load_baseline,
    write_baseline,
)
from m_cli.lint.diagnostic import Diagnostic, Severity


def _diag(
    rule_id: str, path: Path, line: int = 1, col: int = 1, message: str = "msg"
) -> Diagnostic:
    return Diagnostic(
        rule_id=rule_id,
        severity=Severity.INFO,
        message=message,
        path=path,
        line=line,
        column=col,
        column_end=col + 1,
    )


# ---------------------------------------------------------------------------
# write_baseline / load_baseline round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_write_then_load(self, tmp_path: Path) -> None:
        bl = tmp_path / DEFAULT_BASELINE_NAME
        diags = [
            _diag("M-MOD-034", tmp_path / "a.m", line=2, message="hi"),
            _diag("M-MOD-034", tmp_path / "a.m", line=4, message="bye"),
        ]
        n = write_baseline(bl, diags, tmp_path)
        assert n == 2
        entries = load_baseline(bl)
        assert len(entries) == 2
        assert {e.rule_id for e in entries} == {"M-MOD-034"}
        assert all(e.path == "a.m" for e in entries)

    def test_baseline_file_uses_posix_separators(self, tmp_path: Path) -> None:
        nested = tmp_path / "sub" / "deep"
        nested.mkdir(parents=True)
        f = nested / "x.m"
        f.write_bytes(b"x")
        bl = tmp_path / DEFAULT_BASELINE_NAME
        write_baseline(bl, [_diag("M-MOD-034", f)], tmp_path)
        data = json.loads(bl.read_text())
        assert data["entries"][0]["path"] == "sub/deep/x.m"
        # Not the OS-specific form (avoids Windows backslashes leaking in).
        assert "\\" not in data["entries"][0]["path"]

    def test_schema_version_is_pinned(self, tmp_path: Path) -> None:
        bl = tmp_path / DEFAULT_BASELINE_NAME
        write_baseline(bl, [], tmp_path)
        data = json.loads(bl.read_text())
        assert data["version"] == SCHEMA_VERSION

    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_baseline(tmp_path / "nope.json") == []

    def test_load_rejects_unknown_schema(self, tmp_path: Path) -> None:
        bl = tmp_path / DEFAULT_BASELINE_NAME
        bl.write_text(json.dumps({"version": 99, "entries": []}))
        with pytest.raises(ValueError, match="schema version"):
            load_baseline(bl)

    def test_load_rejects_malformed_entry(self, tmp_path: Path) -> None:
        bl = tmp_path / DEFAULT_BASELINE_NAME
        bl.write_text(
            json.dumps(
                {"version": SCHEMA_VERSION, "entries": [{"path": "x", "line": "abc"}]}
            )
        )
        with pytest.raises(ValueError, match="malformed"):
            load_baseline(bl)

    def test_entries_sorted_for_stable_diffs(self, tmp_path: Path) -> None:
        bl = tmp_path / DEFAULT_BASELINE_NAME
        diags = [
            _diag("M-MOD-031", tmp_path / "z.m", line=10),
            _diag("M-MOD-034", tmp_path / "a.m", line=2),
            _diag("M-MOD-034", tmp_path / "a.m", line=1),
        ]
        write_baseline(bl, diags, tmp_path)
        data = json.loads(bl.read_text())
        paths_lines = [(e["path"], e["line"]) for e in data["entries"]]
        assert paths_lines == sorted(paths_lines)


# ---------------------------------------------------------------------------
# filter_baselined
# ---------------------------------------------------------------------------


class TestFilterBaselined:
    def test_drops_matching_diagnostic(self, tmp_path: Path) -> None:
        f = tmp_path / "x.m"
        f.write_bytes(b"x")
        d = _diag("M-MOD-034", f, line=5, message="hello")
        bl = [
            BaselineEntry(
                path="x.m",
                line=5,
                rule_id="M-MOD-034",
                message_hash=_hash_for("hello"),
            )
        ]
        out, suppressed = filter_baselined([d], bl, tmp_path)
        assert out == []
        assert suppressed == 1

    def test_keeps_diagnostic_with_different_line(self, tmp_path: Path) -> None:
        f = tmp_path / "x.m"
        f.write_bytes(b"x")
        d = _diag("M-MOD-034", f, line=7, message="hello")
        bl = [
            BaselineEntry(
                path="x.m",
                line=5,
                rule_id="M-MOD-034",
                message_hash=_hash_for("hello"),
            )
        ]
        out, suppressed = filter_baselined([d], bl, tmp_path)
        assert out == [d]
        assert suppressed == 0

    def test_keeps_diagnostic_with_different_message(self, tmp_path: Path) -> None:
        f = tmp_path / "x.m"
        f.write_bytes(b"x")
        d = _diag("M-MOD-034", f, line=5, message="DIFFERENT")
        bl = [
            BaselineEntry(
                path="x.m",
                line=5,
                rule_id="M-MOD-034",
                message_hash=_hash_for("hello"),
            )
        ]
        out, suppressed = filter_baselined([d], bl, tmp_path)
        assert out == [d]
        assert suppressed == 0

    def test_empty_baseline_passes_through(self, tmp_path: Path) -> None:
        f = tmp_path / "x.m"
        f.write_bytes(b"x")
        d = _diag("M-MOD-034", f)
        out, suppressed = filter_baselined([d], [], tmp_path)
        assert out == [d]
        assert suppressed == 0


# ---------------------------------------------------------------------------
# find_baseline (ancestor walk)
# ---------------------------------------------------------------------------


class TestFindBaseline:
    def test_finds_in_current_directory(self, tmp_path: Path) -> None:
        bl = tmp_path / DEFAULT_BASELINE_NAME
        bl.write_text('{"version": 1, "entries": []}')
        assert find_baseline(tmp_path) == bl

    def test_walks_up_to_find_baseline(self, tmp_path: Path) -> None:
        bl = tmp_path / DEFAULT_BASELINE_NAME
        bl.write_text('{"version": 1, "entries": []}')
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        assert find_baseline(nested) == bl

    def test_stops_at_git_boundary(self, tmp_path: Path) -> None:
        # Outer baseline that should NOT be found.
        outer = tmp_path / DEFAULT_BASELINE_NAME
        outer.write_text('{"version": 1, "entries": []}')

        # Inner project with its own .git → walk stops here.
        inner = tmp_path / "inner"
        inner.mkdir()
        (inner / ".git").mkdir()  # boundary marker

        nested = inner / "src"
        nested.mkdir()
        # No baseline in inner/, but we should NOT escape into outer.
        assert find_baseline(nested) is None

    def test_no_baseline_returns_none(self, tmp_path: Path) -> None:
        # Mark tmp_path as a git boundary so the ancestor walk doesn't
        # escape into a real baseline file in /tmp or further up.
        (tmp_path / ".git").mkdir()
        assert find_baseline(tmp_path) is None


# ---------------------------------------------------------------------------
# Helper for tests
# ---------------------------------------------------------------------------


def _hash_for(message: str) -> str:
    """Compute the same short hash baseline.py uses, for test fixtures."""
    import hashlib

    return hashlib.sha1(message.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# CLI integration — subprocess
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    def test_update_baseline_then_filter(self, tmp_path: Path) -> None:
        """End-to-end: capture, then re-lint and confirm suppression.

        Shells out via ``python -m m_cli`` rather than the installed
        ``m`` script so the test runs in any checkout without relying
        on the editable-install entry point being on PATH.
        """
        f = tmp_path / "demo.m"
        f.write_bytes(b"DEMO ; legacy\n SET X=X+1\n QUIT\n")

        # First run: capture findings into baseline.
        r1 = subprocess.run(
            [
                sys.executable,
                "-m",
                "m_cli",
                "lint",
                str(f),
                "--rules=default",
                "--update-baseline",
            ],
            cwd=tmp_path,
            capture_output=True,
        )
        assert r1.returncode == 0
        baseline = tmp_path / DEFAULT_BASELINE_NAME
        assert baseline.exists()
        data = json.loads(baseline.read_text())
        # The M-MOD-034 SET X=X+1 finding should be captured.
        assert any(e["rule_id"] == "M-MOD-034" for e in data["entries"])

        # Second run: same source, baseline applied → no findings.
        r2 = subprocess.run(
            [sys.executable, "-m", "m_cli", "lint", str(f), "--rules=default"],
            cwd=tmp_path,
            capture_output=True,
        )
        assert r2.returncode == 0
        # stdout (the diagnostics stream) is empty when everything is
        # suppressed.
        assert r2.stdout == b""
        # Summary on stderr mentions the baseline suppression.
        assert b"suppressed by baseline" in r2.stderr

    def test_no_baseline_disables_filtering(self, tmp_path: Path) -> None:
        f = tmp_path / "demo.m"
        f.write_bytes(b"DEMO ; legacy\n SET X=X+1\n QUIT\n")

        # Capture baseline.
        subprocess.run(
            [
                sys.executable,
                "-m",
                "m_cli",
                "lint",
                str(f),
                "--rules=default",
                "--update-baseline",
            ],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        # --no-baseline → suppression skipped → original finding shows.
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "m_cli",
                "lint",
                str(f),
                "--rules=default",
                "--no-baseline",
            ],
            cwd=tmp_path,
            capture_output=True,
        )
        assert b"M-MOD-034" in r.stdout
