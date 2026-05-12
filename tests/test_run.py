"""Tests for ``m run`` — entryref launcher routed via the active engine.

The runner and engine are both injectable so the unit tests don't need
a live ydb. Real-engine smoke is exercised manually.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from m_cli.engine import EngineNotConfigured
from m_cli.run import run_command
from m_cli.run.runner import (
    EntryrefError,
    build_command,
    build_env,
    parse_entryref,
    resolve_ydb_binary,
)

# ---------------------------------------------------------- entryref parsing


def test_parse_entryref_routine_only():
    assert parse_entryref("HELLO") == ("", "HELLO")


def test_parse_entryref_label_at_routine():
    assert parse_entryref("EN^HELLO") == ("EN", "HELLO")


def test_parse_entryref_rejects_empty():
    with pytest.raises(EntryrefError):
        parse_entryref("")


def test_parse_entryref_rejects_lowercase_routine():
    # M is case-insensitive on commands but the routine *file* convention
    # is uppercase; ydb -run accepts case-insensitively but we normalise.
    label, rtn = parse_entryref("hello")
    assert rtn == "HELLO"


def test_parse_entryref_rejects_special_chars():
    with pytest.raises(EntryrefError):
        parse_entryref("foo bar")
    with pytest.raises(EntryrefError):
        parse_entryref("HELLO;")


def test_parse_entryref_rejects_leading_digit():
    with pytest.raises(EntryrefError):
        parse_entryref("1HELLO")


def test_parse_entryref_truncates_to_eight_routine_chars():
    label, rtn = parse_entryref("VERYLONGROUTINENAME")
    assert rtn == "VERYLONG"


# -------- legacy helpers (m_cli.run.runner kept for library backcompat) ---


def test_resolve_ydb_binary_via_explicit_YDB(monkeypatch, tmp_path):
    bin_ = tmp_path / "myydb"
    bin_.write_text("#!/bin/sh\nexit 0\n")
    bin_.chmod(0o755)
    monkeypatch.setenv("YDB", str(bin_))
    assert resolve_ydb_binary() == str(bin_)


def test_resolve_ydb_binary_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("YDB", raising=False)
    monkeypatch.delenv("ydb_dist", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert resolve_ydb_binary() is None


def test_build_env_routines_prepends(monkeypatch):
    monkeypatch.setenv("ydb_routines", "/parent/routines")
    env = build_env(routines=["./routines"])
    assert env["ydb_routines"].startswith("./routines")
    assert "/parent/routines" in env["ydb_routines"]


def test_build_command_top_of_routine():
    assert build_command("/usr/bin/ydb", "", "HELLO", []) == [
        "/usr/bin/ydb",
        "-run",
        "^HELLO",
    ]


def test_build_command_extra_args_passed_through():
    cmd = build_command("/usr/bin/ydb", "", "HELLO", ["arg1", "arg2"])
    assert cmd[-2:] == ["arg1", "arg2"]
    assert "^HELLO" in cmd


# ------------------------------------------------------------ run_command rc


@dataclass
class FakeEngine:
    """Records calls to stage_routines + build_run_cmd. Used in lieu of a real engine."""

    stage: str = "/stage/path"
    cmd_to_return: list[str] = field(default_factory=lambda: ["mumps", "-run", "^HELLO"])
    captured: dict = field(default_factory=dict)

    def stage_routines(self, start: Path) -> str:
        self.captured["start"] = start
        return self.stage

    def build_run_cmd(
        self, entryref: str, extras: list[str], stage: str
    ) -> list[str]:
        self.captured["entryref"] = entryref
        self.captured["extras"] = extras
        self.captured["stage"] = stage
        return self.cmd_to_return


def _ns(**kw) -> argparse.Namespace:
    base = {"entryref": "HELLO", "routines": None, "args": [], "quiet": True}
    base.update(kw)
    return argparse.Namespace(**base)


def _patch_engine(monkeypatch, engine):
    monkeypatch.setattr("m_cli.run.cli.detect_engine", lambda: engine)


def test_run_command_returns_zero_on_success(monkeypatch):
    fake = FakeEngine()
    _patch_engine(monkeypatch, fake)
    rc = run_command(_ns(), runner=lambda cmd: 0)
    assert rc == 0
    assert fake.captured["entryref"] == "^HELLO"


def test_run_command_passes_through_engine_rc(monkeypatch):
    _patch_engine(monkeypatch, FakeEngine())
    rc = run_command(_ns(), runner=lambda cmd: 47)
    assert rc == 47


def test_run_command_label_entryref(monkeypatch):
    fake = FakeEngine()
    _patch_engine(monkeypatch, fake)
    run_command(_ns(entryref="EN^HELLO"), runner=lambda c: 0)
    assert fake.captured["entryref"] == "EN^HELLO"


def test_run_command_passes_extra_args_to_engine(monkeypatch):
    fake = FakeEngine()
    _patch_engine(monkeypatch, fake)
    run_command(_ns(args=["--input", "data.csv"]), runner=lambda c: 0)
    assert fake.captured["extras"] == ["--input", "data.csv"]


def test_run_command_routines_flag_prepends_stage(monkeypatch):
    fake = FakeEngine(stage="/proj/routines")
    _patch_engine(monkeypatch, fake)
    run_command(
        _ns(routines=["/extra/path"]), runner=lambda c: 0
    )
    assert fake.captured["stage"] == "/extra/path /proj/routines"


def test_run_command_no_engine_returns_one(monkeypatch, capsys):
    # Domain failure per CLI-UX guide §3.7 (was: usage error / exit 2).
    def boom() -> None:
        raise EngineNotConfigured("no transport detected")

    monkeypatch.setattr("m_cli.run.cli.detect_engine", boom)
    rc = run_command(_ns(), runner=lambda c: 0)
    err = capsys.readouterr().err
    assert rc == 1
    assert "transport" in err.lower() or "engine" in err.lower()


def test_run_command_invalid_entryref_returns_two(monkeypatch, capsys):
    _patch_engine(monkeypatch, FakeEngine())
    rc = run_command(_ns(entryref="1bad"), runner=lambda c: 0)
    err = capsys.readouterr().err
    assert rc == 2
    assert "1bad" in err or "entryref" in err.lower()
