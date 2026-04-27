"""m fmt — the M (MUMPS) formatter.

Tier 1, Step 1 of the M ecosystem gap-remediation plan
(see docs/m-tooling-tier1.md in the m-tools repo).

The formatter is a **lossless byte-range pretty-printer** built on
tree-sitter-m. It is idempotent (`m fmt | m fmt` produces no further
change) and round-trips any conformant M source.

Initial implementation: the **identity formatter** — parses the source,
walks the tree, and emits the original bytes exactly. This validates
the parser+round-trip plumbing before any canonical-layout rules are
layered on top.
"""

from m_cli.fmt.cli import fmt_command
from m_cli.fmt.formatter import ParseError, format_file, format_source

__all__ = ["fmt_command", "format_source", "format_file", "ParseError"]
