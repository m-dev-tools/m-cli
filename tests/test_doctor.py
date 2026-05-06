"""Tests for m doctor — environment diagnostics.

`m doctor` reports the health of the M development environment:
- `$ydb_dist` set and points at a real directory with a `ydb` binary
- `$ydb_routines` set
- tree-sitter-m parser available (can parse a trivial routine)
- m-standard keyword TSV files load
- `ydb` binary resolvable

Each check returns a `Check` record with status `ok` / `warn` / `fail`,
a one-line message, and an optional hint. The command exits 1 if any
check is `fail`, 0 otherwise (`warn` does not fail the run).
"""

from __future__ import annotations

import argparse

from m_cli.doctor import doctor_command
from m_cli.doctor.checks import (
    Check,
    Status,
    check_keywords,
    check_parser,
    check_ydb_binary,
    check_ydb_dist,
    check_ydb_routines,
    run_all_checks,
)

# ---------------------------------------------------------------- Check shape


def test_check_dataclass_carries_status_and_message():
    c = Check(name="ydb_dist", status=Status.OK, message="set", hint=None)
    assert c.name == "ydb_dist"
    assert c.status is Status.OK
    assert c.message == "set"
    assert c.hint is None


def test_status_enum_has_three_levels():
    assert {Status.OK, Status.WARN, Status.FAIL} == set(Status)


# ------------------------------------------------------------- Per-check tests


def test_check_ydb_dist_unset_is_warn(monkeypatch):
    monkeypatch.delenv("ydb_dist", raising=False)
    c = check_ydb_dist()
    assert c.name == "ydb_dist"
    assert c.status is Status.WARN
    assert c.hint is not None  # actionable


def test_check_ydb_dist_points_at_missing_dir_is_fail(monkeypatch, tmp_path):
    bogus = tmp_path / "does-not-exist"
    monkeypatch.setenv("ydb_dist", str(bogus))
    c = check_ydb_dist()
    assert c.status is Status.FAIL
    assert "does-not-exist" in c.message or "missing" in c.message.lower()


def test_check_ydb_dist_dir_without_ydb_binary_is_warn(monkeypatch, tmp_path):
    monkeypatch.setenv("ydb_dist", str(tmp_path))
    c = check_ydb_dist()
    # Directory exists but no `ydb` binary inside — warn, not fail
    assert c.status is Status.WARN
    assert c.hint is not None


def test_check_ydb_dist_with_binary_is_ok(monkeypatch, tmp_path):
    binary = tmp_path / "ydb"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    monkeypatch.setenv("ydb_dist", str(tmp_path))
    c = check_ydb_dist()
    assert c.status is Status.OK


def test_check_ydb_routines_unset_is_warn(monkeypatch):
    monkeypatch.delenv("ydb_routines", raising=False)
    c = check_ydb_routines()
    assert c.status is Status.WARN
    assert c.hint is not None


def test_check_ydb_routines_set_is_ok(monkeypatch):
    monkeypatch.setenv("ydb_routines", ".")
    c = check_ydb_routines()
    assert c.status is Status.OK


def test_check_parser_returns_ok_when_parser_works():
    # The parser ships in this repo — should always work.
    c = check_parser()
    assert c.status is Status.OK


def test_check_keywords_returns_ok_when_tsvs_load():
    c = check_keywords()
    assert c.status is Status.OK
    # Message includes some count
    assert any(ch.isdigit() for ch in c.message)


def test_check_ydb_binary_missing_is_warn(monkeypatch, tmp_path):
    # Empty PATH, no ydb_dist
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("ydb_dist", raising=False)
    monkeypatch.delenv("YDB", raising=False)
    c = check_ydb_binary()
    assert c.status is Status.WARN


def test_check_ydb_binary_via_explicit_YDB(monkeypatch, tmp_path):
    binary = tmp_path / "myydb"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    monkeypatch.setenv("YDB", str(binary))
    c = check_ydb_binary()
    assert c.status is Status.OK
    assert "myydb" in c.message


# ----------------------------------------------------------- run_all_checks()


def test_run_all_checks_returns_list_of_checks():
    checks = run_all_checks()
    assert isinstance(checks, list)
    assert all(isinstance(c, Check) for c in checks)
    # At least the five named checks
    names = {c.name for c in checks}
    assert {
        "ydb_dist",
        "ydb_routines",
        "parser",
        "keywords",
        "ydb_binary",
    }.issubset(names)


# ------------------------------------------------------------- CLI / exit code


def _ns(format: str = "text", **kw) -> argparse.Namespace:
    ns = argparse.Namespace(format=format)
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def test_doctor_cli_exits_zero_when_all_ok(monkeypatch, tmp_path, capsys):
    # Force every check to OK by setting a clean env.
    binary = tmp_path / "ydb"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    monkeypatch.setenv("ydb_dist", str(tmp_path))
    monkeypatch.setenv("ydb_routines", ".")
    monkeypatch.setenv("PATH", str(tmp_path))
    rc = doctor_command(_ns())
    out = capsys.readouterr().out
    assert rc == 0
    assert "ydb_dist" in out
    assert "OK" in out  # human format shows status


def test_doctor_cli_exits_one_when_any_fail(monkeypatch, tmp_path, capsys):
    bogus = tmp_path / "no-such-dir"
    monkeypatch.setenv("ydb_dist", str(bogus))
    rc = doctor_command(_ns())
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out


def test_doctor_cli_warn_does_not_fail_run(monkeypatch, capsys):
    # Unset ydb_dist → WARN, but no FAIL anywhere.
    monkeypatch.delenv("ydb_dist", raising=False)
    monkeypatch.delenv("ydb_routines", raising=False)
    monkeypatch.delenv("YDB", raising=False)
    rc = doctor_command(_ns())
    assert rc == 0  # warns only


def test_doctor_cli_json_format(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ydb_dist", str(tmp_path))
    monkeypatch.setenv("ydb_routines", ".")
    rc = doctor_command(_ns(format="json"))
    out = capsys.readouterr().out
    import json

    payload = json.loads(out)
    assert isinstance(payload, list)
    assert all("name" in c and "status" in c for c in payload)
    assert rc in (0, 1)
