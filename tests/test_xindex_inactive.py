"""Pin the M-XINDX rules that are intentionally inactive.

Five XINDEX rules ship as registered for compatibility with the
^XINDEX numeric-code mapping but never fire on real M source.
They cover patterns subsumed by tree-sitter's ERROR nodes (which
M-XINDX-021 catches first) or grammar-level checks the parser
already enforces. Keeping them registered preserves the 1:1 ID
mapping with VA's ^XINDEX scanner; making the inactivity *explicit*
via this test means a future grammar change that does start
firing one of them surfaces as either a deliberate upgrade or a
regression — never silent drift.

If one of these rules starts firing on the modern or VistA corpus,
either:
  - the grammar legitimately got more permissive (the rule is now
    relevant — promote it out of this list and document the
    activation in CLAUDE.md / README), OR
  - the grammar regressed (file a tree-sitter-m bug).

Either way, a deliberate decision is required, and that's the
point of pinning the inactivity.
"""

from __future__ import annotations

# The five intentionally-silent rule ids. Sourced from TODO.md and
# confirmed by the 2026-04-30 audit (`docs/m-linter-status-2026-04-30.md`
# §5.5).
INTENTIONALLY_SILENT_XINDEX_RULES = frozenset(
    {
        "M-XINDX-015",  # Duplicate label
        "M-XINDX-021",  # Syntax error in line — implicitly caught by tree-sitter
        "M-XINDX-027",  # $VIEW function used
        "M-XINDX-031",  # $Z* intrinsic function used (now superseded by M-MOD-023)
        "M-XINDX-054",  # $SYSTEM access (Kernel-only)
    }
)


def test_intentionally_silent_rules_are_registered() -> None:
    """Each silent rule must remain in the registry — keeping them
    is what preserves the XINDEX 1:1 numeric-code mapping."""
    from m_cli.lint.rules import all_rules

    registered = {r.id for r in all_rules()}
    missing = INTENTIONALLY_SILENT_XINDEX_RULES - registered
    assert not missing, (
        f"intentionally-silent XINDEX rules missing from registry: "
        f"{sorted(missing)}. Either add them back or remove them from "
        f"the test pin and from the README."
    )


def test_silent_rules_have_xindex_tag() -> None:
    """Sanity: these are XINDEX rules, so they must carry the
    `xindex` provenance tag and ride in the `xindex` profile."""
    from m_cli.lint.rules import all_rules

    by_id = {r.id: r for r in all_rules()}
    for rule_id in sorted(INTENTIONALLY_SILENT_XINDEX_RULES):
        r = by_id[rule_id]
        assert "xindex" in r.tags, (
            f"{rule_id} is in the silent set but missing `xindex` tag"
        )


def test_silent_rules_remain_silent_on_a_clean_fixture() -> None:
    """A minimal well-formed M source must not trigger any of the
    silent rules. If one fires, either:
      - the grammar started parsing in a way that exposes it, or
      - the rule's check function broke its silence guarantee.
    Either case wants a deliberate decision, not a quiet flip.
    """
    from pathlib import Path

    from m_cli.lint import lint_source, select_rules

    # Single-label routine; valid syntax; no $VIEW, no duplicate
    # labels, no $SYSTEM, no $Z* — none of the silent patterns.
    src = b"DEMO\n SET X=1\n WRITE X,!\n QUIT\n"

    rules = select_rules("xindex,vista")
    diagnostics = lint_source(Path("demo.m"), src, rules)
    fired_silent = {
        d.rule_id
        for d in diagnostics
        if d.rule_id in INTENTIONALLY_SILENT_XINDEX_RULES
    }
    assert not fired_silent, (
        f"intentionally-silent rules fired on a clean fixture: "
        f"{sorted(fired_silent)}. Either the rule has come alive "
        f"(promote out of the silent set) or the fixture is no "
        f"longer clean (expand it)."
    )
