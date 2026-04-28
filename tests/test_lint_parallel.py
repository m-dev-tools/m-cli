"""Tests for parallel `m lint` execution.

The CLI exposes a ``--jobs N`` flag. Single-process and multi-process
modes must produce identical diagnostics.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from m_cli.cli import main

SAMPLE_SRCS = {
    "ATST.m": b"ATST ;trivial\n quit\n",
    "BAD1.m": b"foo \n quit \n",  # trailing blanks → M-XINDX-013
    "WRONG.m": b"OTHERNAME ;wrong first label\n quit\n",  # M-XINDX-017
    "LONG.m": b"long ;long line\n write " + (b"x" * 250) + b",!\n quit\n",
    "OK.m": b"ok ;clean\n new x\n quit\n",
}


def _seed(tmp_path: Path) -> Path:
    for name, src in SAMPLE_SRCS.items():
        (tmp_path / name).write_bytes(src)
    return tmp_path


def test_serial_and_parallel_produce_same_diagnostics(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _seed(tmp_path)
    rc1 = main(["lint", "--jobs", "1", "--format", "json", str(tmp_path)])
    serial_out = capsys.readouterr().out

    rc2 = main(["lint", "--jobs", "4", "--format", "json", str(tmp_path)])
    parallel_out = capsys.readouterr().out

    assert rc1 == rc2

    # Diagnostics are sorted before output, so JSON should match exactly.
    serial = json.loads(serial_out)
    parallel = json.loads(parallel_out)
    assert serial == parallel


def test_jobs_default_is_picked_up_from_cpu_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path)
    captured = {}
    import m_cli.lint.cli as cli_mod

    real = cli_mod._run_parallel

    def spy(files, rule_filter, lint_unparseable, jobs, config):
        captured["jobs"] = jobs
        return real(files, rule_filter, lint_unparseable, jobs, config)

    monkeypatch.setattr(cli_mod, "_run_parallel", spy)
    main(["lint", "--quiet", str(tmp_path)])
    # Default of os.cpu_count() should be > 0; we can't predict its exact value
    # but we can check that it was passed through as a positive int.
    assert captured["jobs"] >= 1


def test_jobs_invalid_value_returns_2(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _seed(tmp_path)
    rc = main(["lint", "--jobs", "0", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "--jobs" in err.lower()


def test_jobs_one_does_not_spawn_a_pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--jobs 1 should take the in-process serial path."""
    _seed(tmp_path)
    import m_cli.lint.cli as cli_mod

    parallel_called = {"yes": False}

    def spy(*args, **kwargs):
        parallel_called["yes"] = True
        raise AssertionError("parallel path must not be taken with --jobs 1")

    monkeypatch.setattr(cli_mod, "_run_parallel", spy)
    rc = main(["lint", "--jobs", "1", "--quiet", str(tmp_path)])
    assert rc in (0, 1)
    assert parallel_called["yes"] is False


def test_parallel_handles_unreadable_file(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """A file that disappears between collection and worker read should not crash."""
    _seed(tmp_path)
    bad = tmp_path / "GHOST.m"
    bad.write_bytes(b"hello\n quit\n")
    bad.chmod(0o000)
    try:
        rc = main(["lint", "--jobs", "2", str(tmp_path)])
        # Either 0 (no fatal) or 1 (findings ≥ threshold) is acceptable.
        # The point is: don't crash.
        assert rc in (0, 1)
    finally:
        bad.chmod(0o644)
