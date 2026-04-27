"""Canonical-layout validation for ``m fmt --rules=canonical`` over VistA.

Identity-round-trip is no longer the right invariant once canonical
rules are applied (uppercasing keywords *will* change bytes). This
script enforces the new invariants:

  1. **Idempotency.** ``fmt(fmt(src)) == fmt(src)`` for every routine.
  2. **Parse equivalence.** The AST shape of the formatted output
     equals the AST shape of the input — no node types appear or
     disappear, and the pre-order sequence of node types is unchanged.
  3. **Cleanly parsing.** Sources that did not parse cleanly are
     skipped (counted separately, not failed).

Output reports the count of files where canonical layout would
*change* something, the count where it would not, idempotency / parse
failures, and elapsed time.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from m_cli.fmt.formatter import ParseError, format_source
from m_cli.fmt.rules import canonical_rules
from m_cli.parser import parse


def _ast_shape(src: bytes) -> tuple[str, ...]:
    """Pre-order tuple of *executable* node types — semantic fingerprint.

    Skips ``line`` nodes that carry no executable child. The grammar
    emits a ``line`` for any non-empty source line including those with
    nothing but whitespace, but elides them when the line is bare ``\\n``.
    Trimming a whitespace-only line therefore removes one ``line`` node
    without changing what the routine *does*. We compare on the shape
    of the executable content (commands, labels, comments, arguments,
    …) so layout-only changes don't show up as failures.
    """
    out: list[str] = []
    stack = [parse(src).root_node]
    while stack:
        node = stack.pop()
        if node.type == "line" and not _has_executable_child(node):
            continue
        out.append(node.type)
        stack.extend(reversed(node.children))
    return tuple(out)


def _has_executable_child(line_node) -> bool:
    """A ``line`` is executable when it carries a command_sequence,
    label, or comment — anything the parser turns into more than a
    raw newline."""
    return any(
        c.type in ("command_sequence", "label", "comment", "formals", "ERROR")
        for c in line_node.children
    )


def _check_one(path: Path) -> dict:
    """Run the canonical formatter on a single file and report back."""
    rules = canonical_rules()
    try:
        src = path.read_bytes()
    except OSError as e:
        return {"path": str(path), "kind": "io", "detail": str(e)}
    try:
        first = format_source(src, rules=rules)
    except ParseError:
        return {"path": str(path), "kind": "parse"}

    if first == src:
        return {"path": str(path), "kind": "unchanged"}

    try:
        second = format_source(first, rules=rules)
    except ParseError as e:
        return {
            "path": str(path),
            "kind": "post-format-parse-error",
            "detail": str(e),
        }
    if second != first:
        return {"path": str(path), "kind": "non-idempotent"}

    if _ast_shape(src) != _ast_shape(first):
        return {"path": str(path), "kind": "ast-shape-changed"}

    return {"path": str(path), "kind": "changed-ok"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="VistA Packages directory")
    parser.add_argument(
        "--sample", type=int, default=0, help="Process only first N routines (0 = all)"
    )
    parser.add_argument(
        "--show-failures", type=int, default=10, help="Show up to N failures"
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count() or 1,
        help="Parallel worker processes (default: os.cpu_count())",
    )
    args = parser.parse_args()

    if not args.root.is_dir():
        print(f"error: {args.root} is not a directory", file=sys.stderr)
        return 2

    routines = sorted(args.root.rglob("*.m"))
    if args.sample > 0:
        routines = routines[: args.sample]

    counts = {
        "unchanged": 0,
        "changed-ok": 0,
        "non-idempotent": 0,
        "ast-shape-changed": 0,
        "post-format-parse-error": 0,
        "parse": 0,
        "io": 0,
    }
    failures: list[dict] = []

    print(
        f"VistA canonical — {len(routines)} routines, "
        f"rules={[r.id for r in canonical_rules()]}, --jobs={args.jobs}"
    )
    t0 = time.monotonic()
    chunksize = max(1, len(routines) // (args.jobs * 8))
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for i, result in enumerate(
            pool.map(_check_one, routines, chunksize=chunksize), 1
        ):
            counts[result["kind"]] += 1
            if result["kind"] in {
                "non-idempotent",
                "ast-shape-changed",
                "post-format-parse-error",
                "io",
            }:
                failures.append(result)
            if i % 5000 == 0:
                elapsed = time.monotonic() - t0
                rate = i / elapsed if elapsed > 0 else 0
                print(f"  {i:>5}/{len(routines)} ({rate:.0f}/s)")
    elapsed = time.monotonic() - t0

    print()
    print(f"  total                    : {len(routines)}")
    print(f"  unchanged                : {counts['unchanged']}")
    print(f"  changed (idempotent OK)  : {counts['changed-ok']}")
    print(f"  parse errors (skipped)   : {counts['parse']}")
    print(f"  io errors                : {counts['io']}")
    print(f"  non-idempotent           : {counts['non-idempotent']}")
    print(f"  ast-shape-changed        : {counts['ast-shape-changed']}")
    print(f"  post-format parse errors : {counts['post-format-parse-error']}")
    print(f"  elapsed                  : {elapsed:.1f}s")

    if failures and args.show_failures:
        print()
        print(f"first {min(len(failures), args.show_failures)} failures:")
        for f in failures[: args.show_failures]:
            print(f"  {f['kind']:25s} {f['path']}")
        if len(failures) > args.show_failures:
            print(f"  ... and {len(failures) - args.show_failures} more")

    if failures:
        print(
            f"\nFAIL: {len(failures)} routine(s) violated canonical-layout invariants.",
            file=sys.stderr,
        )
        return 1
    print("\nPASS: every cleanly-parsing routine is idempotent under canonical layout")
    print("      and the AST shape is preserved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
