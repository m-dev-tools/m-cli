"""Run M test suites against a YottaDB interpreter.

The runner shells out to ``ydb`` (configurable via ``$YDB`` / discovered
via ``ydb_dist``) and parses its stdout. Output is the mini-protocol
emitted by m-tools' ``^TESTRUN`` assertion library:

    ``  PASS  <description>``
    ``  FAIL  <description>``
    ``         expected: <expected>``
    ``         actual:   <actual>``
    ...
    ``Results: <total> tests  <passed> passed  <failed> failed``
    ``All tests passed.``  *or*  ``<n> test(s) FAILED.``

The subprocess invocation is injectable (``runner=`` kwarg) so unit
tests don't require a live ydb installation.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from m_cli.test.discovery import TestCase, TestSuite

# (cmd, env) -> (stdout, returncode)
RunnerFn = Callable[[list[str], "dict[str, str] | None"], "tuple[str, int]"]


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class Assertion:
    outcome: Outcome
    description: str
    expected: str | None = None
    actual: str | None = None


@dataclass(frozen=True)
class Summary:
    """Parsed result of a suite (or single-test) invocation."""

    passed: int
    failed: int
    total: int
    ok: bool
    assertions: list[Assertion] = field(default_factory=list)


@dataclass(frozen=True)
class RunResult:
    suite: str
    label: str | None
    summary: Summary
    ok: bool
    stdout: str
    returncode: int


_RESULTS_RE = re.compile(
    r"^Results:\s+(\d+)\s+tests\s+(\d+)\s+passed\s+(\d+)\s+failed",
    re.MULTILINE,
)
_FAILED_BANNER_RE = re.compile(r"\d+\s+test\(s\)\s+FAILED", re.MULTILINE)
_PASS_BANNER_RE = re.compile(r"All tests passed\.", re.MULTILINE)
_PASS_LINE_RE = re.compile(r"^  PASS  (.+)$")
_FAIL_LINE_RE = re.compile(r"^  FAIL  (.+)$")
_EXPECTED_RE = re.compile(r"^         expected:\s*(.*)$")
_ACTUAL_RE = re.compile(r"^         actual:\s*(.*)$")


def parse_suite_output(stdout: str) -> Summary:
    """Parse TESTRUN-format output into a Summary."""
    passed = failed = total = 0
    ok = False
    m = _RESULTS_RE.search(stdout)
    if m:
        total = int(m.group(1))
        passed = int(m.group(2))
        failed = int(m.group(3))
    if _FAILED_BANNER_RE.search(stdout):
        ok = False
    elif _PASS_BANNER_RE.search(stdout):
        ok = True
    elif total and failed == 0:
        # No banner but counters look healthy
        ok = True
    else:
        ok = False

    assertions: list[Assertion] = []
    lines = stdout.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        pm = _PASS_LINE_RE.match(line)
        if pm:
            assertions.append(Assertion(Outcome.PASS, pm.group(1).rstrip()))
            i += 1
            continue
        fm = _FAIL_LINE_RE.match(line)
        if fm:
            desc = fm.group(1).rstrip()
            expected = actual = None
            if i + 1 < len(lines):
                em = _EXPECTED_RE.match(lines[i + 1])
                if em:
                    expected = em.group(1).rstrip()
                    i += 1
            if i + 1 < len(lines):
                am = _ACTUAL_RE.match(lines[i + 1])
                if am:
                    actual = am.group(1).rstrip()
                    i += 1
            assertions.append(Assertion(Outcome.FAIL, desc, expected, actual))
            i += 1
            continue
        i += 1

    return Summary(
        passed=passed,
        failed=failed,
        total=total,
        ok=ok,
        assertions=assertions,
    )


def run_suite(
    suite: TestSuite,
    *,
    runner: RunnerFn | None = None,
    env: dict[str, str] | None = None,
) -> RunResult:
    """Execute a whole test suite via ``ydb -run ^SUITE``."""
    cmd = [_ydb_path(), "-run", f"^{suite.name}"]
    runner = runner or _default_runner
    full_env = _build_env(suite.path, env)
    stdout, rc = runner(cmd, full_env)
    summary = parse_suite_output(stdout)
    ok = summary.ok and rc == 0
    return RunResult(
        suite=suite.name,
        label=None,
        summary=summary,
        ok=ok,
        stdout=stdout,
        returncode=rc,
    )


def run_case(
    case: TestCase,
    *,
    runner: RunnerFn | None = None,
    env: dict[str, str] | None = None,
) -> RunResult:
    """Execute a single labeled test via ``%XCMD``."""
    xcmd = (
        "new pass,fail  "
        "do start^TESTRUN(.pass,.fail)  "
        f"do {case.label}^{case.suite}(.pass,.fail)  "
        "do report^TESTRUN(pass,fail)"
    )
    cmd = [_ydb_path(), "-run", "%XCMD", xcmd]
    runner = runner or _default_runner
    full_env = _build_env(case.path, env)
    stdout, rc = runner(cmd, full_env)
    summary = parse_suite_output(stdout)
    ok = summary.ok and rc == 0
    return RunResult(
        suite=case.suite,
        label=case.label,
        summary=summary,
        ok=ok,
        stdout=stdout,
        returncode=rc,
    )


# ---------------------------------------------------------------------------
# Subprocess plumbing
# ---------------------------------------------------------------------------


def _default_runner(cmd: list[str], env: dict[str, str] | None) -> tuple[str, int]:
    """Run ``cmd`` and return (stdout-with-stderr, returncode)."""
    proc = subprocess.run(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.stdout.decode("latin-1", errors="replace"), proc.returncode


def _ydb_path() -> str:
    """Locate the ``ydb`` binary.

    Resolution order: ``$YDB``, then ``$ydb_dist/ydb``, then plain ``ydb``
    (lets the user's PATH find it).
    """
    if explicit := os.environ.get("YDB"):
        return explicit
    if dist := os.environ.get("ydb_dist"):
        candidate = Path(dist) / "ydb"
        if candidate.exists():
            return str(candidate)
    return "ydb"


def _build_env(suite_path: Path, override: dict[str, str] | None) -> dict[str, str]:
    """Compose the environment passed to ydb.

    If the caller already exported ``ydb_routines``, we honor it. Otherwise
    we derive a sensible default from the suite's parent directory: the
    suite folder plus a sibling ``routines/`` if one exists.
    """
    env = os.environ.copy()
    if override:
        env.update(override)
    if "ydb_routines" not in env:
        derived = _derive_ydb_routines(suite_path)
        if derived:
            env["ydb_routines"] = derived
    return env


def _derive_ydb_routines(suite_path: Path) -> str | None:
    parts: list[str] = []
    suite_dir = suite_path.parent
    if suite_dir.is_dir():
        parts.append(str(suite_dir.resolve()))
    # If suite lives at <project>/routines/tests/, add <project>/routines too.
    routines_sibling = suite_dir.parent
    if routines_sibling.name == "routines" and routines_sibling.is_dir():
        parts.insert(0, str(routines_sibling.resolve()))
    if dist := os.environ.get("ydb_dist"):
        parts.append(dist)
    return " ".join(parts) if parts else None
