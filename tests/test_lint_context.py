"""Tests for m_cli.lint.context — the LintContext dataclass and
its plumbing through lint_source.
"""

from __future__ import annotations

from pathlib import Path

from m_cli.lint import lint_source, select_rules
from m_cli.lint.context import LintContext, ensure_context
from m_cli.lint.thresholds import KNOWN_THRESHOLDS


class TestLintContextDefaults:
    def test_empty_context_has_default_thresholds(self):
        ctx = LintContext.empty()
        assert ctx.thresholds == KNOWN_THRESHOLDS
        assert ctx.target_engine == "any"
        assert ctx.workspace is None
        assert ctx.config is None

    def test_default_constructor_is_minimal(self):
        ctx = LintContext()
        assert ctx.target_engine == "any"
        assert ctx.workspace is None
        assert ctx.config is None
        # `thresholds` defaults to {} — defaults are filled in via
        # `validate()` at the call site, not by the dataclass itself.
        assert ctx.thresholds == {}

    def test_ensure_context_with_none_returns_empty(self):
        ctx = ensure_context(None)
        assert isinstance(ctx, LintContext)
        assert ctx.thresholds == KNOWN_THRESHOLDS

    def test_ensure_context_passes_through(self):
        original = LintContext(thresholds={"line_length": 80})
        ctx = ensure_context(original)
        assert ctx is original


class TestPlumbing:
    """The `lint_source` runner threads `ctx` through to context-aware
    rules without breaking the no-context fast path."""

    def test_lint_source_accepts_ctx_kwarg(self):
        # Standard rules ignore the context entirely; this exercises
        # the no-op path.
        src = b"hello ;c\n quit\n"
        rules = select_rules("M-XINDX-013")  # pure single-file rule
        ctx = LintContext.empty()
        diags = lint_source(Path("hello.m"), src, rules, ctx=ctx)
        # Source has no trailing whitespace; no findings expected.
        assert diags == []

    def test_lint_source_runs_without_ctx(self):
        # Backward compat: callers that don't pass ctx still work.
        src = b"hello ;c\n quit\n"
        rules = select_rules("M-XINDX-013")
        diags = lint_source(Path("hello.m"), src, rules)
        assert diags == []

    def test_lint_source_workspace_kwarg_still_works(self):
        # Back-compat shim: existing callers passing workspace= keep
        # working without rewrites.
        src = b"hello ;c\n quit\n"
        rules = select_rules("M-XINDX-013")
        diags = lint_source(Path("hello.m"), src, rules, workspace=None)
        assert diags == []
