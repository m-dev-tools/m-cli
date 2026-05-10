"""`m capabilities` — machine-readable view of the m CLI surface.

Drives `dist/commands.json`, which the tier-1 `repo.meta.json` exposes
as the `commands` payload. The output is derived from the live argparse
parser tree — there is no hand-curated catalog.
"""

from m_cli.capabilities.cli import build_capabilities, capabilities_command

__all__ = ["build_capabilities", "capabilities_command"]
