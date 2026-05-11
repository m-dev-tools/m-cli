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
from m_cli.lint.baseline import (
    DEFAULT_BASELINE_NAME,
    filter_baselined,
    find_baseline,
    load_baseline,
    write_baseline,
)
from m_cli.lint.diagnostic import Diagnostic, Severity
from m_cli.lint.fix import apply_fixes
from m_cli.lint.list_rules import list_rules_command
from m_cli.lint.output import write_output
from m_cli.lint.profiles import DEFAULT_PROFILE, list_profiles
from m_cli.lint.runner import lint_source, select_rules
from m_cli.parser import parse


def lint_command(args: argparse.Namespace) -> int:
    """Entry point for `m lint`. Returns process exit code.

    Exit codes:
      0 — success (no diagnostics, or only diagnostics below --error-on)
      1 — at least one diagnostic at or above --error-on severity
      2 — usage / argument error / rule selection error
    """
    if getattr(args, "list_rules", False):
        return list_rules_command(args)
    if getattr(args, "list_profiles", False):
        return _print_profiles()

    files = _collect_files(args.paths)
    if not files:
        # Nothing to lint is success, not failure (CLI-UX guide §3.2).
        print("m lint: no .m files found", file=sys.stdout)
        return 0

    try:
        config = load_config(Path.cwd())
    except ValueError as e:
        print(f"m lint: {e}", file=sys.stderr)
        return 2

    rule_filter = _resolve_lint_rules(args, config)
    target_engine = _resolve_target_engine(args, config)
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

    # Build the per-run LintContext. Thresholds get default-fill via
    # m_cli.lint.thresholds.validate(); the workspace index is built
    # lazily only if any selected rule opts into context-aware dispatch
    # (covers cross-routine, engine-aware, threshold-driven, and future
    # taint rules behind a single mechanism).
    workspace = None
    if any(getattr(r, "needs_context", False) for r in rules):
        from m_cli.workspace import WorkspaceIndex

        workspace = WorkspaceIndex()
        for f in files:
            try:
                workspace.add_file(f, f.read_bytes())
            except OSError:
                continue

    from m_cli.lint.context import LintContext

    # Pull preset thresholds from the active profile (e.g. `pythonic`
    # ships line_length=100 / commands_per_line=1). Only applies when
    # the rule filter resolves to a single named profile — comma-list
    # selections like `xindex,vista` don't pull preset thresholds.
    from m_cli.lint.profiles import get_profile
    from m_cli.lint.thresholds import validate as _validate_thresholds

    profile_defaults: dict[str, int] = {}
    if "," not in rule_filter and not rule_filter.startswith("M-"):
        profile = get_profile(rule_filter)
        if profile is not None:
            profile_defaults = dict(profile.default_thresholds)

    threshold_overrides = _resolve_thresholds(args, config, profile_defaults)
    try:
        thresholds = _validate_thresholds(threshold_overrides)
    except ValueError as e:
        print(f"m lint: {e}", file=sys.stderr)
        return 2
    ctx = LintContext(
        thresholds=thresholds,
        target_engine=target_engine,
        workspace=workspace,
        config=config,
    )

    if jobs == 1 or len(files) <= 1:
        all_diags, n_files, n_parse_errors = _run_serial(
            files, rules, args.lint_unparseable, config, ctx
        )
    else:
        all_diags, n_files, n_parse_errors = _run_parallel(
            files, rule_filter, args.lint_unparseable, jobs, config, ctx
        )

    if config.lint_severity_overrides:
        all_diags = _apply_severity_overrides(all_diags, config.lint_severity_overrides)

    # --update-baseline: write the current findings and exit 0 regardless
    # of severity. The user is explicitly capturing state; reporting
    # everything as a "failure" would defeat the workflow.
    if getattr(args, "update_baseline", False):
        baseline_path = _resolve_baseline_path(args)
        n_written = write_baseline(baseline_path, all_diags, baseline_path.parent)
        print(
            f"m lint: wrote {n_written} entries to {baseline_path}",
            file=sys.stderr,
        )
        return 0

    # Baseline filtering: drop diagnostics that match a baseline entry.
    n_baselined = 0
    if not getattr(args, "no_baseline", False):
        baseline_file = _find_baseline_or_explicit(args)
        if baseline_file is not None:
            try:
                entries = load_baseline(baseline_file)
            except ValueError as e:
                print(f"m lint: {e}", file=sys.stderr)
                return 2
            all_diags, n_baselined = filter_baselined(all_diags, entries, baseline_file.parent)

    # --fix: apply linked fmt fixers, then re-lint to drop fixed
    # diagnostics from the report.
    fix_result = None
    if getattr(args, "fix", False) and all_diags:
        fix_result = apply_fixes(all_diags, write=True)
        if fix_result.files_changed:
            # Re-lint only the changed files; merge with diags from
            # files we didn't touch. Keeps post-fix output accurate
            # without re-scanning everything.
            changed_set = set(fix_result.files_changed)
            untouched = [d for d in all_diags if d.path not in changed_set]
            relint = []
            for path in fix_result.files_changed:
                try:
                    src = path.read_bytes()
                except OSError:
                    continue
                tree = parse(src)
                if tree.root_node.has_error and not args.lint_unparseable:
                    continue
                relint.extend(lint_source(path, src, rules, ctx=ctx))
            if config.lint_severity_overrides:
                relint = _apply_severity_overrides(relint, config.lint_severity_overrides)
            # Re-apply baseline filter to the post-fix diagnostics so the
            # user doesn't see baselined findings reappear after a fix
            # rewrites surrounding lines.
            if not getattr(args, "no_baseline", False):
                baseline_file = _find_baseline_or_explicit(args)
                if baseline_file is not None:
                    try:
                        entries = load_baseline(baseline_file)
                    except ValueError:
                        entries = []
                    relint, _ = filter_baselined(relint, entries, baseline_file.parent)
            all_diags = sorted(
                untouched + relint,
                key=lambda d: (d.path.as_posix(), d.line, d.column, d.rule_id),
            )

    write_output(all_diags, fmt=args.format)

    if not args.quiet:
        _print_summary(
            rule_filter,
            n_files,
            n_parse_errors,
            all_diags,
            len(rules),
            target_engine,
            n_baselined=n_baselined,
            fix_result=fix_result,
        )

    fail = any(_severity_rank(d.severity) >= _severity_rank(threshold) for d in all_diags)
    return 1 if fail else 0


