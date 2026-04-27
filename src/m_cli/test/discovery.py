"""Test-suite discovery — find ``*TST.m`` files and their test labels.

Discovery is parser-aware: the source is parsed via tree-sitter-m and we
inspect ``label`` / ``formals`` AST nodes. A label qualifies as a test
case when:

  - The name starts with ``t`` followed by an upper-case ASCII letter
    (e.g. ``tGreetWorld``), AND
  - The label has formals containing identifiers ``pass`` and ``fail``
    (the m-tools / TESTRUN convention).

The first label in a suite (which carries the routine name) is excluded
even when it accidentally matches — entry points aren't tests.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from m_cli.parser import parse


@dataclass(frozen=True)
class TestCase:
    """A single test label inside a suite file."""

    __test__ = False  # not a pytest test class

    suite: str
    label: str
    description: str | None
    path: Path
    line: int


@dataclass(frozen=True)
class TestSuite:
    """A test suite — one ``.m`` file, zero-or-more test cases."""

    __test__ = False  # not a pytest test class

    name: str
    path: Path
    cases: list[TestCase] = field(default_factory=list)


_SUITE_NAME_RE = re.compile(r"^[A-Z][A-Z0-9]*TST$")
_TEST_LABEL_RE = re.compile(r"^t[A-Z][A-Za-z0-9]*$")
_TEST_DESC_RE = re.compile(r';@TEST\s+"([^"]*)"')


def is_suite_file(path: Path) -> bool:
    """Return True if ``path`` looks like a test-suite file by naming alone.

    Convention: ``.m`` files whose stem matches ``[A-Z][A-Z0-9]*TST``.
    Lower-case names are rejected — VistA routine names are uppercase.
    """
    if path.suffix != ".m":
        return False
    return bool(_SUITE_NAME_RE.match(path.stem))


def find_test_cases(path: Path, src: bytes) -> list[TestCase]:
    """Return the test labels declared inside ``src``.

    Skips the routine-entry label (first label in the file) and any
    label that doesn't follow the ``t<UpperCase>(pass,fail)`` convention.
    """
    tree = parse(src)
    suite = path.stem
    cases: list[TestCase] = []
    seen_first_label = False
    line_nodes = [c for c in tree.root_node.children if c.type == "line"]
    for line_node in line_nodes:
        label_node = next((c for c in line_node.children if c.type == "label"), None)
        if label_node is None:
            continue
        label_name = src[label_node.start_byte : label_node.end_byte].decode(
            "latin-1", errors="replace"
        )
        if not seen_first_label:
            seen_first_label = True
            # The routine entry label itself is never a test.
            continue
        if not _TEST_LABEL_RE.match(label_name):
            continue
        formals_node = next((c for c in line_node.children if c.type == "formals"), None)
        if formals_node is None or not _has_pass_fail_formals(formals_node, src):
            continue
        description = _extract_description(line_node, src)
        line = label_node.start_point[0] + 1  # tree-sitter rows are 0-based
        cases.append(
            TestCase(
                suite=suite,
                label=label_name,
                description=description,
                path=path,
                line=line,
            )
        )
    return cases


def discover(paths: Iterable[Path]) -> list[TestSuite]:
    """Walk ``paths`` and return discovered test suites in name order.

    - For directories: recursively scan for ``.m`` files whose name
      matches the suite convention.
    - For explicit files: trust the user — parse even if the name
      doesn't match (useful for ad-hoc suites).
    """
    suite_files: list[Path] = []
    for p in paths:
        if p.is_dir():
            for candidate in sorted(p.rglob("*.m")):
                if is_suite_file(candidate):
                    suite_files.append(candidate)
        elif p.is_file():
            suite_files.append(p)
    suites: list[TestSuite] = []
    for sf in suite_files:
        try:
            src = sf.read_bytes()
        except OSError:
            continue
        cases = find_test_cases(sf, src)
        suites.append(TestSuite(name=sf.stem, path=sf, cases=cases))
    suites.sort(key=lambda s: s.name)
    return suites


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_pass_fail_formals(formals_node, src: bytes) -> bool:
    idents = {
        src[c.start_byte : c.end_byte].decode("latin-1", errors="replace")
        for c in formals_node.children
        if c.type == "identifier"
    }
    return {"pass", "fail"}.issubset(idents)


def _extract_description(line_node, src: bytes) -> str | None:
    """Pull the ``;@TEST "..."`` description from the label's line, if any."""
    for c in line_node.children:
        if c.type == "comment":
            text = src[c.start_byte : c.end_byte].decode("latin-1", errors="replace")
            m = _TEST_DESC_RE.search(text)
            if m:
                return m.group(1)
    return None
