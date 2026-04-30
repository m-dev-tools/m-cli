"""LintContext — runtime context passed to context-aware rules.

Rules opt in by setting ``needs_context=True`` on their ``Rule``
declaration. The runner constructs a :class:`LintContext` once per
``m lint`` invocation (or per ``didChange`` in the LSP) and threads
it through ``lint_source`` to every context-aware rule.

The context bundles every per-run knob a rule might need into a
single immutable handle:

  - **thresholds** — resolved from ``[lint.thresholds]`` config (with
    defaults filled in). Used by the M-MOD-001..004 rules.
  - **target_engine** — ``"any"`` / ``"yottadb"`` / ``"iris"``. Used
    by engine-aware allowlist rules (Phase 6).
  - **workspace** — :class:`m_cli.workspace.WorkspaceIndex` if any
    rule in the active set needs cross-routine context, else ``None``.
    Replaces the legacy ``needs_workspace`` flag — rules that used
    it now read ``ctx.workspace``.
  - **config** — the resolved :class:`m_cli.config.Config` for any
    other ad-hoc lookups a rule may need.

Forward growth: new per-run knobs (taint sources/sinks, custom rule
parameters) attach here without changing every rule's signature.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from m_cli.config import Config
    from m_cli.workspace import WorkspaceIndex


@dataclass(frozen=True)
class LintContext:
    """Per-run context for rules that need configuration or the workspace.

    Constructed once at lint-command entry and threaded through to every
    context-aware rule. Frozen so that rules cannot mutate it across
    files within a run.
    """

    thresholds: dict[str, int] = field(default_factory=dict)
    target_engine: str = "any"
    workspace: "WorkspaceIndex | None" = None
    config: "Config | None" = None

    @staticmethod
    def empty() -> "LintContext":
        """Return a context with all defaults — useful for tests and
        for the no-config code path."""
        from m_cli.lint.thresholds import validate

        return LintContext(thresholds=validate(None))


# Sentinel used internally by lint_source when a rule declares
# needs_context=True but the caller passed no ctx — equivalent to
# how None-workspace was handled previously.
def ensure_context(ctx: LintContext | None) -> LintContext:
    """Return ``ctx`` if non-None, else a fresh defaults-only context."""
    return ctx if ctx is not None else LintContext.empty()


__all__ = ["LintContext", "ensure_context"]
