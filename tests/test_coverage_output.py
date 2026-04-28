"""Tests for ``m_cli.coverage.output`` — text / json formatters."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from m_cli.coverage.output import write_output
from m_cli.coverage.runner import CoverageResult, LabelCoverage


def _result() -> CoverageResult:
    h = Path("/p/HELLO.m")
    m = Path("/p/MATH.m")
    labels = [
        LabelCoverage(routine="HELLO", label="GREET", path=h, line=3, covered=True),
        LabelCoverage(routine="HELLO", label="SHOUT", path=h, line=5, covered=False),
        LabelCoverage(routine="MATH", label="ADD", path=m, line=3, covered=True),
    ]
    return CoverageResult(
        labels=labels,
        suites_run=["HELLOTST"],
        returncode=0,
        stdout="",
        by_routine={"HELLO": (1, 2), "MATH": (1, 1)},
    )


def test_text_output_prints_per_routine_table(capsys: pytest.CaptureFixture) -> None:
    write_output(_result(), fmt="text")
    out = capsys.readouterr().out
    assert "HELLO" in out
    assert "MATH" in out
    assert "Total" in out
    # 2 of 3 covered = 66.7%
    assert "66.7%" in out


def test_text_output_uncovered_only(capsys: pytest.CaptureFixture) -> None:
    write_output(_result(), fmt="text", uncovered_only=True)
    out = capsys.readouterr().out
    assert "Uncovered labels (1 of 3)" in out
    assert "SHOUT^HELLO" in out
    # Covered labels should NOT appear in the uncovered-only output.
    assert "GREET^HELLO" not in out


def test_json_output_is_parseable_and_complete(capsys: pytest.CaptureFixture) -> None:
    write_output(_result(), fmt="json")
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 3
    assert payload["covered"] == 2
    assert payload["percent"] == 66.7
    assert payload["suites_run"] == ["HELLOTST"]
    by_routine_names = [r["routine"] for r in payload["by_routine"]]
    assert by_routine_names == ["HELLO", "MATH"]
    # Per-label data is present and carries covered flag.
    assert any(lab["covered"] is False for lab in payload["labels"])


def test_unknown_format_raises() -> None:
    with pytest.raises(ValueError, match="unknown coverage output format"):
        write_output(_result(), fmt="xml")
