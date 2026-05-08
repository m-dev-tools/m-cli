"""Tests for the M-DOC-NN documentation rules.

The grammar these rules validate is specified in
m-stdlib/docs/guides/m-doc-grammar.md. Acceptance gate for WA3 in
m-stdlib's docs/tracking/discoverability-tracker.md.
"""

from __future__ import annotations

from pathlib import Path

from m_cli.lint import lint_source, select_rules
from m_cli.lint.context import LintContext
from m_cli.lint.thresholds import validate as validate_thresholds


def _ctx(**overrides) -> LintContext:
    return LintContext(thresholds=validate_thresholds(overrides))


def _lint(src: bytes, rule_id: str, *, ctx: LintContext | None = None):
    rules = select_rules(rule_id)
    return lint_source(Path(rule_id.replace("-", "") + ".m"), src, rules, ctx=ctx)


# ---------------------------------------------------------------------------
# M-DOC-001 — public label missing required M-doc tags
# ---------------------------------------------------------------------------


def _fully_tagged_label() -> bytes:
    """A label with the complete M-doc tag set — fires zero diagnostics."""
    return (
        b"FOO     ; m-stdlib fixture\n"
        b"        quit\n"
        b"        ;\n"
        b"greet(who)      ; Greet someone.\n"
        b"        ; doc: @param who   string  the name to greet\n"
        b"        ; doc: @returns     string  the rendered greeting\n"
        b"        ; doc: @example     write $$greet^FOO(\"world\")\n"
        b"        ; doc: @since       v0.1.0\n"
        b"        ; doc: @stable      stable\n"
        b"        ; doc: @see         $$bye^FOO\n"
        b"        quit \"hello, \"_who\n"
    )


class TestFullyTaggedLabel:
    def test_silent_when_complete(self):
        assert _lint(_fully_tagged_label(), "M-DOC-001", ctx=_ctx()) == []


class TestInternalSkipped:
    def test_internal_label_is_silent(self):
        # @internal in the doc block excludes the label from M-DOC-001
        # the same way it excludes it from the manifest.
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"helper(x,y)     ; Internal helper.\n"
            b"        ; doc: @internal\n"
            b"        ; doc: Used by greet().\n"
            b"        quit x+y\n"
        )
        assert _lint(src, "M-DOC-001", ctx=_ctx()) == []


class TestNoDocBlockSkipped:
    def test_label_without_doc_block_is_silent(self):
        # No `; doc:` block at all → not "public" per the grammar.
        # M-DOC-001 doesn't fire on these (M-MOD-028 covers the
        # docstring-presence check separately).
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"helper(x)\n"
            b"        new y set y=x*2\n"
            b"        quit y\n"
        )
        assert _lint(src, "M-DOC-001", ctx=_ctx()) == []


class TestMissingParam:
    def test_missing_param_for_formal(self):
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"add(a,b)        ; Sum a+b.\n"
            b"        ; doc: @param a   int  first operand\n"
            b"        ; doc: @returns   int  the sum\n"
            b"        ; doc: @since     v0.1.0\n"
            b"        ; doc: @stable    stable\n"
            b"        quit a+b\n"
        )
        diags = _lint(src, "M-DOC-001", ctx=_ctx())
        assert len(diags) == 1
        assert "@param for formal 'b'" in diags[0].message

    def test_extra_param_not_in_formals(self):
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"add(a,b)        ; Sum a+b.\n"
            b"        ; doc: @param a   int  first\n"
            b"        ; doc: @param b   int  second\n"
            b"        ; doc: @param c   int  spurious\n"
            b"        ; doc: @returns   int  the sum\n"
            b"        ; doc: @since     v0.1.0\n"
            b"        ; doc: @stable    stable\n"
            b"        quit a+b\n"
        )
        diags = _lint(src, "M-DOC-001", ctx=_ctx())
        assert len(diags) == 1
        assert "@param 'c' not in formal-list" in diags[0].message


class TestMissingReturns:
    def test_quit_value_without_returns_fires(self):
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"answer()        ; The answer.\n"
            b"        ; doc: @since   v0.1.0\n"
            b"        ; doc: @stable  stable\n"
            b"        quit 42\n"
        )
        diags = _lint(src, "M-DOC-001", ctx=_ctx())
        msgs = [d.message for d in diags]
        assert any("'quit <expression>' but no @returns" in m for m in msgs)

    def test_value_less_quit_does_not_require_returns(self):
        # Procedure-form: bare `quit` means no return value, so @returns
        # is not required.
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"reset()         ; Reset state.\n"
            b"        ; doc: @since   v0.1.0\n"
            b"        ; doc: @stable  stable\n"
            b"        kill ^X\n"
            b"        quit\n"
        )
        diags = _lint(src, "M-DOC-001", ctx=_ctx())
        msgs = [d.message for d in diags]
        assert not any("@returns" in m for m in msgs)


