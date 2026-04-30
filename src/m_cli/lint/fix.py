"""Auto-fix orchestration for ``m lint --fix``.

For every diagnostic whose rule has a ``fixer_id``, look up the
corresponding ``m fmt`` rule and apply it to the file. Each unique
fixer runs once per file (regardless of how many diagnostics it
covers) — diagnostics of the same kind collapse to a single rewrite.

Returns enough metadata for the CLI to print a clean summary:
which files changed, which fixers ran, and how many fixable
diagnostics were addressed.

This module owns no policy: it doesn't decide WHEN to fix, only HOW.
The CLI handles the user opt-in (``--fix``), preview (``--check``),
re-lint, and exit-code logic.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from m_cli.lint.diagnostic import Diagnostic


@dataclass
class FixResult:
    """Summary of what ``apply_fixes`` did."""

    files_changed: list[Path]
    """Files whose bytes on disk are now different."""

    fixable_count: int
    """Number of diagnostics that had a fixer_id (whether the fix
    actually changed bytes or not — useful for the summary line)."""

    unfixable_count: int
    """Diagnostics whose rule has no fixer_id."""

    by_fixer: dict[str, int]
    """Per-fixer count: ``{fixer_id: diagnostics_addressed}``."""

    skipped_parse_errors: list[Path]
    """Files where the fmt rule refused to apply because of parse
    errors. The original lint diagnostics still surface, but no
    auto-fix is attempted."""


def apply_fixes(
    diags: list[Diagnostic], *, write: bool = True
) -> FixResult:
    """Apply auto-fixes for every fixable diagnostic in ``diags``.

    Algorithm:
      1. Group diagnostics by ``(path, fixer_id)``.
      2. For each unique ``(path, fixer_id)``, read the file, run
         the fmt rule, and (if ``write``) write the result back.
      3. Track ``files_changed`` only for paths whose bytes
         actually moved.

    With ``write=False`` the helper still computes the post-fix bytes
    so the CLI can offer a preview (``--check`` style), but doesn't
    touch disk. Returns the same :class:`FixResult` either way.
    """
    # Lazy imports — fmt.rules imports from lint._keywords, so we'd
    # circularly import if we top-leveled these.
    from m_cli.fmt.formatter import ParseError
    from m_cli.fmt.rules import rule_by_id

    fixable_by_path: dict[Path, dict[str, list[Diagnostic]]] = defaultdict(
        lambda: defaultdict(list)
    )
    fixable_count = 0
    unfixable_count = 0

    for d in diags:
        # Need to round-trip through the fmt registry: the lint rule's
        # `fixer_id` is the public string handle (e.g. "trim-trailing-
        # whitespace"), and `rule_by_id` resolves it back to the
        # callable FmtRule.
        rule = _lookup_lint_rule(d.rule_id)
        if rule is None or not rule.fixer_id:
            unfixable_count += 1
            continue
        if rule_by_id(rule.fixer_id) is None:
            # Lint rule references a fixer that isn't registered —
            # treat as unfixable so the user still sees the diagnostic.
            unfixable_count += 1
            continue
        fixable_by_path[d.path][rule.fixer_id].append(d)
        fixable_count += 1

    files_changed: list[Path] = []
    by_fixer: dict[str, int] = defaultdict(int)
    skipped_parse_errors: list[Path] = []

    for path, fixers in fixable_by_path.items():
        try:
            original = path.read_bytes()
        except OSError:
            continue
        current = original
        parse_failed = False
        for fixer_id, addressed in fixers.items():
            fmt_rule = rule_by_id(fixer_id)
            if fmt_rule is None:
                continue  # already filtered above; defensive
            try:
                # format_source raises ParseError on dirty parses.
                # Use the rule's apply directly so we run a single
                # rule rather than the full pipeline.
                current = fmt_rule.apply(current)
            except ParseError:
                parse_failed = True
                break
            by_fixer[fixer_id] += len(addressed)
        if parse_failed:
            skipped_parse_errors.append(path)
            # Don't count by_fixer for this file — back them out.
            for fixer_id, addressed in fixers.items():
                by_fixer[fixer_id] = max(0, by_fixer[fixer_id] - len(addressed))
            continue
        if current != original:
            if write:
                path.write_bytes(current)
            files_changed.append(path)

    return FixResult(
        files_changed=files_changed,
        fixable_count=fixable_count,
        unfixable_count=unfixable_count,
        by_fixer=dict(by_fixer),
        skipped_parse_errors=skipped_parse_errors,
    )


def _lookup_lint_rule(rule_id: str):
    """Look up a registered lint rule by id. Returns ``None`` if unknown.

    We avoid importing :func:`m_cli.lint.runner.all_rules` at module
    load time to keep the dependency graph linear; resolve lazily.
    """
    from m_cli.lint.runner import all_rules

    return next((r for r in all_rules() if r.id == rule_id), None)
