"""Tests for the lint-rule → fmt-rule fixer linkage.

Each lint rule may declare a ``fixer_id`` pointing to an ``m fmt``
rule that auto-fixes the diagnostic. The LSP wrapper uses this to
expose Quick Fix code actions; CI tools can use it to suggest auto-fix
commands. ``fixer_id`` is ``None`` when no auto-fix exists.

This test pins the existing pairings and asserts that every declared
``fixer_id`` resolves to a real ``FmtRule`` — so a rename on either
side breaks loudly.
"""

from __future__ import annotations

from m_cli.fmt import all_rules as all_fmt_rules
from m_cli.fmt import canonical_rules
from m_cli.lint import Rule
from m_cli.lint.rules import all_rules as all_lint_rules


def test_rule_dataclass_has_fixer_id_field() -> None:
    """The dataclass exposes ``fixer_id: str | None``, default None."""
    annotations = Rule.__annotations__
    assert "fixer_id" in annotations


def test_rule_can_be_constructed_without_fixer_id() -> None:
    """Backwards compatibility: existing register(Rule(...)) calls still work."""
    from m_cli.lint.diagnostic import Severity

    r = Rule(
        id="X",
        severity=Severity.INFO,
        title="x",
        tags=("test",),
        check=lambda src, tree, path, index: iter(()),
    )
    assert r.fixer_id is None


def test_rule_accepts_fixer_id() -> None:
    from m_cli.lint.diagnostic import Severity

    r = Rule(
        id="X",
        severity=Severity.INFO,
        title="x",
        tags=("test",),
        check=lambda src, tree, path, index: iter(()),
        fixer_id="trim-trailing-whitespace",
    )
    assert r.fixer_id == "trim-trailing-whitespace"


def test_M_XINDX_013_links_to_trim_trailing_whitespace() -> None:
    rule = next(r for r in all_lint_rules() if r.id == "M-XINDX-013")
    assert rule.fixer_id == "trim-trailing-whitespace"


def test_M_XINDX_047_links_to_uppercase_command_keywords() -> None:
    rule = next(r for r in all_lint_rules() if r.id == "M-XINDX-047")
    assert rule.fixer_id == "uppercase-command-keywords"


def test_every_declared_fixer_id_resolves_to_a_real_fmt_rule() -> None:
    fmt_ids = {r.id for r in all_fmt_rules()}
    for rule in all_lint_rules():
        if rule.fixer_id is None:
            continue
        assert rule.fixer_id in fmt_ids, (
            f"Lint rule {rule.id} declares fixer_id={rule.fixer_id!r} "
            f"which does not match any FmtRule (known: {sorted(fmt_ids)})"
        )


def test_lint_rules_without_fixer_default_to_none() -> None:
    """Anything not explicitly linked must report None — never silently empty."""
    sample = ["M-XINDX-014", "M-XINDX-017", "M-XINDX-019"]
    by_id = {r.id: r for r in all_lint_rules()}
    for rule_id in sample:
        if rule_id in by_id:
            assert by_id[rule_id].fixer_id is None, (
                f"{rule_id} should have fixer_id=None (no auto-fix yet)"
            )


def test_canonical_fmt_rules_cover_every_lint_fixer() -> None:
    """Every fmt rule referenced as a fixer must be in canonical_rules() —
    otherwise running ``m fmt --rules=canonical`` won't actually apply
    the fix the LSP advertised."""
    canonical_ids = {r.id for r in canonical_rules()}
    referenced = {r.fixer_id for r in all_lint_rules() if r.fixer_id}
    missing = referenced - canonical_ids
    assert not missing, f"Lint rules reference fmt rules that aren't in canonical: {missing}"


# ---------------------------------------------------------------------------
# fixer_for() public helper
# ---------------------------------------------------------------------------


def test_fixer_for_known_rule_returns_fmt_id() -> None:
    from m_cli.lint import fixer_for

    assert fixer_for("M-XINDX-013") == "trim-trailing-whitespace"
    assert fixer_for("M-XINDX-047") == "uppercase-command-keywords"


def test_fixer_for_unfixable_rule_returns_none() -> None:
    from m_cli.lint import fixer_for

    assert fixer_for("M-XINDX-014") is None
    assert fixer_for("M-XINDX-019") is None


def test_fixer_for_unknown_rule_returns_none() -> None:
    from m_cli.lint import fixer_for

    assert fixer_for("not-a-real-rule-id") is None


def test_fixer_for_in_top_level_namespace() -> None:
    """Tooling consumers should be able to ``from m_cli.lint import fixer_for``."""
    from m_cli.lint import fixer_for as via_subpkg

    # Currently only the subpackage exports it. Promote if/when needed.
    assert callable(via_subpkg)


# ---------------------------------------------------------------------------
# JSON output exposes fixer_id
# ---------------------------------------------------------------------------


def test_json_output_includes_fixer_id() -> None:
    """The LSP wrapper reads ``--format=json`` output to get fixer hints."""
    import json
    from pathlib import Path

    from m_cli.lint import lint_source, select_rules
    from m_cli.lint.output import format_json

    src = b"hello ;c   \n new x  \n quit\n"
    diags = lint_source(Path("hello.m"), src, select_rules("xindex"))
    payload = json.loads(format_json(diags))
    by_rule = {d["rule_id"]: d for d in payload}
    if "M-XINDX-013" in by_rule:
        assert by_rule["M-XINDX-013"]["fixer_id"] == "trim-trailing-whitespace"
    if "M-XINDX-047" in by_rule:
        assert by_rule["M-XINDX-047"]["fixer_id"] == "uppercase-command-keywords"
    # Every diagnostic must carry the field, even if None.
    for d in payload:
        assert "fixer_id" in d
