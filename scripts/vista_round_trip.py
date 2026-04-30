"""VistA round-trip validation for `m fmt` (Step 1: identity formatter).

The §3.5 validation gate from m-tooling-tier1.md requires the formatter
to run cleanly on the full 40,000-routine VistA corpus. For Step 1 (the
identity formatter), "cleanly" means:

  - Every routine that parses without ERROR nodes must round-trip
    byte-for-byte (input bytes == formatted bytes).
  - Routines that the parser flags with errors are reported separately
    and counted toward the 99.06% / 0.94% boundary documented in
    tree-sitter-m's own VistA validation.

Usage:

    .venv/bin/python scripts/vista_round_trip.py \
        ~/vista-meta/vista/vista-m-host/Packages

Run with --sample N to process only the first N routines (smoke test).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from m_cli.fmt.formatter import ParseError, format_source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Root of the VistA Packages directory")
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Process only first N routines (0 = all)",
    )
    parser.add_argument(
        "--show-failures",
        type=int,
        default=10,
        help="Show first N failures",
    )
    args = parser.parse_args()

    if not args.root.is_dir():
        print(f"error: {args.root} is not a directory", file=sys.stderr)
        return 2

    routines = sorted(args.root.rglob("*.m"))
    if args.sample > 0:
        routines = routines[: args.sample]

    n_total = len(routines)
    n_round_trip_ok = 0
    n_round_trip_fail = 0
    n_parse_error = 0
    n_io_error = 0
    failures: list[tuple[Path, str]] = []

    print(f"VistA round-trip — {n_total} routines from {args.root}")
    t0 = time.monotonic()

    for i, path in enumerate(routines, 1):
        try:
            src = path.read_bytes()
        except OSError as e:
            n_io_error += 1
            failures.append((path, f"io: {e}"))
            continue

        try:
            out = format_source(src)
        except ParseError as e:
            n_parse_error += 1
            failures.append((path, f"parse: {e}"))
            continue

        if out == src:
            n_round_trip_ok += 1
        else:
            n_round_trip_fail += 1
            failures.append((path, "round-trip mismatch"))

        # Progress every 5000 routines
        if i % 5000 == 0:
            elapsed = time.monotonic() - t0
            rate = i / elapsed if elapsed > 0 else 0
            print(f"  {i:>5}/{n_total} ({rate:.0f}/s)")

    elapsed = time.monotonic() - t0

    print()
    print(f"  total           : {n_total}")
    print(f"  round-trip OK   : {n_round_trip_ok}  ({100*n_round_trip_ok/n_total:.2f}%)")
    print(f"  round-trip FAIL : {n_round_trip_fail}")
    print(f"  parse error     : {n_parse_error}  ({100*n_parse_error/n_total:.2f}%)")
    print(f"  io error        : {n_io_error}")
    print(f"  elapsed         : {elapsed:.1f}s ({n_total/elapsed:.0f} routines/s)")
    print()

    if failures and args.show_failures > 0:
        print(f"first {min(args.show_failures, len(failures))} failures:")
        for path, why in failures[: args.show_failures]:
            print(f"  {path}: {why}")
        if len(failures) > args.show_failures:
            print(f"  ... and {len(failures) - args.show_failures} more")

    # Exit code semantics:
    # 0 — every cleanly-parsing routine round-tripped (parse errors don't fail)
    # 1 — at least one routine that parsed cleanly did not round-trip
    if n_round_trip_fail > 0:
        print(
            f"\nFAIL: {n_round_trip_fail} routine(s) parsed cleanly but did "
            f"not round-trip. Step 1 identity formatter is not yet correct.",
            file=sys.stderr,
        )
        return 1
    print(
        f"PASS: all {n_round_trip_ok} cleanly-parsing routines round-tripped "
        f"byte-for-byte. ({n_parse_error} parse errors are inherited from "
        f"tree-sitter-m's VistA-corpus boundary, not a fmt regression.)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
