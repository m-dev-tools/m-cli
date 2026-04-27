"""m-cli — the M (MUMPS) source-level toolchain.

Entry-point binary `m` with subcommands `fmt`, `lint`, `test`. Tier 1 of
the M ecosystem gap-remediation plan.

The package is built on tree-sitter-m and m-standard. See
docs/m-tooling-tier1.md in the m-tools repo for the strategy doc.
"""

import logging

__version__ = "0.1.0"

logging.getLogger(__name__).addHandler(logging.NullHandler())
