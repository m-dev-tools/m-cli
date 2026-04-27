"""m lint — the M (MUMPS) linter.

Tier 1, Step 2 of the M ecosystem gap-remediation plan
(see docs/m-tooling-tier1.md in the m-tools repo).

Rule families (selected via `m lint --rules <family>`):

- **xindex** — replicates the VistA Toolkit `^XINDEX` rule set as the
  initial baseline. Rule IDs of the form `M-XINDX-<NN>` map 1:1 to
  XINDEX error codes (XINDEX source: VistA-M Toolkit/Routines/XINDX*.m).
  This family is the design-decision baseline (see m-tooling-tier1.md
  §5.2).

- **sac** — VA SAC (Standards & Conventions) compliance, driven by
  m-standard's SAC mappings. *Planned, not in the initial rule set.*

- **all** — every rule the linter knows.

The framework is parser-aware (tree-sitter-m AST) so it can express
checks that pure text scanners cannot (postconditional argument
analysis, naked-reference flow, label-call resolution).
"""

from m_cli.lint.cli import lint_command
from m_cli.lint.diagnostic import Diagnostic, Severity
from m_cli.lint.runner import lint_source

__all__ = ["lint_command", "lint_source", "Diagnostic", "Severity"]
