"""`m test` command implementation.

Argparse-driven. Supports:

  m test                          # auto-detect routines/tests/ under CWD
  m test PATH [PATH...]           # discover suites under given paths
  m test PATH/SUITETST.m::tCase   # run one labeled test
  m test --list PATH              # list discovered suites + cases, no run
  m test --filter PATTERN PATH    # only run suites whose name matches
  m test --format {text,tap,json}
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from m_cli.engine import EngineNotConfigured, detect_engine, seed_for_paths
from m_cli.test.changed import changed_to_suites, find_changed_m_files
from m_cli.test.discovery import TestSuite, discover, find_test_cases, is_suite_file
from m_cli.test.output import write_output
from m_cli.test.runner import RunResult, run_case, run_suite


def test_command(args: argparse.Namespace) -> int:
    """Entry point for `m test`. Returns process exit code.

    Exit codes:
      0 — all suites and cases passed
      1 — at least one suite failed (or could not be parsed)
      2 — usage / discovery / argument error
    """
    paths, single_case_selector = _split_paths_and_selector(args.paths)
    if not paths and not single_case_selector:
        paths = _default_paths()

    if single_case_selector is not None:
        return _run_single_case(single_case_selector, args)

    if not paths:
        # "Nothing to test" is not a failure (CLI-UX guide §3.2).
        print("m test: no suites found", file=sys.stdout)
        return 0

    suites = discover(paths)
    if args.filter:
        suites = [s for s in suites if args.filter in s.name]
    if not suites:
        print("m test: no suites found", file=sys.stdout)
        return 0

    if getattr(args, "changed", False):
        base = getattr(args, "changed_base", None)
        changed_files = find_changed_m_files(Path.cwd(), base=base)
        suites = changed_to_suites(changed_files, suites)
        if not suites:
            print(
                "m test: no changed .m files affect any discovered suite",
                file=sys.stderr,
            )
            return 0

    if args.list:
        _list_suites(suites)
        return 0

    try:
        conn = detect_engine()
        seed_for_paths([s.path for s in suites], conn)
    except EngineNotConfigured as e:
        print(f"m test: {e}", file=sys.stderr)
        return 2

    seeds = list(getattr(args, "seeds", []) or [])
    env_files = list(getattr(args, "env_files", []) or [])
    update_snapshots = bool(getattr(args, "update_snapshots", False))
    timings = bool(getattr(args, "timings", False))
    timeout = _resolve_timeout(args)
    results: list[RunResult] = []
    for suite in suites:
        results.append(
            run_suite(
                suite,
                conn=conn,
                seeds=seeds,
                env_files=env_files,
                update_snapshots=update_snapshots,
                timeout=timeout,
            )
        )

    write_output(results, fmt=args.format)
    if not args.quiet:
        _print_summary(results, timings=timings)

    return 0 if all(r.ok for r in results) else 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_paths_and_selector(
    raw: list[Path],
) -> tuple[list[Path], "tuple[Path, str] | None"]:
    """Pull a single ``FILE.m::tLabel`` selector out of the positional args."""
    plain: list[Path] = []
    selector: tuple[Path, str] | None = None
    for p in raw:
        s = str(p)
        if "::" in s:
            head, _, label = s.partition("::")
            if selector is not None:
                # Two selectors → ambiguous; bail with a clear error later.
                raise SystemExit("m test: only one SUITE::tCase selector allowed")
            selector = (Path(head), label)
        else:
            plain.append(p)
    return plain, selector


def _default_paths() -> list[Path]:
    """Pick a sensible default path when none is given.

    Convention: a ``routines/tests/`` directory in the current working
    directory (the m-tools / VistA layout). If that's missing, no
    default is supplied — the caller must specify a path.
    """
    cwd = Path.cwd()
    candidate = cwd / "routines" / "tests"
    if candidate.is_dir():
        return [candidate]
    return []


def _run_single_case(selector: tuple[Path, str], args: argparse.Namespace) -> int:
    suite_path, label = selector
    if not suite_path.is_file():
        print(f"m test: suite file not found: {suite_path}", file=sys.stderr)
        return 2
    if not (is_suite_file(suite_path) or suite_path.suffix == ".m"):
        print(f"m test: not an .m file: {suite_path}", file=sys.stderr)
        return 2
    src = suite_path.read_bytes()
    cases = find_test_cases(suite_path, src)
    case = next((c for c in cases if c.label == label), None)
    if case is None:
        available = ", ".join(c.label for c in cases) or "(none)"
        print(
            f"m test: label '{label}' not found in {suite_path}\n        available: {available}",
            file=sys.stderr,
        )
        return 2
    if args.list:
        _list_suites([TestSuite(name=case.suite, path=suite_path, cases=[case])])
        return 0
    try:
        conn = detect_engine()
        seed_for_paths([case.path], conn)
    except EngineNotConfigured as e:
        print(f"m test: {e}", file=sys.stderr)
        return 2
    isolation = not getattr(args, "no_isolation", False)
    seeds = list(getattr(args, "seeds", []) or [])
    env_files = list(getattr(args, "env_files", []) or [])
    update_snapshots = bool(getattr(args, "update_snapshots", False))
    timings = bool(getattr(args, "timings", False))
    timeout = _resolve_timeout(args)
    result = run_case(
        case,
        conn=conn,
        isolation=isolation,
        seeds=seeds,
        env_files=env_files,
        update_snapshots=update_snapshots,
        timeout=timeout,
    )
    write_output([result], fmt=args.format)
    if not args.quiet:
        _print_summary([result], timings=timings)
    return 0 if result.ok else 1


def _list_suites(suites: list[TestSuite]) -> None:
    for s in suites:
        print(f"{s.name}  ({s.path})")
        for c in s.cases:
            desc = f"  — {c.description}" if c.description else ""
            print(f"  {c.label}{desc}")


def _resolve_timeout(args: argparse.Namespace) -> float | None:
    """Resolve the --timeout flag to the value the runner expects.

    The CLI exposes ``0`` as "no timeout"; the runner's contract uses
    ``None`` for that. Anything else passes through as-is.
    """
    raw = getattr(args, "timeout", None)
    if raw is None or raw <= 0:
        return None
    return float(raw)


def _print_summary(results: list[RunResult], *, timings: bool = False) -> None:
    n_suites = len(results)
    n_pass = sum(1 for r in results if r.ok)
    n_timeout = sum(1 for r in results if r.timed_out)
    n_fail = n_suites - n_pass
    total_pass = sum(r.summary.passed for r in results)
    total_fail = sum(r.summary.failed for r in results)
    total = sum(r.summary.total for r in results)
    parts = [
        f"{n_suites} suite(s)",
        f"{n_pass} passed" if n_pass else "0 passed",
    ]
    if n_fail:
        parts.append(f"{n_fail} failed")
    if n_timeout:
        parts.append(f"{n_timeout} timed out")
    parts.append(f"{total_pass}/{total} assertions passed")
    if total_fail:
        parts.append(f"{total_fail} failed")
    if timings:
        total_ms = sum(r.elapsed_ms for r in results)
        parts.append(f"{total_ms:.0f} ms total")
    print("m test: " + ", ".join(parts), file=sys.stderr)
    if timings:
        # Per-suite breakdown sorted slowest-first to surface inner-loop drag.
        ordered = sorted(results, key=lambda r: r.elapsed_ms, reverse=True)
        for r in ordered:
            label = f" [{r.label}]" if r.label else ""
            print(
                f"        {r.elapsed_ms:>8.0f} ms  {r.suite}{label}",
                file=sys.stderr,
            )
