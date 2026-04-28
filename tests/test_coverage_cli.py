"""Integration-style tests for the `m coverage` CLI surface.

Drives ``coverage_command`` directly via argparse Namespace so we
exercise the full CLI path (resolution, discovery, run, output, exit
code) without spawning a subprocess. The runner is monkeypatched at
``m_cli.coverage.runner._default_runner`` so no live ydb is needed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from m_cli.coverage.cli import coverage_command


def _make_args(**overrides) -> argparse.Namespace:
    defaults = dict(
        paths=[Path(".")],
        routines=[],
        tests=[],
        suites=None,
        format="text",
        uncovered=False,
        lines=False,
        min_percent=None,
        quiet=True,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _seed(tmp_path: Path) -> None:
    routines = tmp_path / "routines"
    routines.mkdir()
    tests = routines / "tests"
    tests.mkdir()
    (routines / "HELLO.m").write_bytes(b"HELLO ;c\n QUIT\nGREET ;c\n QUIT\n")
    (tests / "HELLOTST.m").write_bytes(b"HELLOTST ;c\n D GREET^HELLO\n QUIT\n")


def _patch_runner(monkeypatch: pytest.MonkeyPatch, stdout: str = "", rc: int = 0) -> None:
    def fake(cmd, stdin_text, env):
        return stdout, rc

    monkeypatch.setattr("m_cli.coverage.runner._default_runner", fake)


def test_cli_returns_2_when_no_routines(tmp_path: Path) -> None:
    args = _make_args(paths=[tmp_path])
    rc = coverage_command(args)
    assert rc == 2


def test_cli_returns_2_when_no_suites(tmp_path: Path) -> None:
    """A routine but no suites → can't run coverage."""
    (tmp_path / "HELLO.m").write_bytes(b"HELLO ;c\n QUIT\nGREET ;c\n QUIT\n")
    rc = coverage_command(_make_args(paths=[tmp_path]))
    assert rc == 2


def test_cli_runs_with_full_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _seed(tmp_path)
    _patch_runner(monkeypatch, '^ycov("HELLO","GREET",1)="1:0:0:1:1"\n', rc=0)

    rc = coverage_command(_make_args(paths=[tmp_path]))
    assert rc == 0

    out = capsys.readouterr().out
    assert "100.0%" in out


def test_cli_min_percent_threshold_fails_when_below(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two production labels, one covered → 50% < 80% threshold → exit 1."""
    routines = tmp_path / "routines"
    routines.mkdir()
    (routines / "tests").mkdir()
    (routines / "HELLO.m").write_bytes(
        b"HELLO ;c\n QUIT\nA ;c\n QUIT\nB ;c\n QUIT\n"
    )
    (routines / "tests" / "HELLOTST.m").write_bytes(
        b"HELLOTST ;c\n D A^HELLO\n QUIT\n"
    )
    # HELLO.m has labels on lines 1,3,5; A is on line 3 with QUIT on
    # line 4 (offset 1 from A). Trace says A's offset 1 was hit.
    _patch_runner(monkeypatch, '^ycov("HELLO","A",1)="1:0:0:1:1"\n', rc=0)

    rc = coverage_command(_make_args(paths=[tmp_path], min_percent=80.0))
    assert rc == 1


def test_cli_min_percent_threshold_passes_when_met(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path)
    _patch_runner(monkeypatch, '^ycov("HELLO","GREET",1)="1:0:0:1:1"\n', rc=0)

    rc = coverage_command(_make_args(paths=[tmp_path], min_percent=100.0))
    assert rc == 0


def test_cli_unknown_suite_filter_returns_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path)
    _patch_runner(monkeypatch)

    rc = coverage_command(_make_args(paths=[tmp_path], suites="DOESNOTEXIST"))
    assert rc == 2


def test_cli_json_output_is_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _seed(tmp_path)
    _patch_runner(monkeypatch, '^ycov("HELLO","GREET",1)="1:0:0:1:1"\n', rc=0)

    coverage_command(_make_args(paths=[tmp_path], format="json"))
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 1
    assert payload["covered"] == 1
    assert payload["percent"] == 100.0


def test_cli_propagates_runner_returncode_as_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ydb non-zero exit → m coverage exit 1 even if some labels covered."""
    _seed(tmp_path)
    _patch_runner(monkeypatch, '^ycov("HELLO","GREET",1)="1:0:0:1:1"\n', rc=2)

    rc = coverage_command(_make_args(paths=[tmp_path]))
    assert rc == 1
