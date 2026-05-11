"""`m coverage` command implementation.

Resolves arguments to (production routines, test suites), runs a
coverage pass under YottaDB, writes the result in the requested
format. Exit codes:

  0 — success (coverage data produced; ``--min-percent`` met if set)
  1 — coverage threshold not met, or ydb run returned non-zero
  2 — usage / argument error / no routines found
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from m_cli.coverage.output import write_output
from m_cli.coverage.runner import (
    discover_routines_and_suites,
    run_coverage,
)
from m_cli.engine import EngineNotConfigured, read_connection, seed_for_paths


def coverage_command(args: argparse.Namespace) -> int:
    paths = _resolve_paths(args)
    if paths is None:
        return 2

    routines, suites = discover_routines_and_suites(paths)
    # "Nothing to cover" is not a failure (CLI-UX guide §3.2). Same
    # logic as `m test` / `m watch` — empty world exits 0 to stdout.
    if not routines:
        print("m coverage: no production .m routines found", file=sys.stdout)
        return 0
    if not suites:
        print("m coverage: no *TST.m suites found", file=sys.stdout)
        return 0

    suite_filter = None
    if args.suites:
        suite_filter = [s.strip() for s in args.suites.split(",") if s.strip()]
        unknown = [s for s in suite_filter if s not in {x.name for x in suites}]
        if unknown:
            print(
                f"m coverage: unknown suite(s) in --suites: {sorted(unknown)}",
                file=sys.stderr,
            )
            return 2

    try:
        conn = read_connection()
        seed_for_paths(routines + [s.path for s in suites], conn)
    except EngineNotConfigured as e:
        print(f"m coverage: {e}", file=sys.stderr)
        return 2

    branch = getattr(args, "branch", False)
    result = run_coverage(
        routines,
        suites,
        suite_filter=suite_filter,
        conn=conn,
        with_branches=branch,
    )
    write_output(
        result,
        fmt=args.format,
        uncovered_only=args.uncovered,
        show_lines=args.lines,
        show_branches=branch,
    )

    if not args.quiet:
        _print_summary(result, args)

    if result.returncode != 0:
        return 1
    if args.min_percent is not None and result.percent < args.min_percent:
        return 1
    return 0


def _resolve_paths(args: argparse.Namespace) -> list[Path] | None:
    """Build the list of directories / files to walk.

    Resolution order:
      1. Explicit ``--routines`` and/or ``--tests`` flags (combined).
      2. Otherwise, the positional ``paths`` arg (default ``[.]``).

    For (2), we further auto-detect: if the path contains a
    ``routines/`` subdir, use ``routines/`` (with its ``tests/``
    subtree) so ``m coverage`` from a project root "just works"
    against the m-tools layout.
    """
    if args.routines or args.tests:
        out: list[Path] = []
        for p in (args.routines or []):
            if not p.exists():
                print(f"m coverage: --routines {p}: not found", file=sys.stderr)
                return None
            out.append(p)
        for p in (args.tests or []):
            if not p.exists():
                print(f"m coverage: --tests {p}: not found", file=sys.stderr)
                return None
            out.append(p)
        return out

    out = []
    for p in args.paths:
        if not p.exists():
            print(f"m coverage: {p}: not found", file=sys.stderr)
            return None
        # Auto-detect: if a `routines/` subdir exists, use it.
        rsubdir = p / "routines" if p.is_dir() else None
        out.append(rsubdir if rsubdir and rsubdir.is_dir() else p)
    return out


def _print_summary(result, args) -> None:
    line = (
        f"m coverage: {len(result.suites_run)} suite(s), "
        f"{result.covered}/{result.total} labels "
        f"({result.percent:.1f}%)"
    )
    if args.min_percent is not None:
        line += f", threshold {args.min_percent:.1f}%"
    print(line, file=sys.stderr)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path(".")],
        help="Project root or path(s) to scan (default: current directory)",
    )
    parser.add_argument(
        "--routines",
        action="append",
        type=Path,
        default=[],
        help="Explicit production-routines path (repeatable). Skips auto-detect.",
    )
    parser.add_argument(
        "--tests",
        action="append",
        type=Path,
        default=[],
        help="Explicit test-suites path (repeatable). Skips auto-detect.",
    )
    parser.add_argument(
        "--suites",
        default=None,
        help="Comma-separated suite names to restrict the run (default: all)",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "lcov"),
        default="text",
        help=(
            "Output format (default: text). 'lcov' emits a tracefile "
            "consumable by genhtml / Codecov / Coveralls."
        ),
    )
    parser.add_argument(
        "--lines",
        action="store_true",
        help=(
            "Show line-level detail in text output. With --uncovered, "
            "also lists every uncovered executable line."
        ),
    )
    parser.add_argument(
        "--uncovered",
        action="store_true",
        help="Print only uncovered labels (text format only)",
    )
    parser.add_argument(
        "--branch",
        action="store_true",
        help=(
            "Collect branch coverage: identify IF/ELSE/FOR/postconditional "
            "decisions and report which were reached during the run."
        ),
    )
    parser.add_argument(
        "--min-percent",
        type=float,
        default=None,
        help="Fail with exit 1 if total coverage is below this percent",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress the summary line on stderr",
    )
    parser.set_defaults(func=coverage_command)
