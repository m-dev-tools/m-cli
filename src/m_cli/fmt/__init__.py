"""m fmt — the M (MUMPS) formatter.

Tier 1, Step 1 of the M ecosystem gap-remediation plan
(see docs/m-tooling-tier1.md in the m-tools repo).

Two layers:

1. **Identity pass** — parses the source via tree-sitter-m and emits
   the bytes verbatim. Round-trip-clean on 99.04% of VistA's 39,330
   routines. Default behavior of `m fmt`.

2. **Canonical-layout rules** (opt-in via ``--rules=canonical``) —
   pure ``bytes -> bytes`` transformations layered on top of identity.
   Each rule must be idempotent and AST-shape-preserving. Backed by
   ``make vista-canonical`` over the full corpus.

Public library surface (stable for out-of-tree tooling):

    from m_cli.fmt import (
        format_source,       # (src, *, rules=None) -> bytes
        format_file,         # (path, *, rules=None) -> (src, formatted)
        canonical_rules,     # () -> list[FmtRule]
        select_fmt_rules,    # (str) -> list[FmtRule]   (e.g. "canonical")
        FmtRule, ParseError,
    )
"""

from m_cli.fmt.cli import fmt_command
from m_cli.fmt.formatter import ParseError, format_file, format_source
from m_cli.fmt.rules import FmtRule, all_rules, canonical_rules, rule_by_id, select_fmt_rules

__all__ = [
    "fmt_command",
    "format_source",
    "format_file",
    "canonical_rules",
    "select_fmt_rules",
    "all_rules",
    "rule_by_id",
    "FmtRule",
    "ParseError",
]
