"""Run M test suites against the vista-meta YottaDB engine.

The runner builds an ``ssh`` argv that invokes ``mumps`` remotely on
vista-meta; output parsing follows the TESTRUN protocol unchanged
(``  PASS  ...`` / ``  FAIL  ...`` / ``Results: N tests ...``).

The subprocess invocation is injectable (``runner=`` kwarg) so unit
tests don't need a live container — pass a fake that returns canned
``(stdout, returncode)`` and a fake :class:`~m_cli.engine.Connection`.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from m_cli.engine import (
    Connection,
    build_suite_ssh_cmd,
    build_xcmd_ssh_cmd,
    read_connection,
    remote_stage,
)
from m_cli.test.discovery import TestCase, TestSuite

# (cmd, env) -> (stdout, returncode). ``env`` is unused for the SSH
# transport (env vars are set inside the remote shell command), but
# the parameter is kept so the existing RunnerFn signature is stable.
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


# Sentinel returncode used by _default_runner when subprocess.TimeoutExpired
# fires. Out of any real returncode range (signal-killed processes return
# -1..-128, normal exits return 0..255), so callers can branch on it without
# colliding with a real mumps exit.
TIMEOUT_RC = -65535


@dataclass(frozen=True)
class RunResult:
    suite: str
    label: str | None
    summary: Summary
    ok: bool
    stdout: str
    returncode: int
    # True when the subprocess was killed because it ran past the per-suite
    # timeout. Distinguishes a hard timeout from a real 0/0 failure caused
    # by parser issues or zero-assertion suites.
    timed_out: bool = False


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


def _escape_m_string(s: str) -> str:
    """Escape a Python string for embedding inside an M ``"..."`` literal.

    Doubles every embedded ``"`` per M string-literal escaping rules
    so callers can build xcmds containing arbitrary path / label text
    without breaking the parse.
    """
    return s.replace('"', '""')


def _seed_prelude(seeds: list[str]) -> str:
    """Build the ``do load^STDSEED("...")`` sequence for ``--seed PATH``.

    Returns an empty string when ``seeds`` is empty so callers can
    splice it unconditionally without leaving stray double-spaces.
    """
    if not seeds:
        return ""
    return (
        "  ".join(f'do load^STDSEED("{_escape_m_string(p)}")' for p in seeds) + "  "
    )


def run_suite(
    suite: TestSuite,
    *,
    runner: RunnerFn | None = None,
    conn: Connection | None = None,
    seeds: list[str] | None = None,
    timeout: float | None = None,
) -> RunResult:
    """Execute a whole suite on vista-meta.

    Without ``seeds``: invokes ``mumps -run ^SUITE`` directly (no
    ``%XCMD`` indirection). With ``seeds``: switches to
    ``mumps -run %XCMD 'do load^STDSEED(...) do ^SUITE'`` so each
    ``--seed PATH`` (track Y) is loaded before the suite runs.

    Per-test concerns (track X — STDMOCK registry, track W — STDFIX
    rollback) are handled in :func:`run_case` rather than at suite
    launch: each ``mumps`` invocation is a fresh process with a clean
    ``^STDLIB($JOB,...)`` tree, so the registry is empty by
    construction; the suite's own routine drives the per-test loop
    and is the right place to add ``with^STDFIX`` if the author wants
    per-test rollback.
    """
    conn = conn or read_connection()
    stage = remote_stage(suite.path)
    seeds = seeds or []
    if seeds:
        xcmd = _seed_prelude(seeds) + f"do ^{suite.name}"
        cmd = build_xcmd_ssh_cmd(conn, xcmd, stage)
    else:
        cmd = build_suite_ssh_cmd(conn, suite.name, stage)
    runner = runner or _make_default_runner(timeout)
    stdout, rc = runner(cmd, None)
    summary = parse_suite_output(stdout)
    timed_out = rc == TIMEOUT_RC
    ok = summary.ok and rc == 0
    return RunResult(
        suite=suite.name,
        label=None,
        summary=summary,
        ok=ok,
        stdout=stdout,
        returncode=rc,
        timed_out=timed_out,
    )


def run_case(
    case: TestCase,
    *,
    runner: RunnerFn | None = None,
    conn: Connection | None = None,
    isolation: bool = True,
    seeds: list[str] | None = None,
    timeout: float | None = None,
) -> RunResult:
    """Execute a single labeled test via ``mumps -run %XCMD`` on vista-meta.

    The xcmd prelude clears the STDMOCK registry (track X) and loads
    each ``--seed PATH`` (track Y) before invoking the test. When
    ``isolation`` is true (default), the test invocation is wrapped
    in inline ``tstart`` / ``trollback`` so per-test global mutations
    roll back at the end of the test (track W). Pass
    ``isolation=False`` to opt out for legacy ^TESTRUN-style suites
    or suites that manage their own transactions.

    Why inline rather than ``with^STDFIX``: STDFIX runs ``xecute code``
    inside its own stack frame, where the xcmd-level ``pass`` /
    ``fail`` locals aren't reachable. STDFIX stays the right API for
    application code that wants tag bookkeeping and an error-trap
    re-raise; the runner only needs the rollback.
    """
    conn = conn or read_connection()
    stage = remote_stage(case.path)
    protocol = case.protocol
    invoke_test = f"do {case.label}^{case.suite}(.pass,.fail)"
    if isolation:
        # Inline transaction scope at the xcmd frame so .pass / .fail
        # remain visible to the test invocation.
        invoke_test = f"tstart  {invoke_test}  trollback"
    xcmd = (
        "new pass,fail  "
        "do clear^STDMOCK  "
        + _seed_prelude(seeds or [])
        + f"do start^{protocol}(.pass,.fail)  "
        + invoke_test
        + "  "
        + f"do report^{protocol}(pass,fail)"
    )
    cmd = build_xcmd_ssh_cmd(conn, xcmd, stage)
    runner = runner or _make_default_runner(timeout)
    stdout, rc = runner(cmd, None)
    summary = parse_suite_output(stdout)
    timed_out = rc == TIMEOUT_RC
    ok = summary.ok and rc == 0
    return RunResult(
        suite=case.suite,
        label=case.label,
        summary=summary,
        ok=ok,
        stdout=stdout,
        returncode=rc,
        timed_out=timed_out,
    )


def _make_default_runner(timeout: float | None):
    """Build a runner closure that captures the per-suite timeout.

    Lets ``run_suite`` / ``run_case`` thread a timeout through to
    ``_default_runner`` while keeping the public ``RunnerFn`` shape
    (``cmd, env -> stdout, rc``) stable for test fakes.
    """

    def runner(cmd: list[str], env: dict[str, str] | None) -> tuple[str, int]:
        return _default_runner(cmd, env, timeout=timeout)

    return runner


def _default_runner(
    cmd: list[str],
    env: dict[str, str] | None,
    *,
    timeout: float | None = None,
) -> tuple[str, int]:
    """Run ``cmd`` and return (stdout-with-stderr, returncode).

    When ``timeout`` is set and the subprocess does not exit before
    the deadline, the runner captures whatever output it produced,
    appends a ``[m-cli: timed out after Ns]`` marker, and returns
    :data:`TIMEOUT_RC`. Callers branch on that to surface the timeout
    distinctly from a real ``0/0`` parse — see ``RunResult.timed_out``.
    """
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or b"").decode("latin-1", errors="replace")
        marker = f"\n[m-cli: timed out after {timeout}s; subprocess killed]\n"
        return partial + marker, TIMEOUT_RC
    return proc.stdout.decode("latin-1", errors="replace"), proc.returncode
