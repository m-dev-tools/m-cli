"""`m lint` command implementation.

Argparse-driven. Resolves paths to .m files, runs the selected rule
family, and writes results in the requested format.

When ``--jobs > 1`` (the default — ``os.cpu_count()``), per-file lint
runs in a ``ProcessPoolExecutor``. Each routine is independent, so
linear scale-up is the expected pattern.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from m_cli.config import Config, load_config
from m_cli.lint.diagnostic import Diagnostic, Severity
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
        config = load_config(Path.cwd())
    except ValueError as e:
        print(f"m lint: {e}", file=sys.stderr)
        return 2

    rule_filter = _resolve_lint_rules(args, config)
    try:
        rules = select_rules(rule_filter)
    except ValueError as e:
        print(f"m lint: {e}", file=sys.stderr)
        return 2
    if config.lint_disable:
        rules = [r for r in rules if r.id not in config.lint_disable]
    if not rules:
        print(f"m lint: no rules matched --rules={rule_filter!r}", file=sys.stderr)
        return 2

    threshold = _severity_from_string(args.error_on)
    if threshold is None:
        print(f"m lint: invalid --error-on value: {args.error_on!r}", file=sys.stderr)
        return 2

    jobs = args.jobs if args.jobs is not None else (os.cpu_count() or 1)
    if jobs < 1:
        print(f"m lint: --jobs must be >= 1 (got {jobs})", file=sys.stderr)
        return 2

    if jobs == 1 or len(files) <= 1:
        all_diags, n_files, n_parse_errors = _run_serial(
            files, rules, args.lint_unparseable, config
        )
    else:
        all_diags, n_files, n_parse_errors = _run_parallel(
            files, rule_filter, args.lint_unparseable, jobs, config
        )

    if config.lint_severity_overrides:
        all_diags = _apply_severity_overrides(all_diags, config.lint_severity_overrides)

    write_output(all_diags, fmt=args.format)

    if not args.quiet:
        _print_summary(rule_filter, n_files, n_parse_errors, all_diags, len(rules))

    fail = any(_severity_rank(d.severity) >= _severity_rank(threshold) for d in all_diags)
    return 1 if fail else 0


def _resolve_lint_rules(args: argparse.Namespace, config: Config) -> str:
    """CLI flag wins; otherwise config; otherwise the historical default."""
    if args.rules is not None:
        return args.rules
    if config.lint_rules is not None:
        return config.lint_rules
    return "xindex"


def _apply_severity_overrides(
    diags: list[Diagnostic], overrides: dict[str, Severity]
) -> list[Diagnostic]:
    """Return a new list with per-rule severity remapped per ``overrides``.
    Diagnostics whose rule id has no override are passed through unchanged."""
    if not overrides:
        return diags
    return [
        dataclasses.replace(d, severity=overrides[d.rule_id]) if d.rule_id in overrides else d
        for d in diags
    ]


# ---------------------------------------------------------------------------
# Per-file work (single source of truth for both serial and parallel paths)
# ---------------------------------------------------------------------------


def _lint_one_file(
    path: Path,
    rule_filter: str,
    lint_unparseable: bool,
    disable: tuple[str, ...] = (),
) -> tuple[list[Diagnostic], bool, str | None]:
    """Read, parse, and lint a single file.

    Returns (diagnostics, parseable, error_message). On unrecoverable
    I/O failure, ``error_message`` carries a human-readable string.
    """
    try:
        src = path.read_bytes()
    except OSError as e:
        return [], True, f"{path}: {e}"
    tree = parse(src)
    if tree.root_node.has_error and not lint_unparseable:
        return [], False, None
    rules = select_rules(rule_filter)
    if disable:
        rules = [r for r in rules if r.id not in disable]
    return lint_source(path, src, rules), True, None


def _run_serial(
    files: list[Path], rules: list, lint_unparseable: bool, _config: Config
) -> tuple[list[Diagnostic], int, int]:
    """Lint every file in the current process (no pool overhead).

    ``rules`` is already filtered by ``config.lint_disable`` at the
    caller; we accept ``_config`` only for symmetry with the parallel path.
    """
    all_diags: list[Diagnostic] = []
    n_files = 0
    n_parse_errors = 0
    for path in files:
        try:
            src = path.read_bytes()
        except OSError as e:
            print(f"m lint: {path}: {e}", file=sys.stderr)
            continue
        tree = parse(src)
        if tree.root_node.has_error and not lint_unparseable:
            n_parse_errors += 1
            continue
        all_diags.extend(lint_source(path, src, rules))
        n_files += 1
    return all_diags, n_files, n_parse_errors


def _run_parallel(
    files: list[Path],
    rule_filter: str,
    lint_unparseable: bool,
    jobs: int,
    config: Config,
) -> tuple[list[Diagnostic], int, int]:
    """Lint files across ``jobs`` worker processes.

    Workers re-run ``select_rules`` and apply the disable list themselves —
    the rule list isn't picklable but the config strings/tuples are.
    """
    all_diags: list[Diagnostic] = []
    n_files = 0
    n_parse_errors = 0
    chunksize = max(1, len(files) // (jobs * 8))
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for diags, parseable, err in pool.map(
            _lint_one_file_packed,
            [(p, rule_filter, lint_unparseable, config.lint_disable) for p in files],
            chunksize=chunksize,
        ):
            if err is not None:
                print(f"m lint: {err}", file=sys.stderr)
                continue
            if not parseable:
                n_parse_errors += 1
                continue
            all_diags.extend(diags)
            n_files += 1
    all_diags.sort(key=lambda d: (d.path.as_posix(), d.line, d.column, d.rule_id))
    return all_diags, n_files, n_parse_errors


def _lint_one_file_packed(args):
    """ProcessPoolExecutor.map needs a single-arg callable."""
    return _lint_one_file(*args)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _print_summary(
    rule_filter: str, n_files: int, n_parse_errors: int, diags, n_rules: int
) -> None:
    by_sev = {sev: 0 for sev in Severity}
    for d in diags:
        by_sev[d.severity] += 1
    parts = [
        f"{n_files} file(s) checked",
        f"{n_rules} rule(s) active (--rules={rule_filter})",
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
