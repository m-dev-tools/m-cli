"""Tests for `m watch` polling — file-mtime-based change detection."""

from __future__ import annotations

import os
import time
from pathlib import Path

from m_cli.watch.poller import Poller


def _touch(p: Path, mtime: float | None = None) -> None:
    """Create or update ``p`` and optionally set its mtime."""
    if not p.exists():
        p.write_text("")
    if mtime is not None:
        os.utime(p, (mtime, mtime))


def test_first_poll_returns_no_changes(tmp_path: Path) -> None:
    a = tmp_path / "a.m"
    a.write_text("")
    poller = Poller([tmp_path])
    # Prime — first call records the baseline; subsequent polls report deltas.
    poller.poll_once()
    assert poller.poll_once() == set()


def test_changed_file_is_reported(tmp_path: Path) -> None:
    a = tmp_path / "a.m"
    a.write_text("v1")
    poller = Poller([tmp_path])
    poller.poll_once()
    # Bump mtime explicitly — write_text may keep nanosecond mtime stable.
    _touch(a, time.time() + 1)
    a.write_text("v2")
    _touch(a, time.time() + 2)
    changed = poller.poll_once()
    assert changed == {a}


def test_new_file_appears(tmp_path: Path) -> None:
    poller = Poller([tmp_path])
    poller.poll_once()
    new = tmp_path / "new.m"
    new.write_text("")
    changed = poller.poll_once()
    assert changed == {new}


def test_deleted_file_is_reported(tmp_path: Path) -> None:
    a = tmp_path / "a.m"
    a.write_text("")
    poller = Poller([tmp_path])
    poller.poll_once()
    a.unlink()
    changed = poller.poll_once()
    assert changed == {a}


def test_only_m_files_tracked(tmp_path: Path) -> None:
    m = tmp_path / "a.m"
    m.write_text("")
    txt = tmp_path / "a.txt"
    txt.write_text("")
    poller = Poller([tmp_path])
    poller.poll_once()
    txt.write_text("changed")
    _touch(txt, time.time() + 1)
    assert poller.poll_once() == set()
    m.write_text("changed")
    _touch(m, time.time() + 2)
    assert poller.poll_once() == {m}


def test_recurses_into_subdirectories(tmp_path: Path) -> None:
    sub = tmp_path / "deep" / "sub"
    sub.mkdir(parents=True)
    inner = sub / "x.m"
    inner.write_text("")
    poller = Poller([tmp_path])
    poller.poll_once()
    inner.write_text("changed")
    _touch(inner, time.time() + 1)
    assert poller.poll_once() == {inner}


def test_explicit_file_path_works(tmp_path: Path) -> None:
    a = tmp_path / "a.m"
    a.write_text("")
    poller = Poller([a])
    poller.poll_once()
    a.write_text("changed")
    _touch(a, time.time() + 1)
    assert poller.poll_once() == {a}