def _resolve_baseline_path(args: argparse.Namespace) -> Path:
    """Pick the baseline file path for --update-baseline.

    User-supplied --baseline wins; otherwise default to
    ``./.m-lint-baseline.json`` in the current working directory.
    """
    if args.baseline is not None:
        return Path(args.baseline).resolve()
    return (Path.cwd() / DEFAULT_BASELINE_NAME).resolve()


def _find_baseline_or_explicit(args: argparse.Namespace) -> Path | None:
    """Return the baseline file to apply, or ``None`` if there isn't one.

    --baseline PATH wins (and must exist); otherwise walk up from cwd
    looking for the default name.
    """
    if args.baseline is not None:
        candidate = Path(args.baseline).resolve()
        if not candidate.is_file():
            print(
                f"m lint: --baseline {candidate}: not found",
                file=sys.stderr,
            )
            return None
        return candidate
    return find_baseline(Path.cwd())


def _resolve_lint_rules(args: argparse.Namespace, config: Config) -> str:
    """CLI flag wins; otherwise config; otherwise the built-in default profile."""
    if args.rules is not None:
        return args.rules
    if config.lint_rules is not None:
        return config.lint_rules
    return DEFAULT_PROFILE


def _resolve_target_engine(args: argparse.Namespace, config: Config) -> str:
    """CLI flag wins; otherwise config; otherwise 'any' (no engine filter)."""
    flag = getattr(args, "target_engine", None)
    if flag is not None:
        return flag
    if config.lint_target_engine is not None:
        return config.lint_target_engine
    return "any"


def _resolve_thresholds(
    args: argparse.Namespace,
    config: Config,
    profile_defaults: dict[str, int] | None = None,
) -> dict[str, int]:
    """Layer profile defaults < config-file thresholds < ``--threshold`` CLI.

    Resolution order, lowest to highest precedence:
      1. ``profile_defaults`` — preset thresholds bundled with the
         active profile (e.g. ``pythonic`` ships ``line_length=100``).
         ``None`` means "no profile preset"; defaults are filled in
         later by :func:`m_cli.lint.thresholds.validate`.
      2. ``config.lint_thresholds`` — per-project ``[lint.thresholds]``
         in ``.m-cli.toml``.
      3. ``args.threshold`` — repeatable CLI ``--threshold KEY=VAL``.

    Returns a dict of overrides (the system-wide built-in defaults
    are filled in by ``thresholds.validate`` at the call site).
    """
    overrides: dict[str, int] = dict(profile_defaults or {})
    overrides.update(config.lint_thresholds)
    flag_values = getattr(args, "threshold", None) or []
    for spec in flag_values:
        if "=" not in spec:
            raise ValueError(f"--threshold expects KEY=VAL, got {spec!r}")
        key, _, val_str = spec.partition("=")
        key = key.strip()
        try:
            val = int(val_str.strip())
        except ValueError as e:
            raise ValueError(
                f"--threshold {key!r}: value must be an integer, got {val_str!r}"
            ) from e
        overrides[key] = val
    return overrides


