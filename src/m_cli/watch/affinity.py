"""Resolve which test suites to re-run when a given file changes.

Convention: source file ``foo.m`` is tested by suite ``FOOTST.m`` (the
source basename, uppercased, with ``TST`` appended). When the changed
file is itself a suite, only that suite re-runs. When no affinity is
discoverable, fall back to running every known suite.
"""

from __future__ import annotations

from pathlib import Path

from m_cli.test.discovery import TestSuite, is_suite_file


def resolve_affinity(changed: Path, suites: list[TestSuite]) -> list[TestSuite]:
    """Return the subset of ``suites`` to re-run for a change to ``changed``.

    - Non-``.m`` paths return ``[]`` (the watcher should ignore them).
    - Suite files match themselves by name only.
    - Source files map to ``<STEM.upper()>TST``; if that suite exists,
      it's the sole match. Otherwise every suite is returned (fall-back).
    """
    if changed.suffix != ".m":
        return []

    if is_suite_file(changed):
        match = next((s for s in suites if s.name == changed.stem), None)
        return [match] if match else []

    expected = f"{changed.stem.upper()}TST"
    direct = [s for s in suites if s.name == expected]
    if direct:
        return direct
    return list(suites)