class TestMissingRaises:
    def test_undeclared_ecode_fires(self):
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"check(x)        ; Validate x.\n"
            b"        ; doc: @param x   int  the value to check\n"
            b"        ; doc: @since     v0.1.0\n"
            b"        ; doc: @stable    stable\n"
            b"        if x<0 set $ecode=\",U-FOO-NEG,\" quit\n"
            b"        quit\n"
        )
        diags = _lint(src, "M-DOC-001", ctx=_ctx())
        msgs = [d.message for d in diags]
        assert any("U-FOO-NEG" in m and "@raises" in m for m in msgs)

    def test_declared_ecode_silent(self):
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"check(x)        ; Validate x.\n"
            b"        ; doc: @param x      int  the value to check\n"
            b"        ; doc: @raises       U-FOO-NEG  x is negative\n"
            b"        ; doc: @since        v0.1.0\n"
            b"        ; doc: @stable       stable\n"
            b"        if x<0 set $ecode=\",U-FOO-NEG,\" quit\n"
            b"        quit\n"
        )
        diags = _lint(src, "M-DOC-001", ctx=_ctx())
        assert diags == []

    def test_ecode_inside_at_example_doc_does_not_fire(self):
        # An @example body that *demonstrates* what a caller might do
        # (set $ecode on a callee's return) is NOT a $ECODE the label
        # itself raises — the lint rule should ignore those. False-
        # positive caught while running M-DOC-001 against m-stdlib's
        # STDCSPRNG.available; pinned here.
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"available()     ; Probe.\n"
            b"        ; doc: @returns      bool    1 iff probe succeeds\n"
            b"        ; doc: @example      if '$$available^FOO() set $ecode=\",U-MYAPP-NO-FOO,\"\n"
            b"        ; doc: @since        v0.1.0\n"
            b"        ; doc: @stable       stable\n"
            b"        quit 1\n"
        )
        diags = _lint(src, "M-DOC-001", ctx=_ctx())
        msgs = [d.message for d in diags]
        assert not any("@raises" in m for m in msgs)


class TestMissingSinceStable:
    def test_missing_since_fires(self):
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"reset()         ; Reset.\n"
            b"        ; doc: @stable      stable\n"
            b"        quit\n"
        )
        diags = _lint(src, "M-DOC-001", ctx=_ctx())
        msgs = [d.message for d in diags]
        assert any("@since" in m for m in msgs)

    def test_missing_stable_fires(self):
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"reset()         ; Reset.\n"
            b"        ; doc: @since   v0.1.0\n"
            b"        quit\n"
        )
        diags = _lint(src, "M-DOC-001", ctx=_ctx())
        msgs = [d.message for d in diags]
        assert any("@stable" in m for m in msgs)


class TestStableValueValidated:
    def test_unknown_level_fires(self):
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"reset()         ; Reset.\n"
            b"        ; doc: @since    v0.1.0\n"
            b"        ; doc: @stable   beta\n"
            b"        quit\n"
        )
        diags = _lint(src, "M-DOC-001", ctx=_ctx())
        msgs = [d.message for d in diags]
        assert any("'beta'" in m and "experimental/stable/deprecated" in m for m in msgs)

    def test_deprecated_without_deprecated_tag_fires(self):
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"oldThing()      ; Legacy.\n"
            b"        ; doc: @since    v0.1.0\n"
            b"        ; doc: @stable   deprecated\n"
            b"        quit\n"
        )
        diags = _lint(src, "M-DOC-001", ctx=_ctx())
        msgs = [d.message for d in diags]
        assert any("@stable deprecated" in m and "@deprecated tag" in m for m in msgs)

    def test_deprecated_with_deprecated_tag_silent(self):
        src = (
            b"FOO     ; fixture\n"
            b"        quit\n"
            b"        ;\n"
            b"oldThing()      ; Legacy.\n"
            b"        ; doc: @since        v0.1.0\n"
            b"        ; doc: @stable       deprecated\n"
            b"        ; doc: @deprecated   v0.2.0  use $$newThing^FOO instead\n"
            b"        ; doc: @see          $$newThing^FOO\n"
            b"        quit\n"
        )
        diags = _lint(src, "M-DOC-001", ctx=_ctx())
        # The only thing that COULD still fire is @returns (this label
        # has no quit-value, so it shouldn't). Confirm zero.
        assert diags == []


class TestRuleIsTaggedModern:
    def test_rule_is_in_modern_profile(self):
        from m_cli.lint.rules import rules_by_tag

        ids = {r.id for r in rules_by_tag("modern")}
        assert "M-DOC-001" in ids

    def test_rule_is_in_doc_tag(self):
        from m_cli.lint.rules import rules_by_tag

        ids = {r.id for r in rules_by_tag("doc")}
        assert "M-DOC-001" in ids
