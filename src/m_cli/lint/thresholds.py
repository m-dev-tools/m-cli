"""Configurable numeric thresholds for the M-MOD-NN modernization rules.

These replace the hard-coded 1980s-era byte limits in the legacy XINDEX
rule set (M-XINDX-019 line ≤ 245 bytes; M-XINDX-035 routine ≤ 20,000
bytes; M-XINDX-058 code line ≤ 15,000 bytes) with sensible modern
defaults. Users override any threshold via ``[lint.thresholds]`` in
``.m-cli.toml`` or ``--threshold KEY=VAL`` on the command line.

Adding a new threshold here requires adding it to ``KNOWN_THRESHOLDS``
(which serves as both the default-value table and the allowlist for
config-file validation). Unknown keys are rejected at config-load time
to catch typos that would otherwise silently no-op.
"""

from __future__ import annotations

# Threshold name → default value. Keys are checked against this set
# when loading config; values are merged with overrides in `validate()`.
KNOWN_THRESHOLDS: dict[str, int] = {
    # M-MOD-001: line longer than this (bytes). 200 is the modern
    # readability ceiling, way below the legacy 245-byte SAC limit
    # which dated to early-90s terminal widths.
    "line_length": 200,
    # M-MOD-002: a *code* line (non-comment-only) longer than this.
    # 1000 is a "pathological" threshold — no normal code line gets
    # this long. Replaces M-XINDX-058's 15,000-byte limit which
    # dated to a long-vanished compiled-token-table size.
    "code_line_length": 1000,
    # M-MOD-003: routine source longer than this many lines.
    # Replaces M-XINDX-035's 20,000-byte limit (a MUMPS-77 routine
    # cap that has not applied for two engine generations).
    "routine_lines": 1000,
    # M-MOD-004: label body (lines from the label header to the next
    # label or EOF) longer than this. New rule — encourages
    # decomposition of mega-labels.
    "label_lines": 50,
    # M-MOD-005: cyclomatic complexity per label > this. Standard
    # McCabe formula: decisions + 1, where decisions count IF, FOR,
    # and each postconditional. Industry baseline is ~10–15; we ship
    # 15 as a conservative ceiling that stays out of small-routine
    # noise.
    "cyclomatic": 15,
    # M-MOD-006: cognitive complexity per label > this. Sonar-style
    # — decisions count once each, plus a +depth penalty for each
    # decision sitting in a dot-block of depth N. Captures the
    # "how hard is this to follow" metric better than raw cyclomatic.
    "cognitive": 20,
    # M-MOD-007: dot-block nesting depth > this. Each ``.`` in a
    # ``dot_block_prefix`` adds one level. Five levels is already
    # painful to read; legitimate code rarely needs more than 3–4.
    "dot_block_depth": 5,
    # M-MOD-008: number of formal arguments to a label > this. M is
    # untyped and positional; readability collapses past about 7.
    "argument_count": 7,
    # M-MOD-009: number of commands on a single line > this. M permits
    # arbitrary command sequences per line; modern style limits to
    # 3 to keep diffs readable and reduce review-review-review fatigue.
    "commands_per_line": 3,
    # M-MOD-029: minimum comment density per label (percent). Counts
    # the fraction of body lines containing a comment (full-line
    # ``;...`` or inline ``code ;...``). Below this percentage,
    # M-MOD-029 flags the label as under-documented. 10% is a low
    # bar — a 30-line label needs only 3 lines with comments.
    "comment_density_pct": 10,
}


def validate(overrides: dict[str, int] | None) -> dict[str, int]:
    """Return a complete threshold dict with overrides applied.

    Defaults from :data:`KNOWN_THRESHOLDS` fill in any threshold the
    caller did not override. Raises :class:`ValueError` for unknown
    keys (likely typos) or non-positive values.

    Passing ``None`` is equivalent to passing ``{}`` — returns the
    pure defaults.
    """
    result = dict(KNOWN_THRESHOLDS)
    if not overrides:
        return result
    for key, val in overrides.items():
        if key not in KNOWN_THRESHOLDS:
            known = ", ".join(sorted(KNOWN_THRESHOLDS))
            raise ValueError(
                f"unknown threshold {key!r} (known thresholds: {known})"
            )
        if not isinstance(val, int) or isinstance(val, bool) or val <= 0:
            raise ValueError(
                f"threshold {key!r} must be a positive integer, got {val!r}"
            )
        result[key] = val
    return result


__all__ = ["KNOWN_THRESHOLDS", "validate"]
