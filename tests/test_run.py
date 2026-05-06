"""Tests for ``m run`` — thin ``ydb -run`` wrapper.

The runner is injectable so the unit tests don't need a live ydb.
Real-engine smoke is exercised manually.
"""

from __future__ import annotations

import argparse

import pytest

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


# -------------------------------------------------------- ydb binary resolution


def test_resolve_ydb_binary_via_explicit_YDB(monkeypatch, tmp_path):
    bin_ = tmp_path / "myydb"
    bin_.write_text("#!/bin/sh\nexit 0\n")
    bin_.chmod(0o755)
    monkeypatch.setenv("YDB", str(bin_))
    assert resolve_ydb_binary() == str(bin_)


def test_resolve_ydb_binary_via_ydb_dist(monkeypatch, tmp_path):
    bin_ = tmp_path / "ydb"
    bin_.write_text("#!/bin/sh\nexit 0\n")
    bin_.chmod(0o755)
    monkeypatch.delenv("YDB", raising=False)
    monkeypatch.setenv("ydb_dist", str(tmp_path))
    assert resolve_ydb_binary() == str(bin_)


def test_resolve_ydb_binary_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("YDB", raising=False)
    monkeypatch.delenv("ydb_dist", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert resolve_ydb_binary() is None


# ------------------------------------------------------------- env composition


def test_build_env_inherits_parent(monkeypatch):
    monkeypatch.setenv("ydb_routines", "/parent/routines")
    monkeypatch.setenv("MY_FLAG", "1")
    env = build_env(routines=None)
    assert env["ydb_routines"] == "/parent/routines"
    assert env["MY_FLAG"] == "1"


def test_build_env_routines_prepends(monkeypatch):
    monkeypatch.setenv("ydb_routines", "/parent/routines")
    env = build_env(routines=["./routines"])
    assert env["ydb_routines"].startswith("./routines")
    assert "/parent/routines" in env["ydb_routines"]


def test_build_env_routines_when_unset(monkeypatch):
    monkeypatch.delenv("ydb_routines", raising=False)
    env = build_env(routines=["./routines"])
    assert env["ydb_routines"] == "./routines"


def test_build_env_multiple_routines_paths_join_with_space(monkeypatch):
    monkeypatch.delenv("ydb_routines", raising=False)
    env = build_env(routines=["./a", "./b"])
    assert env["ydb_routines"] == "./a ./b"


# --------------------------------------------------------- command composition


def test_build_command_top_of_routine():
    assert build_command("/usr/bin/ydb", "", "HELLO", []) == [
        "/usr/bin/ydb",
        "-run",
        "^HELLO",
    ]


def test_build_command_label_entryref():
    assert build_command("/usr/bin/ydb", "EN", "HELLO", []) == [
        "/usr/bin/ydb",
        "-run",
        "EN^HELLO",
    ]


def test_build_command_extra_args_passed_through():
    cmd = build_command("/usr/bin/ydb", "", "HELLO", ["arg1", "arg2"])
    assert cmd[-2:] == ["arg1", "arg2"]
    assert "^HELLO" in cmd


# ------------------------------------------------------------ run_command rc


def _ns(**kw) -> argparse.Namespace:
    base = {"entryref": "HELLO", "routines": None, "args": [], "quiet": True}
    base.update(kw)
    return argparse.Namespace(**base)


def test_run_command_returns_zero_on_success(monkeypatch, tmp_path):
    # Stub resolve_ydb_binary so the test doesn't need real ydb.
    bin_ = tmp_path / "ydb"
    bin_.write_text("#!/bin/sh\nexit 0\n")
    bin_.chmod(0o755)
    monkeypatch.setenv("YDB", str(bin_))
    captured: dict = {}

    def fake_runner(cmd, env):
        captured["cmd"] = cmd
        return 0

    rc = run_command(_ns(), runner=fake_runner)
    assert rc == 0
    assert captured["cmd"][1:] == ["-run", "^HELLO"]


def test_run_command_passes_through_engine_rc(monkeypatch, tmp_path):
    bin_ = tmp_path / "ydb"
    bin_.write_text("#!/bin/sh\nexit 0\n")
    bin_.chmod(0o755)
    monkeypatch.setenv("YDB", str(bin_))

    def fake_runner(cmd, env):
        return 47

    rc = run_command(_ns(), runner=fake_runner)
    assert rc == 47


def test_run_command_no_ydb_returns_two(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("YDB", raising=False)
    monkeypatch.delenv("ydb_dist", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    rc = run_command(_ns(), runner=lambda c, e: 0)
    err = capsys.readouterr().err
    assert rc == 2
    assert "ydb" in err.lower()


def test_run_command_invalid_entryref_returns_two(capsys):
    rc = run_command(_ns(entryref="1bad"), runner=lambda c, e: 0)
    err = capsys.readouterr().err
    assert rc == 2
    assert "1bad" in err or "entryref" in err.lower()
