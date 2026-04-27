"""`m lint` command implementation.

Argparse-driven. Resolves paths to .m files, runs the selected rule
family, and writes results in the requested format.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from m_cli.lint.diagnostic import Severity
from m_cli.lint.output import write_output
from m_cli.lint.runner import lint_source, select_rules
from m_cli.parser import parse


def lint_command(args: argparse.Namespace) -> int:
    """Entry point for `m lint`. Returns process exit code.

    Exit codes:
      0 — success (no diagnostics, or only diagnostics below --error-on)
      1 — at least one diagnostic at or above --error-on severity
      2 — usage / argument error / rule selection error
    """
    files = _collect_files(args.paths)
    if not files:
        print("m lint: no .m files found", file=sys.stderr)
        return 2

    try:
        rules = select_rules(args.rules)
    except ValueError as e:
        print(f"m lint: {e}", file=sys.stderr)
        return 2
    if not rules:
        print(f"m lint: no rules matched --rules={args.rules!r}", file=sys.stderr)
        return 2

    threshold = _severity_from_string(args.error_on)
    if threshold is None:
        print(f"m lint: invalid --error-on value: {args.error_on!r}", file=sys.stderr)
        return 2

    all_diags = []
    n_files = 0
    n_parse_errors = 0
    for path in files:
        try:
            src = path.read_bytes()
        except OSError as e:
            print(f"m lint: {path}: {e}", file=sys.stderr)
            continue
        # Run only on routines that parse cleanly. (XINDEX behaves
        # similarly: severe parse errors short-circuit further checks.)
        tree = parse(src)
        if tree.root_node.has_error and not args.lint_unparseable:
            n_parse_errors += 1
            continue
        diags = lint_source(path, src, rules)
        all_diags.extend(diags)
        n_files += 1

    write_output(all_diags, fmt=args.format)

    if not args.quiet:
        _print_summary(args, n_files, n_parse_errors, all_diags, len(rules))

    # Exit code based on threshold
    fail = any(_severity_rank(d.severity) >= _severity_rank(threshold) for d in all_diags)
    return 1 if fail else 0


def _collect_files(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(sorted(p.rglob("*.m")))
        elif p.is_file():
            out.append(p)
        elif p.exists():
            out.append(p)
        else:
            print(f"m lint: {p}: no such file or directory", file=sys.stderr)
    return out


def _severity_from_string(s: str) -> Severity | None:
    s = s.strip().lower()
    for sev in Severity:
        if sev.value == s:
            return sev
    return None


_RANK = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.STANDARD: 2,
    Severity.FATAL: 3,
}


def _severity_rank(sev: Severity) -> int:
    return _RANK[sev]


def _print_summary(args, n_files: int, n_parse_errors: int, diags, n_rules: int) -> None:
    by_sev = {sev: 0 for sev in Severity}
    for d in diags:
        by_sev[d.severity] += 1
    parts = [
        f"{n_files} file(s) checked",
        f"{n_rules} rule(s) active (--rules={args.rules})",
    ]
    if n_parse_errors:
        parts.append(f"{n_parse_errors} skipped (parse errors)")
    if diags:
        parts.append(
            f"{len(diags)} finding(s): "
            f"{by_sev[Severity.FATAL]}F "
            f"{by_sev[Severity.STANDARD]}S "
            f"{by_sev[Severity.WARNING]}W "
            f"{by_sev[Severity.INFO]}I"
        )
    else:
        parts.append("no findings")
    print("m lint: " + ", ".join(parts), file=sys.stderr)