def _print_profiles() -> int:
    """Implement ``m lint --list-profiles``.

    Resolves each registered profile so the row count reflects the
    rule set it would actually produce. Errors are printed but
    don't fail the listing — the goal is discoverability.
    """
    profiles = list_profiles()
    name_w = max((len(p.name) for p in profiles), default=0)
    print("m lint profiles:")
    for profile in profiles:
        try:
            n_rules = len(profile.selector())
        except Exception as e:  # pragma: no cover — defensive
            n_rules = -1
            print(f"  {profile.name.ljust(name_w)}  [error: {e}]")
            continue
        print(f"  {profile.name.ljust(name_w)}  {n_rules:3d} rule(s)  {profile.description}")
    return 0


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
    ctx=None,
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
    return lint_source(path, src, rules, ctx=ctx), True, None


def _run_serial(
    files: list[Path],
    rules: list,
    lint_unparseable: bool,
    _config: Config,
    ctx=None,
) -> tuple[list[Diagnostic], int, int]:
    """Lint every file in the current process (no pool overhead).

    ``rules`` is already filtered by ``config.lint_disable`` at the
    caller; we accept ``_config`` only for symmetry with the parallel
    path. ``ctx`` is the :class:`LintContext` carrying thresholds,
    target engine, workspace index, and resolved Config.
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
        all_diags.extend(lint_source(path, src, rules, ctx=ctx))
        n_files += 1
    return all_diags, n_files, n_parse_errors


def _run_parallel(
    files: list[Path],
    rule_filter: str,
    lint_unparseable: bool,
    jobs: int,
    config: Config,
    ctx=None,
) -> tuple[list[Diagnostic], int, int]:
    """Lint files across ``jobs`` worker processes.

    Workers re-run ``select_rules`` and apply the disable list themselves —
    the rule list isn't picklable but the config strings/tuples are.
    The :class:`LintContext` (when present) IS picklable (its workspace
    field uses a picklable structure) and gets shipped to each worker
    via the args tuple.
    """
    all_diags: list[Diagnostic] = []
    n_files = 0
    n_parse_errors = 0
    chunksize = max(1, len(files) // (jobs * 8))
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for diags, parseable, err in pool.map(
            _lint_one_file_packed,
            [(p, rule_filter, lint_unparseable, config.lint_disable, ctx) for p in files],
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
    Severity.STYLE: 1,
    Severity.WARNING: 2,
    Severity.ERROR: 3,
}


def _severity_rank(sev: Severity) -> int:
    return _RANK[sev]


def _print_summary(
    rule_filter: str,
    n_files: int,
    n_parse_errors: int,
    diags,
    n_rules: int,
    target_engine: str = "any",
    n_baselined: int = 0,
    fix_result=None,
) -> None:
    by_sev = {sev: 0 for sev in Severity}
    for d in diags:
        by_sev[d.severity] += 1
    rules_part = f"{n_rules} rule(s) active (--rules={rule_filter}"
    if target_engine != "any":
        rules_part += f", --target-engine={target_engine}"
    rules_part += ")"
    parts = [
        f"{n_files} file(s) checked",
        rules_part,
    ]
    if n_parse_errors:
        parts.append(f"{n_parse_errors} skipped (parse errors)")
    if n_baselined:
        parts.append(f"{n_baselined} suppressed by baseline")
    if fix_result is not None:
        n_changed = len(fix_result.files_changed)
        n_addressed = sum(fix_result.by_fixer.values())
        parts.append(f"--fix: {n_addressed} fixed across {n_changed} file(s)")
        if fix_result.skipped_parse_errors:
            parts.append(
                f"{len(fix_result.skipped_parse_errors)} skipped (parse errors during fix)"
            )
    if diags:
        parts.append(
            f"{len(diags)} finding(s): "
            f"{by_sev[Severity.ERROR]}E "
            f"{by_sev[Severity.WARNING]}W "
            f"{by_sev[Severity.STYLE]}S "
            f"{by_sev[Severity.INFO]}I"
        )
    else:
        parts.append("no findings")
    print("m lint: " + ", ".join(parts), file=sys.stderr)

    # Engine-target hint: if a meaningful share of findings are from
    # the engine-aware portability rules and target_engine is `any`,
    # nudge the user toward setting it. The threshold is a hard
    # number rather than a percentage so the hint also fires on small
    # corpora where the absolute count is what matters.
    if target_engine == "any" and diags:
        portability_rules = ("M-MOD-021", "M-MOD-022", "M-MOD-023")
        n_portability = sum(1 for d in diags if d.rule_id in portability_rules)
        if n_portability >= 50 and n_portability >= len(diags) // 4:
            print(
                f"m lint: hint — {n_portability} finding(s) from "
                f"engine-portability rules (M-MOD-021/022/023). If this "
                f"code targets a specific engine, set "
                f"`--target-engine=yottadb` (or =iris) to silence "
                f"engine-allowed $Z* uses. Persist via "
                f'`[lint] target_engine = "yottadb"` in .m-cli.toml.',
                file=sys.stderr,
            )
