"""Modern-corpus lint regression gate for `m lint --rules modern`.

Walks the catalogued non-VistA, post-2010 M corpora (see
``docs/m-corpus-catalog.md``), runs the chosen rule set over each
subtree, and reports per-corpus + aggregate finding counts. Optionally
compares against a checked-in baseline (``scripts/lint_modern.baseline.json``)
and fails CI when any corpus diverges by more than the allowed
threshold.

Usage:

    python scripts/lint_modern.py                      # use config defaults
    python scripts/lint_modern.py --rules=modern       # explicit rule filter
    python scripts/lint_modern.py --update-baseline    # refresh baseline JSON
    python scripts/lint_modern.py --regression-threshold 0.10
                                                       # fail on >10% drift

Companion to ``scripts/vista_lint.py`` (the legacy VA-flavoured
gate). Defaults assume the corpus has been cloned into
``~/m-dev-tools/m-modern-corpus/`` per the layout in the catalog; pass
``--corpus-root`` to override, or ``--corpus`` (repeatable) to point
at individual subtrees.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from m_cli.lint.runner import lint_source, select_rules
from m_cli.parser import parse

# Default corpus layout — matches docs/m-corpus-catalog.md "Suggested layout".
# Each entry: (subdir name, optional .m sub-path filter for partial repos).
DEFAULT_CORPUS_LAYOUT: tuple[tuple[str, str | None], ...] = (
    ("ydbtest", None),  # YottaDB/YDBTest — entire tree
    ("mgsql", None),  # chrisemunt/mgsql — entire tree
    ("ydbocto-aux", None),  # YottaDB/YDBOcto, src/aux only (cloned that way)
    # Optional Tier-1/2 supplements (no-ops if absent):
    ("ewd", None),  # robtweed/EWD
    ("m-web-server", None),  # shabiel/M-Web-Server
)

DEFAULT_BASELINE_PATH = Path(__file__).parent / "lint_modern.baseline.json"
DEFAULT_CORPUS_ROOT = Path.home() / "m-dev-tools" / "m-modern-corpus"
DEFAULT_REGRESSION_THRESHOLD = 0.10  # 10% drift fails the gate


@dataclass(frozen=True)
class CorpusResult:
    """Per-corpus rollup written into the baseline JSON."""

    name: str
    routines_total: int
    routines_linted: int
    routines_skipped_parse: int
    routines_io_error: int
    findings_total: int
    by_rule: dict[str, int]
    by_severity: dict[str, int]
    elapsed_s: float


# ---------------------------------------------------------------------------
# Per-file work (mirrors vista_lint._lint_one)
# ---------------------------------------------------------------------------


def _lint_one(args: tuple[Path, str, str]) -> tuple[Path, list, bool, bool]:
    """(path, rule_filter, target_engine) -> (path, diags, parseable, io_error)."""
    from m_cli.lint.context import LintContext
    from m_cli.lint.thresholds import validate as validate_thresholds

    path, rule_filter, target_engine = args
    try:
        src = path.read_bytes()
    except OSError:
        return path, [], True, True
    tree = parse(src)
    if tree.root_node.has_error:
        return path, [], False, False
    rules = select_rules(rule_filter)
    ctx = LintContext(
        thresholds=validate_thresholds(None),
        target_engine=target_engine,
    )
    return path, lint_source(path, src, rules, ctx=ctx), True, False


# ---------------------------------------------------------------------------
# Per-corpus runner
# ---------------------------------------------------------------------------


def _lint_corpus(
    name: str,
    root: Path,
    rule_filter: str,
    jobs: int,
    target_engine: str = "any",
) -> CorpusResult:
    routines = sorted(root.rglob("*.m"))
    n_total = len(routines)
    if n_total == 0:
        return CorpusResult(
            name=name,
            routines_total=0,
            routines_linted=0,
            routines_skipped_parse=0,
            routines_io_error=0,
            findings_total=0,
            by_rule={},
            by_severity={},
            elapsed_s=0.0,
        )

    rule_counts: Counter[str] = Counter()
    sev_counts: Counter[str] = Counter()
    n_linted = 0
    n_skipped_parse = 0
    n_io = 0

    work = [(p, rule_filter, target_engine) for p in routines]
    chunksize = max(1, len(work) // (jobs * 8))
    t0 = time.monotonic()
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for path, diags, parseable, io_error in pool.map(_lint_one, work, chunksize=chunksize):
            if io_error:
                n_io += 1
            elif not parseable:
                n_skipped_parse += 1
            else:
                n_linted += 1
                for d in diags:
                    rule_counts[d.rule_id] += 1
                    sev_counts[d.severity.value] += 1
    elapsed = time.monotonic() - t0

    return CorpusResult(
        name=name,
        routines_total=n_total,
        routines_linted=n_linted,
        routines_skipped_parse=n_skipped_parse,
        routines_io_error=n_io,
        findings_total=sum(rule_counts.values()),
        by_rule=dict(rule_counts),
        by_severity=dict(sev_counts),
        elapsed_s=elapsed,
    )


# ---------------------------------------------------------------------------
# Baseline I/O
# ---------------------------------------------------------------------------


def _load_baseline(path: Path) -> dict[str, dict] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"warning: could not read baseline {path}: {e}", file=sys.stderr)
        return None


def _write_baseline(path: Path, results: list[CorpusResult], rule_filter: str) -> None:
    payload = {
        "rule_filter": rule_filter,
        "corpora": {
            r.name: {
                "routines_total": r.routines_total,
                "routines_linted": r.routines_linted,
                "findings_total": r.findings_total,
                "by_rule": r.by_rule,
                "by_severity": r.by_severity,
            }
            for r in results
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _compare_to_baseline(
    results: list[CorpusResult],
    baseline: dict[str, dict],
    threshold: float,
) -> int:
    """Return number of regressions found (per-corpus over the threshold)."""
    n_regressions = 0
    for r in results:
        ref = baseline.get("corpora", {}).get(r.name)
        if ref is None:
            continue  # corpus is new since baseline; skip rather than fail
        ref_total = ref.get("findings_total", 0)
        cur_total = r.findings_total
        if ref_total == 0:
            # Avoid divide-by-zero; any new finding is a regression.
            if cur_total > 0:
                print(
                    f"  REGRESSION  {r.name}: 0 → {cur_total} findings (was clean)",
                    file=sys.stderr,
                )
                n_regressions += 1
            continue
        drift = abs(cur_total - ref_total) / ref_total
        if drift > threshold:
            print(
                f"  REGRESSION  {r.name}: {ref_total} → {cur_total} "
                f"({drift * 100:.1f}% drift, threshold {threshold * 100:.0f}%)",
                file=sys.stderr,
            )
            n_regressions += 1
    return n_regressions


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=DEFAULT_CORPUS_ROOT,
        help=(
            f"Root containing the corpus subdirs "
            f"(default: {DEFAULT_CORPUS_ROOT}). Each subdir from the catalog "
            f"layout is walked separately."
        ),
    )
    parser.add_argument(
        "--corpus",
        action="append",
        default=None,
        metavar="NAME=PATH",
        help=(
            "Override / supplement the default corpus layout. Repeatable. "
            "Format: NAME=PATH (e.g. --corpus ydbtest=/data/ydbtest). When "
            "given, replaces the default list entirely."
        ),
    )
    parser.add_argument(
        "--rules",
        default="modern",
        help=(
            "Profile name(s) and/or comma-separated rule IDs. Default "
            "`modern` runs the M-MOD-NN ruleset (initially empty; ships "
            "incrementally). Pass `default` to compare against the legacy "
            "engine-neutral baseline."
        ),
    )
    try:
        baseline_default = DEFAULT_BASELINE_PATH.relative_to(Path.cwd())
    except ValueError:
        baseline_default = DEFAULT_BASELINE_PATH
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE_PATH,
        help=f"Baseline JSON path (default: {baseline_default})",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write the current run's results to the baseline file and exit 0.",
    )
    parser.add_argument(
        "--regression-threshold",
        type=float,
        default=DEFAULT_REGRESSION_THRESHOLD,
        help=(
            f"Per-corpus relative drift that fails the gate (default: "
            f"{DEFAULT_REGRESSION_THRESHOLD * 100:.0f}%%)."
        ),
    )
    parser.add_argument(
        "--target-engine",
        choices=("any", "yottadb", "iris"),
        default="any",
        help=(
            "Target M engine for engine-aware rules (M-MOD-021..023). "
            "Default 'any' means strict ANSI; 'yottadb' / 'iris' relax "
            "the rule against per-engine allowlists from m-standard."
        ),
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count() or 1,
        help="Parallel worker processes (default: os.cpu_count())",
    )
    args = parser.parse_args()

    # Resolve corpus list. CLI override wins; otherwise default layout
    # filtered by what's actually on disk.
    if args.corpus:
        corpus_list: list[tuple[str, Path]] = []
        for spec in args.corpus:
            if "=" not in spec:
                print(f"error: --corpus expects NAME=PATH, got {spec!r}", file=sys.stderr)
                return 2
            name, _, path_str = spec.partition("=")
            corpus_list.append((name.strip(), Path(path_str).expanduser()))
    else:
        corpus_list = []
        for name, _ in DEFAULT_CORPUS_LAYOUT:
            path = args.corpus_root / name
            if path.is_dir():
                corpus_list.append((name, path))
        if not corpus_list:
            print(
                f"error: no corpora found under {args.corpus_root}\n"
                f"  expected subdirs: {[name for name, _ in DEFAULT_CORPUS_LAYOUT]}\n"
                f"  see scripts/setup_modern_corpus.sh for clone instructions",
                file=sys.stderr,
            )
            return 2

    try:
        rules = select_rules(args.rules)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if len(rules) == 0:
        print(
            f"warning: --rules={args.rules!r} resolved to 0 rules — nothing to "
            f"check. Try `m lint --list-profiles` to see what's available.",
            file=sys.stderr,
        )
        # Not a hard error: if `modern` is empty, the gate is a no-op.

    print(
        f"Modern lint — corpora={len(corpus_list)}, rules={args.rules} "
        f"({len(rules)} rules), jobs={args.jobs}"
    )

    # Per-corpus run
    results: list[CorpusResult] = []
    for name, path in corpus_list:
        result = _lint_corpus(name, path, args.rules, args.jobs, args.target_engine)
        results.append(result)
        print(
            f"  {name:14s} {result.routines_linted:>5}/"
            f"{result.routines_total:<5} routines  "
            f"{result.findings_total:>6} findings  "
            f"{result.elapsed_s:>5.1f}s"
        )

    print()
    print("Aggregate:")
    total_routines = sum(r.routines_linted for r in results)
    total_findings = sum(r.findings_total for r in results)
    total_elapsed = sum(r.elapsed_s for r in results)
    print(f"  routines linted  : {total_routines}")
    print(f"  total findings   : {total_findings}")
    print(f"  wall time        : {total_elapsed:.1f}s")

    # Baseline handling
    if args.update_baseline:
        _write_baseline(args.baseline, results, args.rules)
        print(f"\nBaseline written to {args.baseline}")
        return 0

    baseline = _load_baseline(args.baseline)
    if baseline is None:
        print(
            f"\nNo baseline at {args.baseline} — run with --update-baseline to "
            "create one. Skipping regression check.",
            file=sys.stderr,
        )
        return 0

    print()
    print(f"Regression check (threshold {args.regression_threshold * 100:.0f}%):")
    n_regressions = _compare_to_baseline(results, baseline, args.regression_threshold)
    if n_regressions == 0:
        print("  all corpora within threshold.")
        return 0
    print(f"\nFAILED: {n_regressions} corpus(es) drifted beyond threshold.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
