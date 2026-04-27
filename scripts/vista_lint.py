"""VistA lint validation for `m lint` (Step 2: linter).

Runs the active rule family across the full 39,330-routine VistA corpus
and reports:

  - rules-active count
  - per-rule firing counts
  - top-N noisiest routines
  - elapsed time (must stay under the 120 s budget per §3.5 of
    m-tooling-tier1.md)

Use --sample N to lint only the first N routines (smoke test).

Use --rules to override the rule family (default: xindex).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from m_cli.lint.runner import lint_source, select_rules
from m_cli.parser import parse


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Root of the VistA Packages directory")
    parser.add_argument("--sample", type=int, default=0, help="Lint only first N routines (0 = all)")
    parser.add_argument("--rules", default="xindex", help="Rule family or comma-separated IDs")
    parser.add_argument("--top", type=int, default=10, help="Show top-N noisiest routines")
    args = parser.parse_args()

    if not args.root.is_dir():
        print(f"error: {args.root} is not a directory", file=sys.stderr)
        return 2

    try:
        rules = select_rules(args.rules)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    routines = sorted(args.root.rglob("*.m"))
    if args.sample > 0:
        routines = routines[: args.sample]

    n_total = len(routines)
    n_linted = 0
    n_skipped_parse = 0
    n_io = 0
    rule_counts: Counter[str] = Counter()
    sev_counts: Counter[str] = Counter()
    per_routine: list[tuple[int, Path]] = []  # (n_findings, path)

    print(f"VistA lint — {n_total} routines, --rules={args.rules} ({len(rules)} rules)")
    t0 = time.monotonic()

    for i, path in enumerate(routines, 1):
        try:
            src = path.read_bytes()
        except OSError:
            n_io += 1
            continue
        tree = parse(src)
        if tree.root_node.has_error:
            n_skipped_parse += 1
            continue
        diags = lint_source(path, src, rules)
        n_linted += 1
        for d in diags:
            rule_counts[d.rule_id] += 1
            sev_counts[d.severity.value] += 1
        if diags:
            per_routine.append((len(diags), path))

        if i % 5000 == 0:
            elapsed = time.monotonic() - t0
            rate = i / elapsed if elapsed > 0 else 0
            print(f"  {i:>5}/{n_total} ({rate:.0f}/s)")

    elapsed = time.monotonic() - t0

    print()
    print(f"  total routines  : {n_total}")
    print(f"  linted          : {n_linted}")
    print(f"  skipped (parse) : {n_skipped_parse}")
    print(f"  io errors       : {n_io}")
    print(f"  total findings  : {sum(rule_counts.values())}")
    print(f"  routines flagged: {len(per_routine)}  ({100*len(per_routine)/max(n_linted,1):.1f}%)")
    print(f"  elapsed         : {elapsed:.1f}s ({n_linted/elapsed:.0f} routines/s)")

    print()
    print("By rule (descending):")
    for rule_id, count in rule_counts.most_common():
        print(f"  {rule_id:20s} {count:>7}")

    print()
    print("By severity:")
    for sev in ("fatal", "standard", "warning", "info"):
        print(f"  {sev:9s} {sev_counts.get(sev, 0):>7}")

    if per_routine and args.top > 0:
        per_routine.sort(reverse=True)
        print()
        print(f"Top {min(args.top, len(per_routine))} noisiest routines:")
        for n, path in per_routine[: args.top]:
            print(f"  {n:>4}  {path}")

    # Performance gate: 120 s per §3.5 of m-tooling-tier1.md
    if elapsed > 120 and args.sample == 0:
        print(
            f"\nWARNING: lint took {elapsed:.0f}s, above the 120s §3.5 budget.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
