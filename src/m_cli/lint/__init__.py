"""m lint — the M (MUMPS) linter.

Tier 1, Step 2 of the M ecosystem gap-remediation plan
(see docs/m-tooling-tier1.md in the m-tools repo).

Design separation
=================

The lint engine itself is engine- and dialect-neutral: it registers
rules and runs them. Opinionated rule sets ride on top as named
**profiles**, defined in :mod:`m_cli.lint.profiles`. This split is
intentional — it lets m-cli ship VA-flavoured profiles without ever
implying that those profiles are the "M standard", and gives IRIS-,
YDB-, or ANSI-flavoured profiles a clean home alongside.

Built-in profiles (selected via ``m lint --rules <name>``):

- **default** — m-cli's curated baseline. Today this is what `xindex`
  selects (because that's the only rule family that has shipped yet);
  the indirection is the lever for adding engine-specific rules later
  without forcing every project to rename its config.
- **xindex** — port of the VA VistA Toolkit ``^XINDEX`` rule set
  (42 of XINDEX's 66 rules; rule IDs ``M-XINDX-NN`` mirror XINDEX's
  numeric error codes 1:1). XINDEX is a VA tool — it is **not** part
  of the M standard and is **not** shipped by IRIS or YottaDB.
- **sac** — VA SAC (Standards & Conventions) subset. Smaller,
  style-focused.
- **all** — every registered rule.

Run ``m lint --list-profiles`` to see what's available at runtime.

The framework is parser-aware (tree-sitter-m AST) so it can express
checks that pure text scanners cannot (postconditional argument
analysis, naked-reference flow, label-call resolution).

Public library surface (stable for out-of-tree tooling):

    from m_cli.lint import (
        lint_source,        # (path, src, rules) -> list[Diagnostic]
        select_rules,       # (str) -> list[Rule]    (e.g. "default", "xindex", "M-XINDX-013")
        Rule, Diagnostic, Severity,
    )
"""

# Side-effect import: registers M-MOD-NN rules. Must come after `rules`
# is imported (so the registry exists) and after `profiles` (so
# `modern` is registered before any code calls list_profiles()).
from m_cli.lint import _modern as _modern_rules  # noqa: F401

# Side-effect import: registers M-DOC-NN rules. Loaded after `_modern`
# because _doc imports `_label_body_extents` from there. The M-DOC
# family validates the M-doc tag grammar specified in m-stdlib's
# `docs/guides/m-doc-grammar.md` (WA1) and feeds the manifest
# generator (WA4).
from m_cli.lint import _doc as _doc_rules  # noqa: F401
from m_cli.lint.cli import lint_command
from m_cli.lint.context import LintContext
from m_cli.lint.diagnostic import Category, Diagnostic, Severity
from m_cli.lint.profiles import (
    DEFAULT_PROFILE,
    Profile,
    get_profile,
    list_profiles,
    register_profile,
    resolve_profile,
)
from m_cli.lint.rules import Rule
from m_cli.lint.runner import fixer_for, lint_source, select_rules

__all__ = [
    "DEFAULT_PROFILE",
    "Category",
    "Diagnostic",
    "LintContext",
    "Profile",
    "Rule",
    "Severity",
    "fixer_for",
    "get_profile",
    "lint_command",
    "lint_source",
    "list_profiles",
    "register_profile",
    "resolve_profile",
    "select_rules",
]
