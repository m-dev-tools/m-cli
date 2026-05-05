"""Integration of branch coverage into the coverage runner / CLI.

The runner must populate ``CoverageResult.branches`` only when the
caller asks for branch data (``with_branches=True``). The CLI
exposes this via ``--branch``; JSON / text output add the branch
totals when present.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from m_cli.coverage.cli import coverage_command
from m_cli.coverage.runner import run_coverage
from m_cli.engine import Connection

FAKE_CONN = Connection(host="vm-host", ssh_port=2222, ssh_user="vehu")


def _seed(tmp_path: Path) -> tuple[list[Path], list]:
    """Seed: GATE.m has IF on line 4 (one branch); GATETST drives it."""
    (tmp_path / "GATE.m").write_bytes(
        b"GATE ;c\n QUIT\nCHECK ;c\n IF X DO BAR\n QUIT\nBAR ;c\n QUIT\n"
    )
    (tmp_path / "GATETST.m").write_bytes(
        b"GATETST ;c\n D CHECK^GATE\n QUIT\ntFires(pass,fail) ;@TEST\n QUIT\n"
    )
    from m_cli.coverage.runner import discover_routines_and_suites
    return discover_routines_and_suites([tmp_path])


def test_run_coverage_omits_branches_by_default(tmp_path: Path) -> None:
    routines, suites = _seed(tmp_path)

    def fake_runner(cmd, stdin_text, env):
        return "", 0

    result = run_coverage(routines, suites, runner=fake_runner, conn=FAKE_CONN)
    # Branches are opt-in to keep the default fast for callers that
    # never look at branch data (e.g. existing tests).
    assert result.branches is None


def test_run_coverage_collects_branches_when_requested(tmp_path: Path) -> None:
    routines, suites = _seed(tmp_path)
    # CHECK on line 3 of GATE.m → IF on line 4 → offset 1.
    canned = '^ycov("GATE","CHECK",1)="1:0:0:1:1"\n'

    def fake_runner(cmd, stdin_text, env):
        return canned, 0

    result = run_coverage(
        routines, suites, runner=fake_runner, conn=FAKE_CONN, with_branches=True
    )
    assert result.branches is not None
    kinds = sorted(bc.point.kind for bc in result.branches)
    assert "if" in kinds
    # The IF was on a hit line → reached.
    if_branches = [bc for bc in result.branches if bc.point.kind == "if"]
    assert len(if_branches) == 1
    assert if_branches[0].reached is True


def test_branch_totals_helpers(tmp_path: Path) -> None:
    routines, suites = _seed(tmp_path)

    def fake_runner(cmd, stdin_text, env):
        return "", 0  # No hits → no branches reached.

    result = run_coverage(
        routines, suites, runner=fake_runner, conn=FAKE_CONN, with_branches=True
    )
    assert result.total_branches >= 1
    assert result.reached_branches == 0
    assert result.branch_percent == 0.0


# ---------------------------------------------------------------------------
# CLI wiring — `m coverage --branch`
# ---------------------------------------------------------------------------


def _make_args(**overrides) -> argparse.Namespace:
    defaults = dict(
        paths=[Path(".")],
        routines=[],
        tests=[],
        suites=None,
        format="text",
        uncovered=False,
        lines=False,
        branch=False,
        min_percent=None,
        quiet=True,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _patch_runner(monkeypatch: pytest.MonkeyPatch, stdout: str, rc: int = 0) -> None:
    def fake(cmd, stdin_text, env):
        return stdout, rc

    monkeypatch.setattr("m_cli.coverage.runner._default_runner", fake)


def _seed_with_routines_layout(tmp_path: Path) -> None:
    routines = tmp_path / "routines"
    routines.mkdir()
    tests = routines / "tests"
    tests.mkdir()
    (routines / "GATE.m").write_bytes(
        b"GATE ;c\n QUIT\nCHECK ;c\n IF X DO BAR\n QUIT\nBAR ;c\n QUIT\n"
    )
    (tests / "GATETST.m").write_bytes(
        b"GATETST ;c\n D CHECK^GATE\n QUIT\ntFires(pass,fail) ;@TEST\n QUIT\n"
    )


def test_cli_branch_flag_includes_branch_in_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _seed_with_routines_layout(tmp_path)
    _patch_runner(monkeypatch, '^ycov("GATE","CHECK",1)="1:0:0:1:1"\n')

    rc = coverage_command(_make_args(paths=[tmp_path], format="json", branch=True))
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "total_branches" in payload
    assert "reached_branches" in payload
    assert "branch_percent" in payload
    assert payload["total_branches"] >= 1
    assert payload["reached_branches"] == 1


def test_cli_branch_flag_text_output_shows_branch_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _seed_with_routines_layout(tmp_path)
    _patch_runner(monkeypatch, '^ycov("GATE","CHECK",1)="1:0:0:1:1"\n')

    coverage_command(_make_args(paths=[tmp_path], format="text", branch=True))
    out = capsys.readouterr().out
    # Text output should mention branches when --branch is set.
    assert "branch" in out.lower()


def test_cli_branch_flag_omitted_keeps_default_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Without --branch, JSON payload mustn't carry branch keys (size-stable)."""
    _seed_with_routines_layout(tmp_path)
    _patch_runner(monkeypatch, '^ycov("GATE","CHECK",1)="1:0:0:1:1"\n')

    coverage_command(_make_args(paths=[tmp_path], format="json"))
    payload = json.loads(capsys.readouterr().out)
    assert "total_branches" not in payload
