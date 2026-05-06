"""m-cli — the M (MUMPS) source-level toolchain.

Entry-point binary `m` with subcommands `fmt`, `lint`, `test`, `watch`.
Tier 1 of the M ecosystem gap-remediation plan.

This module re-exports the **public library API** that out-of-tree
tooling (LSP server, IDE plugins, CI integrations) is expected to
consume. The names listed in ``__all__`` are stable: future internal
refactors will keep them importable from this top-level package.

    from m_cli import (
        parse,                                # parse M source bytes -> Tree
        format_source, canonical_rules,       # m fmt
        select_fmt_rules, FmtRule, ParseError,
        lint_source, select_rules, Rule,      # m lint
        Diagnostic, Severity,
    )

Internal helpers (per-rule check functions, AST walkers, registry
internals) are not part of the public surface and may move.
"""

import logging

from m_cli.fmt import (
    FmtRule,
    ParseError,
    canonical_rules,
    compact_rules,
    format_source,
    pythonic_lower_rules,
    pythonic_rules,
    sac_rules,
    select_fmt_rules,
)
from m_cli.lint import (
    Category,
    Diagnostic,
    Rule,
    Severity,
    lint_source,
    select_rules,
)
from m_cli.parser import parse

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # parser
    "parse",
    # m fmt
    "format_source",
    "canonical_rules",
    "pythonic_rules",
    "pythonic_lower_rules",
    "compact_rules",
    "sac_rules",
    "select_fmt_rules",
    "FmtRule",
    "ParseError",
    # m lint
    "lint_source",
    "select_rules",
    "Rule",
    "Diagnostic",
    "Severity",
    "Category",
]

logging.getLogger(__name__).addHandler(logging.NullHandler())
