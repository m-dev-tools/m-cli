"""m new — project scaffolder.

`m new <name>` creates a self-contained M project that passes
`m fmt --check`, `m lint`, and `m test` on a clean clone. The
generated layout follows the m-cli conventions (`routines/` for source,
`tests/` for `*TST.m` suites) and uses the pythonic-lower modern style.
"""

from m_cli.new.cli import new_command
from m_cli.new.scaffold import (
    Scaffold,
    derive_routine_name,
    render_scaffold,
)

__all__ = ["new_command", "Scaffold", "derive_routine_name", "render_scaffold"]
