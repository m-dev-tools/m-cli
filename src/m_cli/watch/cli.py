"""`m watch` command implementation.

Discovers test suites under the given paths, runs them once, and then
loops: every ``--interval`` seconds, re-stat the watched ``.m`` files
and re-run any suite affected by the changes. Ctrl+C exits cleanly.

Use ``--once`` to run the initial pass and exit without watching — the
mode the unit tests exercise (and a useful smoke check before starting
a long-running session).
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

from m_cli.test.cli import _default_paths
from m_cli.test.discovery import discover
from m_cli.test.output import write_output
from m_cli.test.runner import RunResult, run_suite
from m_cli.watch.affinity import resolve_affinity
from m_cli.watch.poller import Poller


def watch_command(args: argparse.Namespace) -> int:
    """Entry point for `m watch`. Returns process exit code.

    Exit codes:
      0 — initial pass succeeded (and watch loop ran cleanly until interrupted)
      1 — initial pass failed
      2 — usage / discovery error
    """
    paths = list(args.paths) if args.paths else _default_paths()
    if not paths:
        print(
            "m watch: no paths given and no routines/tests/ directory found",
            file=sys.stderr,
        )
        return 2

    suites = discover(paths)
    if args.filter:
        suites = [s for s in suites if args.filter in s.name]
    if not suites:
        print("m watch: no test suites discovered", file=sys.stderr)
        return 2

    initial_results = [run_suite(s) for s in suites]
    write_output(initial_results, fmt=args.format)
    initial_ok = all(r.ok for r in initial_results)
    _print_status(initial_results, suffix="initial pass")

    if args.once:
        return 0 if initial_ok else 1

    poller = Poller(paths)
    poller.poll_once()  # prime baseline

    print(
        f"m watch: watching {len(paths)} path(s), {len(suites)} suite(s) — Ctrl+C to exit",
        file=sys.stderr,
    )
    signal.signal(signal.SIGINT, _quiet_sigint_handler)

    try:
        while True:
            time.sleep(args.interval)
            changed = poller.poll_once()
            if not changed:
                continue
            affected = _collect_affected(changed, suites)
            if not affected:
                continue
            print(
                f"\nm watch: change detected in "
                f"{', '.join(sorted(p.name for p in changed))} → "
                f"running {len(affected)} suite(s)",
                file=sys.stderr,
            )
            results = [run_suite(s) for s in affected]
            write_output(results, fmt=args.format)
            _print_status(results, suffix="re-run")
    except KeyboardInterrupt:
        print("\nm watch: stopped", file=sys.stderr)
        return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_affected(changed: set[Path], suites: list) -> list:
    seen: dict[str, object] = {}
    for path in changed:
        for suite in resolve_affinity(path, suites):
            seen.setdefault(suite.name, suite)
    # Preserve the discovery order
    return [s for s in suites if s.name in seen]


def _print_status(results: list[RunResult], suffix: str) -> None:
    n = len(results)
    n_ok = sum(1 for r in results if r.ok)
    total = sum(r.summary.total for r in results)
    passed = sum(r.summary.passed for r in results)
    failed = sum(r.summary.failed for r in results)
    bits = [
        f"{n} suite(s)",
        f"{n_ok}/{n} ok",
        f"{passed}/{total} assertions passed",
    ]
    if failed:
        bits.append(f"{failed} failed")
    print(f"m watch ({suffix}): " + ", ".join(bits), file=sys.stderr)


def _quiet_sigint_handler(signum: int, frame) -> None:  # pragma: no cover - signal path
    raise KeyboardInterrupt
