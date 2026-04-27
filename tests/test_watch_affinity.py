"""Tests for `m watch` affinity resolution.

Affinity rule: when a non-suite file changes, the watcher should re-run
suites that test it. Convention: source ``foo.m`` is tested by suite
``FOOTST.m`` (uppercased name + ``TST``). When no match is found, the
watcher falls back to running every discovered suite.
"""

from __future__ import annotations

from pathlib import Path

from m_cli.test.discovery import TestSuite
from m_cli.watch.affinity import resolve_affinity


def _suite(name: str, path: Path | str = ".") -> TestSuite:
    return TestSuite(name=name, path=Path(path) / f"{name}.m", cases=[])


def test_changed_suite_returns_just_that_suite() -> None:
    suites = [_suite("HELLOTST"), _suite("SAFETST")]
    affected = resolve_affinity(Path("HELLOTST.m"), suites)
    assert [s.name for s in affected] == ["HELLOTST"]


def test_changed_source_maps_to_uppercased_TST_suite() -> None:
    suites = [_suite("HELLOTST"), _suite("SAFETST")]
    affected = resolve_affinity(Path("hello.m"), suites)
    assert [s.name for s in affected] == ["HELLOTST"]


def test_changed_source_with_no_matching_suite_returns_all() -> None:
    suites = [_suite("HELLOTST"), _suite("SAFETST")]
    affected = resolve_affinity(Path("orphan.m"), suites)
    assert {s.name for s in affected} == {"HELLOTST", "SAFETST"}


def test_changed_uppercase_source_still_resolves() -> None:
    # Some VistA-style routines have uppercase names. ``DPT.m`` should
    # map to ``DPTTST.m`` if it exists.
    suites = [_suite("DPTTST")]
    affected = resolve_affinity(Path("DPT.m"), suites)
    assert [s.name for s in affected] == ["DPTTST"]


def test_changed_non_m_file_returns_empty() -> None:
    suites = [_suite("HELLOTST")]
    affected = resolve_affinity(Path("README.md"), suites)
    assert affected == []


def test_path_with_directory_prefix_resolved_by_basename() -> None:
    suites = [_suite("HELLOTST", "/proj/routines/tests")]
    affected = resolve_affinity(Path("/proj/routines/hello.m"), suites)
    assert [s.name for s in affected] == ["HELLOTST"]


def test_changed_suite_under_directory_returns_just_that_suite() -> None:
    suites = [_suite("HELLOTST", "/proj/routines/tests"), _suite("SAFETST")]
    affected = resolve_affinity(Path("/proj/routines/tests/HELLOTST.m"), suites)
    assert [s.name for s in affected] == ["HELLOTST"]
