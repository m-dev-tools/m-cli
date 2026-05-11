"""Tests for ``m build`` — warm-compile a directory of M routines.

The compiler subprocess is injectable (``runner=...``) so unit tests
exercise discovery, error aggregation, and exit-code semantics without
needing real ydb.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from m_cli.build import build_command
from m_cli.build.runner import (
    BuildResult,
    discover_files,
)

# --------------------------------------------------------------- file discovery


def test_discover_files_finds_dot_m(tmp_path):
    (tmp_path / "FOO.m").write_text("FOO ; quit\n Q\n")
    (tmp_path / "BAR.m").write_text("BAR ; quit\n Q\n")
    (tmp_path / "README.md").write_text("not m source")
    files = discover_files([tmp_path])
    names = [f.name for f in files]
    assert names == ["BAR.m", "FOO.m"]


def test_discover_files_recurses(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "DEEP.m").write_text("DEEP ; quit\n Q\n")
    files = discover_files([tmp_path])
    assert (tmp_path / "src" / "DEEP.m") in files


def test_discover_files_accepts_explicit_files(tmp_path):
    f = tmp_path / "X.m"
    f.write_text("X ; quit\n Q\n")
    assert discover_files([f]) == [f]


def test_discover_files_skips_non_m(tmp_path):
    (tmp_path / "FOO.m").write_text("FOO ; quit\n Q\n")
    (tmp_path / "FOO.o").write_bytes(b"\x00\x01\x02")
    (tmp_path / "FOO.bak").write_text("backup")
    files = discover_files([tmp_path])
    assert [f.name for f in files] == ["FOO.m"]


def test_discover_files_dedupes(tmp_path):
    f = tmp_path / "X.m"
    f.write_text("X ; quit\n Q\n")
    files = discover_files([tmp_path, f, tmp_path])
    assert files.count(f) == 1


# ----------------------------------------------------------- BuildResult shape


def test_build_result_has_status_fields():
    r = BuildResult(file=Path("X.m"), returncode=0, output="", ok=True)
    assert r.ok is True
    assert r.returncode == 0


# ------------------------------------------------------------- build_command


def _ns(**kw) -> argparse.Namespace:
    base = {"paths": [], "check": False, "quiet": True}
    base.update(kw)
    return argparse.Namespace(**base)


def test_build_command_no_ydb_returns_one(monkeypatch, tmp_path, capsys):
    # Domain failure (CLI-UX §3.7): missing dep is exit 1, not usage 2.
    monkeypatch.delenv("YDB", raising=False)
    monkeypatch.delenv("ydb_dist", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    rc = build_command(_ns(paths=[tmp_path]), runner=lambda b, f: (0, ""))
    err = capsys.readouterr().err
    assert rc == 1
    assert "ydb" in err.lower()


def test_build_command_no_files_returns_one(monkeypatch, tmp_path, capsys):
    # Domain failure (CLI-UX §3.7): empty input set is exit 1.
    bin_ = tmp_path / "ydb"
    bin_.write_text("#!/bin/sh\nexit 0\n")
    bin_.chmod(0o755)
    monkeypatch.setenv("YDB", str(bin_))
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = build_command(_ns(paths=[empty]), runner=lambda b, f: (0, ""))
    err = capsys.readouterr().err
    assert rc == 1
    assert "no .m files" in err.lower() or "no m files" in err.lower()


def test_build_command_returns_zero_when_all_compile(monkeypatch, tmp_path):
    bin_ = tmp_path / "ydb"
    bin_.write_text("#!/bin/sh\nexit 0\n")
    bin_.chmod(0o755)
    monkeypatch.setenv("YDB", str(bin_))
    src = tmp_path / "src"
    src.mkdir()
    (src / "FOO.m").write_text("FOO ; quit\n Q\n")
    (src / "BAR.m").write_text("BAR ; quit\n Q\n")
    calls: list[Path] = []

    def fake_runner(binary, file):
        calls.append(file)
        return (0, "")

    rc = build_command(_ns(paths=[src]), runner=fake_runner)
    assert rc == 0
    assert {f.name for f in calls} == {"FOO.m", "BAR.m"}


def test_build_command_returns_one_on_any_failure(monkeypatch, tmp_path, capsys):
    bin_ = tmp_path / "ydb"
    bin_.write_text("#!/bin/sh\nexit 0\n")
    bin_.chmod(0o755)
    monkeypatch.setenv("YDB", str(bin_))
    (tmp_path / "OK.m").write_text("OK ; quit\n Q\n")
    (tmp_path / "BAD.m").write_text("BAD ; quit\n syntax error\n")

    def fake_runner(binary, file):
        if file.name == "BAD.m":
            return (1, "%YDB-E-SYNTAX, sample error\n")
        return (0, "")

    rc = build_command(_ns(paths=[tmp_path]), runner=fake_runner)
    captured = capsys.readouterr()
    assert rc == 1
    assert "BAD.m" in (captured.out + captured.err)


def test_build_command_check_cleans_up_o_files(monkeypatch, tmp_path):
    bin_ = tmp_path / "ydb"
    bin_.write_text("#!/bin/sh\nexit 0\n")
    bin_.chmod(0o755)
    monkeypatch.setenv("YDB", str(bin_))
    (tmp_path / "FOO.m").write_text("FOO ; quit\n Q\n")
    fake_obj = tmp_path / "FOO.o"

    def fake_runner(binary, file):
        # simulate the engine's side effect: drop FOO.o next to FOO.m
        fake_obj.write_bytes(b"\x00")
        return (0, "")

    rc = build_command(_ns(paths=[tmp_path], check=True), runner=fake_runner)
    assert rc == 0
    assert not fake_obj.exists(), "--check should clean up .o files"


def test_build_command_default_keeps_o_files(monkeypatch, tmp_path):
    bin_ = tmp_path / "ydb"
    bin_.write_text("#!/bin/sh\nexit 0\n")
    bin_.chmod(0o755)
    monkeypatch.setenv("YDB", str(bin_))
    (tmp_path / "FOO.m").write_text("FOO ; quit\n Q\n")
    fake_obj = tmp_path / "FOO.o"

    def fake_runner(binary, file):
        fake_obj.write_bytes(b"\x00")
        return (0, "")

    rc = build_command(_ns(paths=[tmp_path], check=False), runner=fake_runner)
    assert rc == 0
    assert fake_obj.exists(), "default mode keeps .o files for use"
